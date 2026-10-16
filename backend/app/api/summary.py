"""
AI Summary endpoint.
"""

from fastapi import APIRouter, HTTPException

from app.models.schemas import SummaryRequest, SummaryResponse
from app.services.ai_service import generate_article_summary
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["AI Summary"])


@router.post("/summary", response_model=SummaryResponse)
def create_summary(request: SummaryRequest):
    """Generate an AI-powered structured summary for a news article."""
    try:
        summary = generate_article_summary(request.title, request.content)
        return SummaryResponse(success=True, title=request.title, summary=summary)
    except Exception as exc:
        logger.error("Summary generation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="AI summary generation failed. Please try again later.",
        )
