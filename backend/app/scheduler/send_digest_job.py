"""
Cron Job 2: WhatsApp Digest Delivery
Schedule: 6:00 AM IST = 00:30 UTC
Cron expression (UTC): 30 0 * * *

Run manually in dry-run mode (no actual message sent):
    cd backend
    python -m app.scheduler.send_digest_job

Run manually with live sending (requires configured credentials):
    WHATSAPP_DRY_RUN=false python -m app.scheduler.send_digest_job

This script is designed to be run as a Render Cron Job.
It fetches the digest that was already built by collect_job,
then sends it via WhatsApp. It does NOT re-run the collection pipeline.
"""

import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

import pytz

from app.config.settings import settings
from app.database.connection import test_connection, close_connection
from app.database.repository import get_digest
from app.services.whatsapp_service import send_digest
from app.utils.logging_config import get_logger

logger = get_logger("send_digest_job")

_IST = pytz.timezone(settings.TIMEZONE)

# ── Recipient list ────────────────────────────────────────────────────────────
# Configure via the WHATSAPP_RECIPIENTS environment variable as a
# comma-separated list of E.164 numbers (without +), e.g.:
#   WHATSAPP_RECIPIENTS=919876543210,918765432109
# If not set, falls back to this empty list (safe default — no messages sent).

def _get_recipients():
    raw = os.getenv("WHATSAPP_RECIPIENTS", "")
    return [n.strip() for n in raw.split(",") if n.strip()]


def main() -> int:
    logger.info("WhatsApp Digest Job starting — %s UTC",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

    if not test_connection():
        logger.error("MongoDB connection failed. Aborting job.")
        return 1

    # Get today's India-local date
    date_str = datetime.now(_IST).strftime("%Y-%m-%d")
    logger.info("Looking for digest date: %s", date_str)

    digest = get_digest(date_str)

    if not digest:
        logger.error(
            "No digest found for %s. Run collect_job first. Aborting.", date_str
        )
        close_connection()
        return 1

    if digest.get("whatsapp_sent") and not settings.WHATSAPP_DRY_RUN:
        logger.info("Digest for %s was already sent. Skipping to prevent duplicate.", date_str)
        close_connection()
        return 0

    recipients = _get_recipients()
    if not recipients:
        logger.warning(
            "No recipients configured (WHATSAPP_RECIPIENTS is empty). "
            "Running in dry-run mode to preview message."
        )
        # Force dry-run preview so the job is still useful even without recipients
        result = send_digest(digest, [], dry_run=True)
    else:
        result = send_digest(digest, recipients)

    logger.info("Send result:\n%s", json.dumps(result, indent=2, default=str))

    close_connection()

    if result.get("success"):
        logger.info("WhatsApp Digest Job completed successfully.")
        return 0
    else:
        logger.error("WhatsApp Digest Job finished with errors: %s", result.get("errors"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
