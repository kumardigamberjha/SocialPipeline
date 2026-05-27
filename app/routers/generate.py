import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.crew import run_pipeline
from app.schemas import GenerateRequest, GenerateResponse
from app.core.auth_deps import get_current_user
from app.db import queries

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
    user: dict = Depends(get_current_user)
) -> GenerateResponse:
    try:
        logger.info("POST /api/generate  ▸ topic=%r  provider=%s", body.topic, body.provider)

        user_id = user['id']
        queries.reset_usage_if_expired(user_id)
        usage = queries.get_usage(user_id)
        if usage and usage['runs_this_month'] >= usage['max_runs_per_month']:
            raise HTTPException(status_code=429, detail="Usage limit exceeded for this billing period.")

        provider = body.provider or settings.default_provider
        run = queries.create_run(user_id, body.topic, provider)
        run_id = run['id']
        queries.update_run_status(run_id, 'running')
        
        start = time.time()
        
        result = run_pipeline(
            topic=body.topic,
            settings=settings,
            provider=body.provider,
        )

        duration = time.time() - start
        queries.update_run_status(run_id, 'completed', final_result=result.output, duration=duration)
        queries.increment_usage(user_id)

        return GenerateResponse(
            status="success",
            topic=body.topic,
            provider_used=result.provider_used,
            duration_seconds=result.duration_seconds,
            result=result.output,
        )

    except RuntimeError as exc:
        logger.error("Pipeline runtime error: %s", exc)
        if 'run_id' in locals():
            queries.update_run_status(run_id, 'failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in /api/generate")
        if 'run_id' in locals():
            queries.update_run_status(run_id, 'failed')
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {type(exc).__name__}",
        ) from exc
