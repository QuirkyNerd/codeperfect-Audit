"""
backend/database/seed_users.py
Seed script for CodePerfectAuditor to create initial demo users with appropriate roles.
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.database.db import engine, async_session_maker, Base
from backend.database.models import User, Organization
from backend.security.auth import hash_password

async def seed():
    print("Seeding database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Create Demo Org
        org = Organization(name="Demo Hospital", domain="demo.com")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        # Create Users
        users = [
            User(
                org_id=org.id,
                email="admin@demo.com",
                hashed_password=hash_password("password123"),
                name="Admin User",
                role="ADMIN",
                is_active=True
            ),
            User(
                org_id=org.id,
                email="coder@demo.com",
                hashed_password=hash_password("password123"),
                name="Demo Coder",
                role="CODER",
                is_active=True
            ),
            User(
                org_id=org.id,
                email="reviewer@demo.com",
                hashed_password=hash_password("password123"),
                name="Demo Reviewer",
                role="REVIEWER",
                is_active=True
            )
        ]

        for user in users:
            session.add(user)

        await session.commit()
        print("Successfully seeded users (admin@demo.com, coder@demo.com, reviewer@demo.com). Password: password123")

if __name__ == "__main__":
    asyncio.run(seed())
