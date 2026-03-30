"""
main.py – FastAPI entrypoint (v2.1 – FIXED CORS + STABILITY)
"""

import sys
import os
import json
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

_window    = f"{settings.rate_limit_window_seconds}second"
_limit_str = f"{settings.rate_limit_requests}/{_window}"
limiter    = Limiter(key_func=get_remote_address)

def get_cors_origins():
    """
    Safely parse CORS origins from env or settings.
    Ensures localhost + 127.0.0.1 always allowed.
    """
    origins = settings.cors_origins

    if isinstance(origins, str):
        try:
            origins = json.loads(origins)
        except Exception:
            logger.warning("Failed to parse CORS_ORIGINS, using default fallback.")
            origins = []

    if not isinstance(origins, list):
        origins = []

    default_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ]

    for origin in default_origins:
        if origin not in origins:
            origins.append(origin)

    logger.info(f"CORS enabled for origins: {origins}")
    return origins

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Auditor Platform")
    await init_db()
    logger.info("Database tables initialised.")
    yield
    logger.info("Shutting down.")

app = FastAPI(
    title="Auditor Platform",
    version="2.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
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

app.include_router(audit_router,     prefix="/api/v1")
app.include_router(auth_router,      prefix="/api/v1")
app.include_router(case_router,      prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

@app.get("/", tags=["root"])
async def root():
    return {
        "service": "Auditor Platform",
        "version": "2.1.0",
        "docs": "/docs"
    }