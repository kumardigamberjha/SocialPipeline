"""
/api/generate – Run the full content-generation pipeline.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.crew import run_pipeline
from app.schemas import GenerateRequest, GenerateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])


@router.post(
    "/generate",
    response_model=GenerateResponse,
    summary="Run the AI content pipeline",
    description="Accepts a topic and runs all 10 agents sequentially to produce multi-platform content.",
)
async def generate_content(
    body: GenerateRequest,
    settings: Settings = Depends(get_settings),
) -> GenerateResponse:
    """Execute the content pipeline synchronously and return results."""
    try:
        logger.info("POST /api/generate  ▸ topic=%r  provider=%s", body.topic, body.provider)

        result = run_pipeline(
            topic=body.topic,
            settings=settings,
            provider=body.provider,
        )

        return GenerateResponse(
            status="success",
            topic=body.topic,
            provider_used=result.provider_used,
            duration_seconds=result.duration_seconds,
            result=result.output,
        )

    except RuntimeError as exc:
        logger.error("Pipeline runtime error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("Unexpected error in /api/generate")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {type(exc).__name__}",
        ) from exc
