import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.dirname(__file__))

from config import settings

try:
    from backend.database.db import init_db
    from backend.api.routes import router as audit_router
    from backend.api.auth_routes import router as auth_router
    from backend.api.case_routes import router as case_router
    from backend.api.analytics_routes import router as analytics_router
    from backend.utils.logging import get_logger
except ImportError:
    from database.db import init_db
    from api.routes import router as audit_router
    from api.auth_routes import router as auth_router
    from api.case_routes import router as case_router
    from api.analytics_routes import router as analytics_router
    from utils.logging import get_logger

logger = get_logger(__name__)

_window = f"{settings.rate_limit_window_seconds}second"
_limit_str = f"{settings.rate_limit_requests}/{_window}"
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Auditor Platform")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Auditor Platform",
    version="2.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://codeperfect-audit.vercel.app",
        "https://codeperfect-audit-git-main-quirkynerds-projects.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Limit: {_limit_str} per IP."
        },
    )


app.include_router(audit_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(case_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "Auditor Platform",
        "version": "2.3.0",
        "docs": "/docs"
    }