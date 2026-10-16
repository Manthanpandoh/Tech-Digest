"""
Central application settings loaded from environment variables.
All secrets and tuneable parameters live here — never hardcoded.
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "TechPulse AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── MongoDB ───────────────────────────────────────────────────────────────
    MONGODB_URI: str = Field(..., description="MongoDB Atlas connection URI")
    DATABASE_NAME: str = Field(default="techpulse_ai")
    USE_MOCK_DB: bool = Field(default=False, description="Enable in-memory database mock for local testing")

    # Collection names
    ARTICLES_COLLECTION: str = "articles"
    DIGESTS_COLLECTION: str = "digests"
    JOB_HISTORY_COLLECTION: str = "job_history"
    WHATSAPP_LOG_COLLECTION: str = "whatsapp_log"

    # ── OpenRouter / LLM ─────────────────────────────────────────────────────
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL_NAME: str = "google/gemini-2.5-flash"
    LLM_TEMPERATURE_SUMMARY: float = 0.4
    LLM_TEMPERATURE_ANALYSIS: float = 0.2
    LLM_MAX_TOKENS_SUMMARY: int = 700
    LLM_MAX_TOKENS_ANALYSIS: int = 500
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_WAIT_SECONDS: float = 5.0

    # ── WhatsApp Business API ─────────────────────────────────────────────────
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_TEMPLATE_NAME: str = "techpulse_digest"
    WHATSAPP_API_VERSION: str = "v22.0"
    WHATSAPP_DRY_RUN: bool = True  # Safe default — never send without explicit opt-in

    # ── CORS ─────────────────────────────────────────────────────────────────
    FRONTEND_ORIGIN: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # ── Admin security ───────────────────────────────────────────────────────
    ADMIN_API_KEY: str = Field(default="change-me-in-production")

    # ── Timezone & scheduling ────────────────────────────────────────────────
    TIMEZONE: str = "Asia/Kolkata"
    # Cron schedules in UTC (IST = UTC+5:30)
    # 4:00 AM IST = 22:30 UTC previous day
    COLLECTION_CRON: str = "30 22 * * *"
    # 6:00 AM IST = 00:30 UTC
    DIGEST_SEND_CRON: str = "30 0 * * *"

    # ── Pipeline limits ──────────────────────────────────────────────────────
    MAX_ARTICLES_PER_FEED: int = 20
    MAX_ARTICLES_TO_ANALYZE: int = 50
    TOP_ARTICLES_FOR_DIGEST: int = 10
    RSS_FEED_TIMEOUT_SECONDS: int = 15

    # ── RSS Feed configuration ────────────────────────────────────────────────
    # Loaded as a list of dicts; overrideable via JSON env var if needed
    @property
    def RSS_FEEDS(self) -> List[dict]:
        return [
            {
                "name": "Google AI Blog",
                "category": "Artificial Intelligence",
                "url": "https://news.google.com/rss/search?q=Artificial+Intelligence+technology&hl=en-IN&gl=IN&ceid=IN:en",
            },
            {
                "name": "Google Machine Learning",
                "category": "Machine Learning",
                "url": "https://news.google.com/rss/search?q=Machine+Learning&hl=en-IN&gl=IN&ceid=IN:en",
            },
            {
                "name": "Google Data Science",
                "category": "Data Science",
                "url": "https://news.google.com/rss/search?q=Data+Science&hl=en-IN&gl=IN&ceid=IN:en",
            },
            {
                "name": "Google Cybersecurity",
                "category": "Cybersecurity",
                "url": "https://news.google.com/rss/search?q=Cybersecurity&hl=en-IN&gl=IN&ceid=IN:en",
            },
            {
                "name": "Google Cloud Computing",
                "category": "Cloud Computing",
                "url": "https://news.google.com/rss/search?q=Cloud+Computing&hl=en-IN&gl=IN&ceid=IN:en",
            },
            {
                "name": "TechCrunch",
                "category": "Technology",
                "url": "https://techcrunch.com/feed/",
            },
            {
                "name": "The Verge",
                "category": "Technology",
                "url": "https://www.theverge.com/rss/index.xml",
            },
            {
                "name": "Wired Technology",
                "category": "Technology",
                "url": "https://www.wired.com/feed/rss",
            },
            {
                "name": "Ars Technica",
                "category": "Technology",
                "url": "https://feeds.arstechnica.com/arstechnica/index",
            },
            {
                "name": "MIT Technology Review",
                "category": "Technology",
                "url": "https://www.technologyreview.com/feed/",
            },
        ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


# Singleton instance — import this throughout the app
settings = Settings()
