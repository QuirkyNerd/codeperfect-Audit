"""
database/db.py – Async SQLAlchemy engine and session management.

Uses SQLite + aiosqlite by default (zero-config local development).
Switch to PostgreSQL by setting DATABASE_URL in .env, e.g.:
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/codeperfect
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from config import settings
from database.models import Base
try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
# NullPool is recommended for SQLite; for Postgres use default pool.
_pool_args = {}
if "sqlite" in settings.database_url:
    _pool_args["poolclass"] = NullPool
    _connect_args = {"check_same_thread": False}
else:
    _connect_args = {}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args,
    **_pool_args,
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    """Create all tables defined in models.py (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema verified / created.")


async def get_db():
    """
    FastAPI dependency that yields an AsyncSession per request.

    Usage:
        db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
