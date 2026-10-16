"""
AI Analysis endpoint.
"""

from fastapi import APIRouter, HTTPException

from app.models.schemas import AnalysisRequest, AnalysisResponse, AnalysisResult
from app.services.ai_service import analyze_article
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["AI Analysis"])


@router.post("/analysis", response_model=AnalysisResponse)
def analyze_article_endpoint(request: AnalysisRequest):
    """
    Analyse a news article using AI.
    Returns category, sentiment, importance score, and key insights.
    """
    try:
        result = analyze_article(request.title, request.content)
        analysis = AnalysisResult(**result)
        return AnalysisResponse(
            success=True,
            title=request.title,
            analysis=analysis,
        )
    except Exception as exc:
        logger.error("Analysis endpoint failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="AI analysis failed. Please try again later.",
        )
