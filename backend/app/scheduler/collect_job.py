"""
Cron Job 1: Daily Collection and Digest Generation
Schedule: 4:00 AM IST = 22:30 UTC (previous day)
Cron expression (UTC): 30 22 * * *

Run manually for testing:
    cd backend
    python -m app.scheduler.collect_job

This script is designed to be run as a Render Cron Job.
It EXITS when complete (does not start a server loop).
"""

import sys
import json
from datetime import datetime, timezone

# Ensure the backend directory is on the path when run directly
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

from app.database.connection import test_connection, close_connection
from app.database.repository import ensure_indexes
from app.workflows.pipeline import run_daily_pipeline
from app.utils.logging_config import get_logger

logger = get_logger("collect_job")


def main() -> int:
    """
    Entry point. Returns exit code:
        0 = success
        1 = failure
    """
    logger.info("Collect & Digest Job starting — %s UTC",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    # Verify database is reachable before starting
    if not test_connection():
        logger.error("MongoDB connection failed. Aborting job.")
        return 1

    ensure_indexes()

    force = os.getenv("FORCE_REBUILD", "").lower() in ("true", "1") or "--force" in sys.argv
    result = run_daily_pipeline(force=force)

    logger.info("Job result:\n%s", json.dumps(
        {k: str(v) if not isinstance(v, (int, float, bool, list, str, type(None))) else v
         for k, v in result.items()},
        indent=2
    ))

    close_connection()

    if result.get("success"):
        logger.info("Collect & Digest Job completed successfully.")
        return 0
    else:
        logger.error("Collect & Digest Job finished with failures: %s", result.get("errors"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
