"""
News API routes — fetch, search, filter, trending, and article detail.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.database.repository import (
    count_articles,
    get_articles,
    get_top_articles,
)
from app.models.schemas import PaginatedNewsResponse
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/news", tags=["News"])


@router.get("", response_model=PaginatedNewsResponse)
def get_news(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search keyword"),
    sort_by: str = Query("score", description="Sort field: 'score' or 'date'"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
):
    """
    Return paginated news articles with optional category and search filters.
    Articles are sorted by composite score (descending) by default.
    """
    try:
        skip = (page - 1) * page_size
        total = count_articles(category=category, search=search)
        articles = get_articles(
            category=category,
            search=search,
            sort_by=sort_by,
            skip=skip,
            limit=page_size,
        )
        pages = max(1, math.ceil(total / page_size))
        return PaginatedNewsResponse(
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            data=articles,
        )
    except Exception as exc:
        logger.error("get_news failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch news articles.")


@router.get("/trending")
def get_trending(
    limit: int = Query(10, ge=1, le=50, description="Number of trending articles"),
):
    """Return the top-scored articles — the trending feed."""
    try:
        articles = get_top_articles(limit=limit)
        return {"success": True, "count": len(articles), "data": articles}
    except Exception as exc:
        logger.error("get_trending failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch trending articles.")
