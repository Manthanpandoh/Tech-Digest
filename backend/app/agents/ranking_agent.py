"""
Ranking Agent for TechPulse AI.

Calculates a composite score for every cleaned article and updates
the 'score' field in MongoDB. Safe to re-run — scores are updated
in place (idempotent).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from pymongo.errors import PyMongoError

from app.database.connection import get_database
from app.config.settings import settings
from app.utils.logging_config import get_logger
from app.utils.ranking_utils import calculate_score

logger = get_logger(__name__)


def run_ranking() -> Dict[str, Any]:
    """
    Score all articles that have been cleaned but not yet ranked.
    Also re-scores ranked articles so ai_score changes propagate.

    Returns:
        {
            "processed": int,
            "ranked": int,
            "errors": int
        }
    """
    logger.info("=== Ranking Agent started ===")

    stats: Dict[str, Any] = {"processed": 0, "ranked": 0, "errors": 0}

    db = get_database()
    collection = db[settings.ARTICLES_COLLECTION]

    # Process cleaned and already-ranked articles (scores may need refresh
    # after AI analysis adds ai_score)
    cursor = collection.find({"status": {"$in": ["cleaned", "ranked", "analyzed"]}})

    for article in cursor:
        stats["processed"] += 1
        try:
            score = calculate_score(article)
            collection.update_one(
                {"_id": article["_id"]},
                {
                    "$set": {
                        "score": score,
                        "status": "ranked",
                        "ranked_at": datetime.now(timezone.utc),
                    }
                },
            )
            stats["ranked"] += 1
        except PyMongoError as exc:
            logger.error("DB error ranking article %s: %s", article.get("_id"), exc)
            stats["errors"] += 1
        except Exception as exc:
            logger.error("Error ranking article %s: %s", article.get("_id"), type(exc).__name__)
            stats["errors"] += 1

    logger.info(
        "=== Ranking done: %d ranked, %d errors ===",
        stats["ranked"],
        stats["errors"],
    )
    return stats
