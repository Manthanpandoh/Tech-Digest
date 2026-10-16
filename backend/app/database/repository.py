"""
MongoDB repository layer.
All database read/write operations go through these functions.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config.settings import settings
from app.database.connection import get_database
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


# ── Collection helpers ────────────────────────────────────────────────────────

def _articles() -> Collection:
    return get_database()[settings.ARTICLES_COLLECTION]


def _digests() -> Collection:
    return get_database()[settings.DIGESTS_COLLECTION]


def _job_history() -> Collection:
    return get_database()[settings.JOB_HISTORY_COLLECTION]


def _whatsapp_log() -> Collection:
    return get_database()[settings.WHATSAPP_LOG_COLLECTION]


# ── Index initialisation ──────────────────────────────────────────────────────

def ensure_indexes() -> None:
    """Create required MongoDB indexes. Safe to call on every startup."""
    try:
        _articles().create_index([("link", ASCENDING)], unique=True, name="link_unique")
        _articles().create_index([("canonical_link", ASCENDING)], sparse=True, name="canonical_link_sparse")
        _articles().create_index([("score", DESCENDING)], name="score_desc")
        _articles().create_index([("created_at", DESCENDING)], name="created_at_desc")
        _articles().create_index([("category", ASCENDING)], name="category_asc")
        _articles().create_index([("status", ASCENDING)], name="status_asc")
        _digests().create_index([("date", ASCENDING)], unique=True, name="date_unique")
        _job_history().create_index([("started_at", DESCENDING)], name="started_at_desc")
        logger.info("MongoDB indexes verified")
    except PyMongoError as exc:
        logger.error("Index creation error: %s", exc)


# ── Article operations ────────────────────────────────────────────────────────

def article_exists(link: str) -> bool:
    canonical = link
    return _articles().find_one(
        {"$or": [{"link": link}, {"canonical_link": canonical}]},
        {"_id": 1},
    ) is not None


def upsert_article(article: Dict[str, Any]) -> bool:
    """
    Insert article if link is new; skip if it already exists (by link or canonical_link).
    Returns True when a new article was inserted.
    """
    try:
        canonical = article.get("canonical_link") or article.get("link")
        # Check if article already exists under either the raw or canonical link
        existing = _articles().find_one(
            {"$or": [{"link": article["link"]}, {"canonical_link": canonical}]},
            {"_id": 1},
        )
        if existing:
            return False

        result = _articles().update_one(
            {"link": article["link"]},
            {"$setOnInsert": article},
            upsert=True,
        )
        return result.upserted_id is not None
    except DuplicateKeyError:
        return False
    except PyMongoError as exc:
        logger.error("upsert_article failed: %s", exc)
        return False


def update_article(article_id, fields: Dict[str, Any]) -> bool:
    try:
        result = _articles().update_one(
            {"_id": article_id},
            {"$set": fields},
        )
        return result.modified_count > 0
    except PyMongoError as exc:
        logger.error("update_article failed: %s", exc)
        return False


def get_articles(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "score",
    skip: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Fetch articles with optional filtering, search and pagination."""
    query: Dict[str, Any] = {}

    if category and category != "All":
        # Case-insensitive category match
        query["category"] = {"$regex": re.escape(category), "$options": "i"}

    if status:
        query["status"] = status

    if search:
        escaped = re.escape(search)
        query["$or"] = [
            {"title": {"$regex": escaped, "$options": "i"}},
            {"clean_title": {"$regex": escaped, "$options": "i"}},
            {"source": {"$regex": escaped, "$options": "i"}},
            {"category": {"$regex": escaped, "$options": "i"}},
        ]

    sort_field = "score" if sort_by == "score" else "created_at"

    cursor = (
        _articles()
        .find(query, {"_id": 0})
        .sort(sort_field, DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return list(cursor)


def count_articles(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    query: Dict[str, Any] = {}
    if category and category != "All":
        query["category"] = {"$regex": re.escape(category), "$options": "i"}
    if status:
        query["status"] = status
    if search:
        escaped = re.escape(search)
        query["$or"] = [
            {"title": {"$regex": escaped, "$options": "i"}},
            {"clean_title": {"$regex": escaped, "$options": "i"}},
        ]
    return _articles().count_documents(query)


def get_top_articles(limit: int = 10) -> List[Dict[str, Any]]:
    return list(
        _articles()
        .find({}, {"_id": 0})
        .sort("score", DESCENDING)
        .limit(limit)
    )


def get_unanalyzed_articles(limit: int = 50) -> List[Dict[str, Any]]:
    return list(
        _articles()
        .find({"ai_score": {"$exists": False}}, {"_id": 1, "title": 1, "description": 1, "link": 1, "category": 1})
        .sort("score", DESCENDING)
        .limit(limit)
    )


def get_articles_for_digest(limit: int = 10) -> List[Dict[str, Any]]:
    return list(
        _articles()
        .find({"score": {"$exists": True}}, {"_id": 0})
        .sort("score", DESCENDING)
        .limit(limit)
    )


# ── Digest operations ─────────────────────────────────────────────────────────

def get_digest(date_str: str) -> Optional[Dict[str, Any]]:
    return _digests().find_one({"date": date_str}, {"_id": 0})


def save_digest(digest: Dict[str, Any]) -> bool:
    """Upsert digest by date — safe to call multiple times."""
    try:
        _digests().update_one(
            {"date": digest["date"]},
            {"$set": digest},
            upsert=True,
        )
        return True
    except PyMongoError as exc:
        logger.error("save_digest failed: %s", exc)
        return False


def mark_digest_sent(date_str: str) -> bool:
    try:
        _digests().update_one(
            {"date": date_str},
            {"$set": {
                "whatsapp_sent": True,
                "whatsapp_sent_at": datetime.now(timezone.utc),
            }},
        )
        return True
    except PyMongoError as exc:
        logger.error("mark_digest_sent failed: %s", exc)
        return False


# ── Job history ───────────────────────────────────────────────────────────────

def save_job_result(job: Dict[str, Any]) -> None:
    try:
        _job_history().insert_one(job)
    except PyMongoError as exc:
        logger.error("save_job_result failed: %s", exc)


def get_latest_job(job_name: str) -> Optional[Dict[str, Any]]:
    return _job_history().find_one(
        {"job_name": job_name},
        {"_id": 0},
        sort=[("started_at", DESCENDING)],
    )


# ── WhatsApp delivery log ─────────────────────────────────────────────────────

def log_whatsapp_delivery(record: Dict[str, Any]) -> None:
    try:
        _whatsapp_log().insert_one(record)
    except PyMongoError as exc:
        logger.error("log_whatsapp_delivery failed: %s", exc)
