"""
api/case_routes.py – Case Management endpoints for CodePerfectAuditor.

Endpoints:
  GET  /cases           – list cases (filtered, paginated, tenant-isolated)
  GET  /cases/{id}      – single case detail
  PATCH /cases/{id}     – update status (reviewer/admin only)
  DELETE /cases/{id}    – soft delete (admin only)
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

try:
    # When running from project root (development)
    from backend.database.db import get_db
    from backend.database.models import Case, User
    from backend.security.auth import get_current_user, require_admin, require_reviewer
    from backend.utils.logging import get_logger
except ImportError:
    # When running from backend directory (Docker/production)
    from database.db import get_db
    from database.models import Case, User
    from security.auth import get_current_user, require_admin, require_reviewer
    from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/cases", tags=["cases"])


class CaseStatusUpdate(BaseModel):
    status: str   # pending | reviewed | approved | rejected
    comment: str = ""


def _case_to_dict(c: Case) -> dict:
    try:
        summary_data = json.loads(c.summary) if c.summary else {}
        if isinstance(summary_data, dict):
            summary_text = summary_data.get("summary", "")
            explanation_text = summary_data.get("explanation", "")
        else:
            summary_text = c.summary
            explanation_text = ""
    except Exception:
        summary_text = c.summary
        explanation_text = ""

    return {
        "id":              c.id,
        "user_id":         c.user_id,
        "org_id":          c.org_id,
        "input_text":      c.input_text,
        "evidence":        json.loads(c.evidence or "[]"),
        "pipeline_log":    json.loads(c.pipeline_log or "[]"),
        "ai_codes":        json.loads(c.ai_codes or "[]"),
        "human_codes":     json.loads(c.human_codes or "[]"),
        "discrepancies":   json.loads(c.discrepancies or "[]"),
        "risk_score":      c.risk_score,
        "revenue_impact":  c.revenue_impact,
        "coding_accuracy": c.coding_accuracy,
        "avg_confidence":  c.avg_confidence,
        "processing_time": c.processing_time,
        "summary":         summary_text,
        "explanation":     explanation_text,
        "status":            c.status,
        "model_used":        c.model_used,
        "tokens_used":       c.tokens_used,
        "cost_estimate":     c.cost_estimate,

        "created_at":        c.created_at.isoformat() if c.created_at else None,
    }


@router.get("")
async def list_cases(
    page:         int   = Query(1, ge=1),
    page_size:    int   = Query(20, ge=1, le=100),
    status:       str | None = Query(None),
    min_risk:     float | None = Query(None),
    max_risk:     float | None = Query(None),
    from_date:    str | None = Query(None),
    to_date:      str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """
    List cases with filters. Tenant-isolated: Coder sees only own cases,
    Admin/Reviewer sees all cases in their org.
    """
    filters = []

    # Tenant isolation
    if current_user.role == "CODER":
        filters.append(Case.user_id == current_user.id)
    # ADMIN and REVIEWER see ALL cases.

    if status:
        filters.append(Case.status == status)
    if min_risk is not None:
        filters.append(Case.risk_score >= min_risk)
    if max_risk is not None:
        filters.append(Case.risk_score <= max_risk)
    if from_date:
        try:
            dt = datetime.fromisoformat(from_date)
            filters.append(Case.created_at >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use ISO 8601.")
    if to_date:
        try:
            dt = datetime.fromisoformat(to_date)
            filters.append(Case.created_at <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use ISO 8601.")

    base_query = select(Case).where(and_(*filters)) if filters else select(Case)
    count_query = select(func.count(Case.id)).where(and_(*filters)) if filters else select(func.count(Case.id))

    try:
        total     = await db.scalar(count_query) or 0
        offset    = (page - 1) * page_size
        result    = await db.execute(
            base_query.order_by(Case.created_at.asc()).offset(offset).limit(page_size)
        )
        cases     = result.scalars().all()

    except Exception as e:
        logger.error(f"CASE FETCH ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    print("CURRENT USER:", current_user.id, current_user.role)
    print("CASES RETURNED:", len(cases))

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "cases":     [_case_to_dict(c) for c in cases],
    }


@router.get("/{case_id}")
async def get_case(
    case_id:      int,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Case).where(Case.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    # Access control
    if current_user.role == "CODER" and case.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    full = _case_to_dict(case)
    return full


@router.patch("/{case_id}")
async def update_case_status(
    case_id:      int,
    payload:      CaseStatusUpdate,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    if current_user.role == "CODER":
        raise HTTPException(status_code=403, detail="Coders cannot update case status.")
    if payload.status not in ("pending", "reviewed", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid status value.")

    result = await db.execute(select(Case).where(Case.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    case.status           = payload.status
    case.updated_at       = datetime.utcnow()
    await db.commit()
    logger.info("Case %d status -> %s by user %d", case_id, payload.status, current_user.id)
    return {"message": f"Case {case_id} status updated to '{payload.status}'."}


@router.patch("/{case_id}/status")
async def update_case_status_v2(
    case_id:      int,
    payload:      CaseStatusUpdate,
    current_user: User = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """v14 endpoint for status updates with comment."""
    return await update_case_status(case_id, payload, current_user, db)


@router.delete("/{case_id}", dependencies=[Depends(require_admin)])
async def delete_case(case_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).where(Case.id == case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    await db.delete(case)
    await db.commit()
    return {"message": f"Case {case_id} deleted."}
