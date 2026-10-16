"""
Digest API routes — retrieve the latest daily digest.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytz
from fastapi import APIRouter, HTTPException, Query

from app.config.settings import settings
from app.database.repository import get_digest
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/digest", tags=["Digest"])

_IST = pytz.timezone(settings.TIMEZONE)


@router.get("/latest")
def get_latest_digest():
    """Return today's daily digest (Asia/Kolkata date)."""
    date_str = datetime.now(_IST).strftime("%Y-%m-%d")
    digest = get_digest(date_str)

    if not digest:
        return {
            "success": False,
            "message": f"No digest available for {date_str}. Run the collection pipeline first.",
            "date": date_str,
        }

    return {
        "success": True,
        "date": digest["date"],
        "article_count": digest.get("article_count", 0),
        "articles": digest.get("articles", []),
        "whatsapp_sent": digest.get("whatsapp_sent", False),
        "created_at": str(digest.get("created_at", "")),
    }


@router.get("/{date}")
def get_digest_by_date(date: str):
    """
    Return the digest for a specific date (YYYY-MM-DD).
    Date should be in Asia/Kolkata local date format.
    """
    # Basic format validation
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be in YYYY-MM-DD format.")

    digest = get_digest(date)
    if not digest:
        raise HTTPException(status_code=404, detail=f"No digest found for date: {date}")

    return {
        "success": True,
        "date": digest["date"],
        "article_count": digest.get("article_count", 0),
        "articles": digest.get("articles", []),
        "whatsapp_sent": digest.get("whatsapp_sent", False),
        "created_at": str(digest.get("created_at", "")),
    }
