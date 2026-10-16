"""
TechPulse AI — FastAPI application entry point.

Start locally:
    cd backend
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Production (Render):
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.analysis import router as analysis_router
from app.api.digest import router as digest_router
from app.api.news import router as news_router
from app.api.summary import router as summary_router
from app.config.settings import settings
from app.database.connection import close_connection, get_database, test_connection
from app.database.repository import ensure_indexes
from app.utils.logging_config import get_logger

logger = get_logger("techpulse.main")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("TechPulse AI starting up...")
    _validate_config()
    if test_connection():
        ensure_indexes()
        logger.info("MongoDB connected and indexes verified.")
    else:
        logger.warning(
            "MongoDB connection failed at startup. "
            "The application will start but database operations will fail."
        )
    yield
    # Shutdown
    logger.info("TechPulse AI shutting down...")
    close_connection()


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic AI Platform for Real-Time Technology News",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Origins are configured via FRONTEND_ORIGIN in .env
# Multiple origins can be separated by commas:
#   FRONTEND_ORIGIN=https://yourapp.vercel.app,http://localhost:5173
_origins = [o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(news_router)
app.include_router(summary_router)
app.include_router(analysis_router)
app.include_router(digest_router)
app.include_router(admin_router)


def _validate_config() -> None:
    """Log a warning for any required settings that are missing."""
    warnings = []
    if not settings.MONGODB_URI:
        warnings.append("MONGODB_URI is not set")
    if not settings.OPENROUTER_API_KEY:
        warnings.append("OPENROUTER_API_KEY is not set — AI features will fail")
    if settings.ADMIN_API_KEY == "change-me-in-production":
        warnings.append("ADMIN_API_KEY is using the default value — change it in production")
    if settings.WHATSAPP_DRY_RUN:
        logger.info("WhatsApp is in DRY_RUN mode — no messages will be sent")

    for w in warnings:
        logger.warning("CONFIG WARNING: %s", w)


# ── Root routes ───────────────────────────────────────────────────────────────

@app.get("/", tags=["Status"])
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health", tags=["Status"])
def health():
    """
    Health check endpoint.
    Returns database connectivity status without exposing credentials.
    """
    db_ok = test_connection()
    db_name = get_database().name if db_ok else "unavailable"

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "healthy" if db_ok else "degraded",
            "version": settings.APP_VERSION,
            "database": "connected" if db_ok else "disconnected",
            "database_name": db_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
