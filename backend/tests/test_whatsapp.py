"""
Tests for WhatsApp service.
No real messages are sent — DRY_RUN is enforced.
"""

import pytest
from unittest.mock import patch, MagicMock


# ── Message formatting ────────────────────────────────────────────────────────

def test_format_digest_message_basic():
    from app.services.whatsapp_service import format_digest_message

    digest = {
        "date": "2026-10-12",
        "articles": [
            {
                "rank": 1,
                "title": "OpenAI GPT-5 Launch",
                "source": "TechCrunch",
                "category": "AI",
                "score": 92.0,
                "sentiment": "Positive",
                "importance": "High",
                "summary": "OpenAI has launched GPT-5 with improved reasoning capabilities.",
                "link": "https://example.com/gpt5",
            }
        ]
    }

    msg = format_digest_message(digest)
    assert "TechPulse AI" in msg
    assert "2026-10-12" in msg
    assert "OpenAI GPT-5 Launch" in msg
    assert "TechCrunch" in msg
    assert "https://example.com/gpt5" in msg


def test_format_digest_message_stays_within_limit():
    from app.services.whatsapp_service import format_digest_message, _MAX_MESSAGE_LENGTH

    articles = [
        {
            "rank": i,
            "title": f"Very long article title about technology number {i} " * 5,
            "source": "Source",
            "category": "AI",
            "score": 80.0,
            "sentiment": "Neutral",
            "importance": "Medium",
            "summary": "Long summary " * 30,
            "link": f"https://example.com/{i}",
        }
        for i in range(10)
    ]
    digest = {"date": "2026-10-12", "articles": articles}
    msg = format_digest_message(digest)
    assert len(msg) <= _MAX_MESSAGE_LENGTH


def test_format_digest_empty_articles():
    from app.services.whatsapp_service import format_digest_message

    digest = {"date": "2026-10-12", "articles": []}
    msg = format_digest_message(digest)
    assert "TechPulse AI" in msg


# ── Dry-run mode ──────────────────────────────────────────────────────────────

def test_send_digest_dry_run():
    from app.services.whatsapp_service import send_digest

    digest = {
        "date": "2026-10-12",
        "articles": [
            {
                "rank": 1, "title": "Test", "source": "Src",
                "category": "AI", "score": 80.0, "sentiment": "Positive",
                "importance": "High", "summary": "Test summary.", "link": "https://example.com"
            }
        ]
    }

    result = send_digest(digest, ["919876543210"], dry_run=True)
    assert result["dry_run"] is True
    assert result["success"] is True
    assert result["sent"] == 1  # dry-run counts recipients as "sent"


def test_send_digest_missing_token():
    """Without a token, send should fail cleanly (not raise an exception)."""
    from app.services.whatsapp_service import send_digest

    with patch("app.services.whatsapp_service.settings") as mock_settings:
        mock_settings.WHATSAPP_DRY_RUN = False
        mock_settings.WHATSAPP_ACCESS_TOKEN = ""
        mock_settings.WHATSAPP_PHONE_NUMBER_ID = ""

        digest = {"date": "2026-10-12", "articles": []}
        result = send_digest(digest, ["919876543210"], dry_run=False)

    assert result["success"] is False
    assert len(result["errors"]) > 0


def test_send_digest_no_recipients_dry_run():
    """No recipients in dry-run should still succeed."""
    from app.services.whatsapp_service import send_digest

    digest = {"date": "2026-10-12", "articles": []}
    result = send_digest(digest, [], dry_run=True)
    assert result["success"] is True


# ── Phone number cleaning ─────────────────────────────────────────────────────

def test_clean_phone_valid():
    from app.services.whatsapp_service import _clean_phone_number

    assert _clean_phone_number("919876543210") == "919876543210"
    assert _clean_phone_number("+919876543210") == "919876543210"
    assert _clean_phone_number("91 98765 43210") == "919876543210"


def test_clean_phone_too_short():
    from app.services.whatsapp_service import _clean_phone_number

    assert _clean_phone_number("123") is None


def test_clean_phone_too_long():
    from app.services.whatsapp_service import _clean_phone_number

    assert _clean_phone_number("1" * 20) is None
