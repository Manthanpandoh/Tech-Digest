"""
Pydantic schemas for request validation, response serialisation,
and internal data structures throughout TechPulse AI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ── Shared helpers ────────────────────────────────────────────────────────────

class OKResponse(BaseModel):
    success: bool = True
    message: str = "OK"


# ── Article ───────────────────────────────────────────────────────────────────

class ArticleBase(BaseModel):
    title: str
    link: str
    source: str
    category: str


class ArticleInDB(ArticleBase):
    """Shape of an article document as stored in MongoDB."""
    published: Optional[str] = None
    published_dt: Optional[datetime] = None
    clean_title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    score: Optional[float] = None
    status: str = "raw"
    # AI analysis fields
    ai_score: Optional[int] = None
    ai_category: Optional[str] = None
    sentiment: Optional[str] = None
    importance: Optional[str] = None
    key_insights: Optional[List[str]] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    analyzed_at: Optional[datetime] = None


class ArticleResponse(BaseModel):
    """Public article shape returned by the API (no internal _id)."""
    title: str
    link: str
    source: str
    category: str
    published: Optional[str] = None
    clean_title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    score: Optional[float] = None
    status: Optional[str] = None
    ai_score: Optional[int] = None
    ai_category: Optional[str] = None
    sentiment: Optional[str] = None
    importance: Optional[str] = None
    key_insights: Optional[List[str]] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None


class PaginatedNewsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    data: List[Dict[str, Any]]


# ── AI Summary ────────────────────────────────────────────────────────────────

class SummaryRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    content: str = Field(default="", max_length=5000)


class SummaryResponse(BaseModel):
    success: bool = True
    title: str
    summary: str


# ── AI Analysis ───────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    content: str = Field(default="", max_length=5000)


class AnalysisResult(BaseModel):
    ai_score: int = Field(..., ge=0, le=100)
    category: str
    sentiment: str
    importance: str
    key_insights: List[str] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = {"AI", "Cloud", "Cybersecurity", "Programming",
                   "Google", "Microsoft", "Apple", "Other"}
        return v if v in allowed else "Other"

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        allowed = {"Positive", "Negative", "Neutral"}
        return v if v in allowed else "Neutral"

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        allowed = {"Low", "Medium", "High"}
        return v if v in allowed else "Medium"


class AnalysisResponse(BaseModel):
    success: bool = True
    title: str
    analysis: AnalysisResult


# ── Daily Digest ──────────────────────────────────────────────────────────────

class DigestArticle(BaseModel):
    rank: int
    title: str
    source: str
    category: str
    score: Optional[float] = None
    ai_score: Optional[int] = None
    sentiment: Optional[str] = None
    importance: Optional[str] = None
    summary: Optional[str] = None
    link: str


class DigestDocument(BaseModel):
    date: str  # YYYY-MM-DD in Asia/Kolkata
    created_at: datetime
    article_count: int
    articles: List[DigestArticle]
    whatsapp_sent: bool = False
    whatsapp_sent_at: Optional[datetime] = None


class DigestResponse(BaseModel):
    success: bool = True
    date: str
    article_count: int
    articles: List[DigestArticle]
    whatsapp_sent: bool


# ── Job / Pipeline ────────────────────────────────────────────────────────────

class JobResult(BaseModel):
    job_name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    success: bool = False
    collected: int = 0
    cleaned: int = 0
    ranked: int = 0
    analyzed: int = 0
    digest_date: Optional[str] = None
    whatsapp_sent: bool = False
    errors: List[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None


class JobStatusResponse(BaseModel):
    success: bool = True
    job: JobResult


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime
