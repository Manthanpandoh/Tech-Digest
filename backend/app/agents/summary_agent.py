"""
Summary and Analysis Agent for TechPulse AI.

Runs AI analysis and summary generation on ranked articles,
then stores results back in MongoDB. Skips articles that already
have analysis to avoid duplicate LLM calls and unnecessary cost.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List

from pymongo.errors import PyMongoError

from app.database.connection import get_database
from app.config.settings import settings
from app.services.ai_service import analyze_and_summarize_safe
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_MAX_ANALYSIS_WORKERS = 2


def _analyze_single_article(article: Dict[str, Any], collection, stats: Dict[str, Any], lock: threading.Lock) -> None:
    article_id = article["_id"]
    title = article.get("clean_title") or article.get("title") or ""
    content = article.get("description") or ""

    try:
        analysis = analyze_and_summarize_safe(title, content)

        if analysis.get("analysis_error"):
            with lock:
                stats["skipped_error"] += 1
            logger.warning("Analysis unavailable for: %s", title[:60])
            collection.update_one(
                {"_id": article_id},
                {
                    "$set": {
                        "status": "analyzed",
                        "analyzed_at": datetime.now(timezone.utc),
                        "analysis_error": True,
                    }
                },
            )
            return

        collection.update_one(
            {"_id": article_id},
            {
                "$set": {
                    "ai_score": analysis["ai_score"],
                    "ai_category": analysis["category"],
                    "sentiment": analysis["sentiment"],
                    "importance": analysis["importance"],
                    "key_insights": analysis["key_insights"],
                    "summary": analysis.get("summary", ""),
                    "status": "analyzed",
                    "analyzed_at": datetime.now(timezone.utc),
                }
            },
        )
        with lock:
            stats["analyzed"] += 1
        logger.debug("Analyzed & summarized: %s", title[:60])

    except PyMongoError as exc:
        logger.error("DB error for article %s: %s", article_id, exc)
        with lock:
            stats["errors"] += 1
    except Exception as exc:
        logger.error("Unexpected error for article %s: %s", article_id, type(exc).__name__)
        with lock:
            stats["errors"] += 1


def run_analysis() -> Dict[str, Any]:
    """
    Analyse up to MAX_ARTICLES_TO_ANALYZE ranked articles that haven't
    been AI-analysed yet using a bounded concurrent thread pool.

    Returns:
        {
            "processed": int,
            "analyzed": int,
            "skipped_error": int,
            "errors": int
        }
    """
    logger.info("=== Summary/Analysis Agent started ===")

    stats: Dict[str, Any] = {
        "processed": 0,
        "analyzed": 0,
        "skipped_error": 0,
        "errors": 0,
    }

    db = get_database()
    collection = db[settings.ARTICLES_COLLECTION]

    # Only analyse articles that don't yet have an ai_score
    cursor = (
        collection
        .find(
            {"status": "ranked", "ai_score": {"$exists": False}},
            {"_id": 1, "title": 1, "clean_title": 1, "description": 1, "link": 1},
        )
        .limit(settings.MAX_ARTICLES_TO_ANALYZE)
    )

    articles = list(cursor)
    stats["processed"] = len(articles)

    if not articles:
        logger.info("=== Analysis done: 0 articles to analyze ===")
        return stats

    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=_MAX_ANALYSIS_WORKERS) as executor:
        futures = [
            executor.submit(_analyze_single_article, article, collection, stats, lock)
            for article in articles
        ]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                logger.error("Worker raised exception: %s", exc)
                with lock:
                    stats["errors"] += 1

    logger.info(
        "=== Analysis done: %d analyzed, %d errors ===",
        stats["analyzed"],
        stats["errors"],
    )
    return stats

