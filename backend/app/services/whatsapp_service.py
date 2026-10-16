"""
WhatsApp Business Cloud API integration for TechPulse AI.

Uses only the official Meta WhatsApp Business Platform (Cloud API).
DRY_RUN mode is the safe default — no messages are sent unless
WHATSAPP_DRY_RUN=false is explicitly set in the environment.

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.config.settings import settings
from app.database.repository import log_whatsapp_delivery, mark_digest_sent
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_GRAPH_BASE = "https://graph.facebook.com"
_MAX_MESSAGE_LENGTH = 4096  # WhatsApp Business API text message limit


# ── Message formatting ────────────────────────────────────────────────────────

def format_digest_message(digest: Dict[str, Any]) -> str:
    """
    Build the human-readable WhatsApp digest text for a given digest document.
    Stays within WhatsApp's message-length constraints.
    """
    date_str = digest.get("date", "Today")
    articles: List[Dict[str, Any]] = digest.get("articles", [])

    lines = [
        f"🚀 *TechPulse AI — Daily Digest*",
        f"📅 {date_str}",
        f"📰 Top {len(articles)} Technology Stories\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for art in articles:
        rank = art.get("rank", "?")
        title = art.get("title", "No title")[:120]
        source = art.get("source", "Unknown")
        category = art.get("category", "")
        importance = art.get("importance", "")
        sentiment = art.get("sentiment", "")
        score = art.get("score")
        link = art.get("link", "")

        # Short summary — truncate to avoid blowing the message limit
        summary = (art.get("summary") or "")[:200].strip()
        if summary:
            # Take only the first two sentences
            sentences = summary.split(". ")
            summary = ". ".join(sentences[:2]).strip()
            if not summary.endswith("."):
                summary += "."

        score_str = f" | ⭐ {score:.0f}" if score is not None else ""
        sentiment_emoji = {"Positive": "📈", "Negative": "📉", "Neutral": "➡️"}.get(sentiment, "")
        importance_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(importance, "")

        block = [
            f"*{rank}. {title}*",
            f"📂 {category}  |  📰 {source}{score_str}  {importance_emoji}{sentiment_emoji}",
        ]
        if summary:
            block.append(summary)
        if link:
            block.append(f"🔗 {link}")
        block.append("")  # blank line separator

        lines.extend(block)

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Powered by TechPulse AI_")

    message = "\n".join(lines)

    # If message exceeds limit, truncate article list and add a note
    if len(message) > _MAX_MESSAGE_LENGTH:
        message = message[: _MAX_MESSAGE_LENGTH - 60]
        message += "\n\n_[Message truncated — see full digest online]_"

    return message


# ── Sending ────────────────────────────────────────────────────────────────────

def send_digest(
    digest: Dict[str, Any],
    recipient_numbers: List[str],
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Send a daily digest to a list of WhatsApp numbers.

    Parameters
    ----------
    digest : dict
        Digest document as stored in MongoDB.
    recipient_numbers : list[str]
        E.164 format phone numbers, e.g. ["919876543210"].
    dry_run : bool or None
        If None, uses WHATSAPP_DRY_RUN setting.
        If True, formats message and logs it without sending.

    Returns
    -------
    dict with keys: success, sent, failed, dry_run, message_preview
    """
    effective_dry_run = settings.WHATSAPP_DRY_RUN if dry_run is None else dry_run

    message_text = format_digest_message(digest)
    date_str = digest.get("date", "unknown")

    result: Dict[str, Any] = {
        "success": False,
        "sent": 0,
        "failed": 0,
        "dry_run": effective_dry_run,
        "date": date_str,
        "message_preview": message_text[:200] + "...",
        "errors": [],
    }

    if effective_dry_run:
        logger.info("=== WhatsApp DRY RUN for %s ===", date_str)
        logger.info("Message preview (%d chars):\n%s", len(message_text), message_text[:500])
        logger.info("Would send to %d recipient(s)", len(recipient_numbers))
        result["success"] = True
        result["sent"] = len(recipient_numbers)
        return result

    # ── Credential validation ─────────────────────────────────────────────────
    if not settings.WHATSAPP_ACCESS_TOKEN:
        msg = "WHATSAPP_ACCESS_TOKEN is not configured. Cannot send."
        logger.error(msg)
        result["errors"].append(msg)
        return result

    if not settings.WHATSAPP_PHONE_NUMBER_ID:
        msg = "WHATSAPP_PHONE_NUMBER_ID is not configured. Cannot send."
        logger.error(msg)
        result["errors"].append(msg)
        return result

    if not recipient_numbers:
        msg = "No recipient numbers provided."
        logger.warning(msg)
        result["errors"].append(msg)
        return result

    # ── Send to each recipient ────────────────────────────────────────────────
    url = (
        f"{_GRAPH_BASE}/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    for number in recipient_numbers:
        clean_number = _clean_phone_number(number)
        if not clean_number:
            logger.warning("Invalid phone number format: %s", number)
            result["failed"] += 1
            result["errors"].append(f"Invalid number: {number}")
            continue

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text,
            },
        }

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                resp_data = response.json()

            message_id = (
                resp_data.get("messages", [{}])[0].get("id", "unknown")
            )
            logger.info("WhatsApp sent to %s — message_id: %s", clean_number, message_id)
            result["sent"] += 1

            # Log delivery record
            log_whatsapp_delivery({
                "date": date_str,
                "recipient": clean_number,
                "message_id": message_id,
                "sent_at": datetime.now(timezone.utc),
                "status": "sent",
            })

        except httpx.HTTPStatusError as exc:
            err = f"HTTP {exc.response.status_code} sending to {clean_number}: {exc.response.text[:200]}"
            logger.error(err)
            result["errors"].append(err)
            result["failed"] += 1

        except httpx.TimeoutException:
            err = f"Timeout sending to {clean_number}"
            logger.error(err)
            result["errors"].append(err)
            result["failed"] += 1

        except Exception as exc:
            err = f"{type(exc).__name__} sending to {clean_number}: {exc}"
            logger.error(err)
            result["errors"].append(err)
            result["failed"] += 1

    result["success"] = result["sent"] > 0

    if result["success"]:
        mark_digest_sent(date_str)

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_phone_number(number: str) -> Optional[str]:
    """
    Normalise a phone number to E.164 format (digits only, no +).
    Returns None if the number is clearly invalid.
    """
    digits = "".join(c for c in str(number) if c.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        return None
    return digits
