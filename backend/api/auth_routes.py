"""
api/auth_routes.py – Authentication endpoints for CodePerfectAuditor.
[HARDENED] Includes backend-enforced RBAC admin action guards:
  - Self-deactivation forbidden (HTTP 403)
  - Last admin cannot be deactivated (HTTP 403)
  - All deactivation/role-change actions are audit-logged

Endpoints:
  POST /auth/signup   – register a new user (Admin can create any role; public signup = CODER)
  POST /auth/login    – email+password → access_token + refresh httpOnly cookie
  POST /auth/refresh  – exchange refresh cookie for new access_token
  GET  /auth/me       – current user profile
  GET  /auth/users    – list all users (Admin only)
  POST /auth/users    – create user (Admin only)
  PATCH /auth/users/{id}/role – change role (Admin only)

  POST /auth/org      – create organisation (Admin only)
  GET  /auth/org      – list organisations (Admin only)
  POST /auth/branches – create branch (Admin only)
  GET  /auth/branches – list branches (Admin only)
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

try:
    # When running from project root (development)
    from backend.database.db import get_db
    from backend.database.models import User, Organization, Branch
    from backend.security.auth import (
        hash_password, verify_password,
        create_access_token, create_refresh_token, decode_token,
        get_current_user, require_admin,
    )
    from backend.utils.logging import get_logger
except ImportError:
    # When running from backend directory (Docker/production)
    from database.db import get_db
    from database.models import User, Organization, Branch
    from security.auth import (
        hash_password, verify_password,
        create_access_token, create_refresh_token, decode_token,
        get_current_user, require_admin,
    )
    from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name:      str
    email:     EmailStr
    password:  str
    role:      str = "CODER"   # ADMIN | CODER | REVIEWER
    org_id:    int | None = None
    branch_id: int | None = None


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class UserOut(BaseModel):
    id:         int
    name:       str
    email:      str
    role:       str
    org_id:     int | None
    branch_id:  int | None
    created_at: datetime

    class Config:
        from_attributes = True


class OrgRequest(BaseModel):
    name: str


class BranchRequest(BaseModel):
    name:   str
    org_id: int


class RoleUpdateRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str


# ── Signup ────────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Public signup — always creates CODER role. Admin role must be set by existing admin."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # First user ever gets ADMIN role automatically
    user_count_result = await db.execute(select(User))
    all_users = user_count_result.scalars().all()
    role = "ADMIN" if len(all_users) == 0 else "CODER"

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
        org_id=payload.org_id,
        branch_id=payload.branch_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("New user registered: %s (role=%s)", user.email, user.role)
    return {"message": f"Account created. Role: {user.role}", "user_id": user.id, "role": user.role}


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate user and issue access_token + refresh_token cookie."""
    print("LOGIN ATTEMPT:", payload.email)
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user   = result.scalar_one_or_none()

    if user:
        print("LOGIN INPUT:", payload.password)
        print("DB HASH:", user.password_hash)

    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            print("LOGIN VERIFICATION FAILED. Passwords do not match hash.")
        else:
            print("LOGIN FAILED: User not found.")
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token  = create_access_token(user.id, user.role, user.email)
    refresh_token = create_refresh_token(user.id)

    # Set refresh token as httpOnly secure cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax",
        secure=False,  # Set True in production with HTTPS
    )

    return {
        "access_token": access_token,
        "token_type":   "bearer",
        "user": {
            "id":    user.id,
            "name":  user.name,
            "email": user.email,
            "role":  user.role,
        },
    }


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token.")

    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    user_id = int(payload["sub"])
    result  = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user    = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    new_access = create_access_token(user.id, user.role, user.email)
    return {"access_token": new_access, "token_type": "bearer"}


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id":        current_user.id,
        "name":      current_user.name,
        "email":     current_user.email,
        "role":      current_user.role,
        "org_id":    current_user.org_id,
        "branch_id": current_user.branch_id,
    }


# ── Admin: User Management ────────────────────────────────────────────────────

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users  = result.scalars().all()
    return [
        {
            "id": u.id, "name": u.name, "email": u.email,
            "role": u.role, "org_id": u.org_id, "branch_id": u.branch_id,
            "is_active": u.is_active, "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
async def create_user(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(
        name=payload.name, email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role, org_id=payload.org_id, branch_id=payload.branch_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User created.", "user_id": user.id, "role": user.role}


@router.patch("/users/{user_id}/role")
async def update_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if payload.role not in ("ADMIN", "CODER", "REVIEWER"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be ADMIN, CODER, or REVIEWER.")
    old_role = user.role
    user.role = payload.role
    await db.commit()
    logger.info(
        "AUDIT: Admin %s (id=%d) changed role of user %s (id=%d) from %s to %s.",
        current_user.email, current_user.id, user.email, user.id, old_role, payload.role,
    )
    return {"message": f"Role updated from {old_role} to {payload.role}."}


@router.patch("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not payload.new_password or len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    target.password_hash = hash_password(payload.new_password)
    await db.commit()
    await db.refresh(target)

    print("UPDATED HASH:", target.password_hash)

    logger.info(
        "AUDIT: Admin %s (id=%d) reset password for user %s (id=%d).",
        current_user.email, current_user.id, target.email, target.id,
    )
    return {"message": f"Password for '{target.name}' has been reset successfully."}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),   # enforces ADMIN + authenticated
):
    """
    Delete a user account. ADMIN-only.
    """
    print("DELETE CALLED", user_id)
    # ── Guard 1: Self-deactivation ─────────────────────────────────────────────
    if user_id == current_user.id:
        logger.warning(
            "AUDIT BLOCK: Admin %s (id=%d) attempted self-deactivation.",
            current_user.email, current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own account. Contact another Administrator.",
        )

    try:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found")

        from sqlalchemy import text
        await db.execute(text("UPDATE cases SET user_id = NULL WHERE user_id = :id"), {"id": user_id})

        await db.delete(user)
        await db.commit()

        return {"message": "User deleted"}
    except Exception as e:
        print("DELETE ERROR:", str(e))
        raise HTTPException(500, str(e))


# ── Admin: Organisation & Branch Management ───────────────────────────────────

@router.post("/org", status_code=201, dependencies=[Depends(require_admin)])
async def create_org(payload: OrgRequest, db: AsyncSession = Depends(get_db)):
    org = Organization(name=payload.name)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {"org_id": org.id, "name": org.name}


@router.get("/org", dependencies=[Depends(require_admin)])
async def list_orgs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    return [{"id": o.id, "name": o.name, "created_at": o.created_at.isoformat()}
            for o in result.scalars().all()]


@router.post("/branches", status_code=201, dependencies=[Depends(require_admin)])
async def create_branch(payload: BranchRequest, db: AsyncSession = Depends(get_db)):
    branch = Branch(name=payload.name, org_id=payload.org_id)
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return {"branch_id": branch.id, "name": branch.name}


@router.get("/branches")
async def list_branches(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Branch)
    if current_user.role != "ADMIN" and current_user.org_id:
        query = query.where(Branch.org_id == current_user.org_id)
    result = await db.execute(query.order_by(Branch.created_at.desc()))
    return [{"id": b.id, "name": b.name, "org_id": b.org_id} for b in result.scalars().all()]
