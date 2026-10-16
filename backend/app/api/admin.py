"""
Admin/internal API routes.
Protected by API key header — not exposed to public users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config.settings import settings
from app.database.repository import get_latest_job
from app.utils.logging_config import get_logger
from app.workflows.pipeline import run_daily_pipeline

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def _verify_admin_key(api_key: str | None = Depends(_api_key_header)) -> None:
    """Dependency: reject requests without a valid admin API key."""
    if not api_key or api_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin API key.",
        )


@router.post("/collect", dependencies=[Depends(_verify_admin_key)])
def trigger_collection(force: bool = False):
    """
    Manually trigger the full daily pipeline.
    Pass ?force=true to regenerate a digest even if one exists for today.

    Requires header:  X-Admin-Key: <ADMIN_API_KEY>
    """
    logger.info("Manual pipeline trigger requested (force=%s)", force)
    try:
        result = run_daily_pipeline(force=force)
        return {
            "success": result.get("success"),
            "message": "Pipeline completed.",
            "result": {
                k: str(v) if not isinstance(v, (int, float, bool, list, str, type(None))) else v
                for k, v in result.items()
            },
        }
    except Exception as exc:
        logger.error("Manual pipeline trigger failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {type(exc).__name__}")


@router.get("/status", dependencies=[Depends(_verify_admin_key)])
def get_job_status():
    """Return the most recent execution record for each known job."""
    collect_job = get_latest_job("daily_pipeline")
    return {
        "success": True,
        "jobs": {
            "daily_pipeline": collect_job,
        },
    }
