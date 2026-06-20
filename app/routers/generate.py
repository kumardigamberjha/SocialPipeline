import logging
import time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.config import Settings, get_settings
from app.crew import run_pipeline, run_blog_pipeline
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    BlogGenerateRequest,
    BlogGenerateResponse,
    BlogPostOut,
    BlogPostSummary,
)
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


# ── Long-Form Blog Endpoints ─────────────────────────────────────────────────


def _run_blog_job(topic: str, provider: str, run_id: str, user_id: str, niche: str) -> None:
    """Background worker for blog generation (runs after the HTTP response).

    FastAPI executes sync background tasks in its threadpool, so the long
    ~20k-word generation never blocks the request. Failures are logged and the
    run is marked failed inside run_blog_pipeline.
    """
    settings = get_settings()
    try:
        run_blog_pipeline(
            topic=topic,
            settings=settings,
            provider=provider,
            run_id=run_id,
            user_id=user_id,
            niche=niche,
        )
    except Exception:  # already logged + run marked failed inside the pipeline
        logger.exception("Background blog job failed for run_id=%s", run_id)


@router.post(
    "/blog/generate",
    response_model=BlogGenerateResponse,
    status_code=202,
    summary="Generate a long-form (~20,000 word) technical blog post",
    description=(
        "Creates a run, dispatches blog generation to a background task, and "
        "returns the run_id immediately. Stream progress via "
        "/api/ws/blog/{client_id} or poll GET /api/blog/posts."
    ),
)
async def generate_blog(
    body: BlogGenerateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(get_current_user),
) -> BlogGenerateResponse:
    user_id = user["id"]

    queries.reset_usage_if_expired(user_id)
    usage = queries.get_usage(user_id)
    if usage and usage["runs_this_month"] >= usage["max_runs_per_month"]:
        raise HTTPException(status_code=429, detail="Usage limit exceeded for this billing period.")

    provider = body.provider or settings.default_provider
    run = queries.create_run(user_id, body.topic, provider)
    run_id = run["id"]

    logger.info("POST /api/blog/generate ▸ topic=%r provider=%s run_id=%s", body.topic, provider, run_id)

    background_tasks.add_task(_run_blog_job, body.topic, provider, run_id, user_id, body.niche)

    return BlogGenerateResponse(
        status="queued",
        run_id=run_id,
        topic=body.topic,
        provider=provider,
    )


@router.get(
    "/blog/posts",
    response_model=list[BlogPostSummary],
    summary="List the current user's blog posts (newest first)",
)
async def list_blog_posts(
    limit: int = 20,
    user: dict = Depends(get_current_user),
) -> list[BlogPostSummary]:
    posts = queries.get_blog_posts(user["id"], limit=limit)
    return [BlogPostSummary(**post) for post in posts]


@router.get(
    "/blog/posts/{blog_id}",
    response_model=BlogPostOut,
    summary="Get a single blog post with full markdown content",
)
async def get_blog_post(
    blog_id: str,
    user: dict = Depends(get_current_user),
) -> BlogPostOut:
    post = queries.get_blog_by_id(blog_id, user["id"])
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return BlogPostOut(**post)


@router.delete(
    "/blog/posts/{blog_id}",
    summary="Soft-delete one of the current user's blog posts",
)
async def delete_blog_post(
    blog_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    deleted = queries.soft_delete_blog(blog_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"status": "deleted", "id": blog_id}


@router.get(
    "/blog/{slug}",
    response_model=BlogPostOut,
    summary="Public: get a published blog post by slug (no auth)",
)
async def get_public_blog(slug: str) -> BlogPostOut:
    post = queries.get_blog_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return BlogPostOut(**post)
