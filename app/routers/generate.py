import asyncio
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.db.session import get_session

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
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GenerateResponse:
    try:
        logger.info("POST /api/generate  ▸ topic=%r  provider=%s", body.topic, body.provider)

        if os.getenv("ENABLE_USAGE_LIMITS", "false").lower() in ("true", "1"):
            await queries.reset_usage_if_expired(session, user_id)
            usage = await queries.get_usage(session, user_id)
            if usage and usage.get("max_runs_per_month") and usage["runs_this_month"] >= usage["max_runs_per_month"]:
                raise HTTPException(status_code=429, detail="Usage limit exceeded for this billing period.")

        provider = body.provider or settings.default_provider
        run = await queries.create_run(session, user_id, body.topic, provider)
        run_id = run["id"]
        await queries.update_run_status(session, run_id, user_id, "running")

        start = time.time()

        # run_pipeline is a synchronous multi-minute CrewAI kickoff. Awaited
        # directly it froze the entire event loop — every other request in this
        # worker, including /api/health — for the duration. Phase 4 moves this
        # onto a queue; until then it at least runs off the loop.
        result = await asyncio.to_thread(
            run_pipeline,
            topic=body.topic,
            settings=settings,
            provider=body.provider,
        )

        duration = time.time() - start
        await queries.update_run_status(
            session, run_id, user_id, "completed",
            final_result=result.output, duration=duration,
        )
        await queries.increment_usage(session, user_id)

        return GenerateResponse(
            status="success",
            topic=body.topic,
            provider_used=result.provider_used,
            duration_seconds=result.duration_seconds,
            result=result.output,
        )

    except RuntimeError as exc:
        logger.error("Pipeline runtime error: %s", exc)
        if "run_id" in locals():
            await queries.update_run_status(session, run_id, user["id"], "failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in /api/generate")
        if "run_id" in locals():
            await queries.update_run_status(session, run_id, user["id"], "failed")
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
    session: AsyncSession = Depends(get_session),
) -> BlogGenerateResponse:
    user_id = user["id"]

    if os.getenv("ENABLE_USAGE_LIMITS", "false").lower() in ("true", "1"):
        await queries.reset_usage_if_expired(session, user_id)
        usage = await queries.get_usage(session, user_id)
        if usage and usage.get("max_runs_per_month") and usage["runs_this_month"] >= usage["max_runs_per_month"]:
            raise HTTPException(status_code=429, detail="Usage limit exceeded for this billing period.")

    provider = body.provider or settings.default_provider
    run = await queries.create_run(session, user_id, body.topic, provider)
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
    session: AsyncSession = Depends(get_session),
) -> list[BlogPostSummary]:
    posts = await queries.get_blog_posts(session, user["id"], limit=limit)
    return [BlogPostSummary(**post) for post in posts]


@router.get(
    "/blog/posts/{blog_id}",
    response_model=BlogPostOut,
    summary="Get a single blog post with full markdown content",
)
async def get_blog_post(
    blog_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BlogPostOut:
    post = await queries.get_blog_by_id(session, blog_id, user["id"])
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
    session: AsyncSession = Depends(get_session),
) -> dict:
    deleted = await queries.soft_delete_blog(session, blog_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"status": "deleted", "id": blog_id}


@router.get(
    "/blog/{slug}",
    response_model=BlogPostOut,
    summary="Public: get a published blog post by slug (no auth)",
)
async def get_public_blog(
    slug: str, session: AsyncSession = Depends(get_session)
) -> BlogPostOut:
    post = await queries.get_public_blog_by_slug(session, slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return BlogPostOut(**post)
