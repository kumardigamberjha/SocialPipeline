"""
Shared pipeline dispatch helpers.

Every generation pipeline (LinkedIn / Blog / YouTube) runs on a dedicated Celery
queue, with an in-process FastAPI BackgroundTasks fallback. This module
centralizes the "can we actually use Celery?" decision and the fallback runners
so the linkedin/blog/youtube/planner routers all share one implementation.

Why the worker check matters
----------------------------
Checking only that Redis is reachable is not enough: if Redis is up but NO
worker is draining the target queue, apply_async silently enqueues a task that
never runs and the generation hangs "forever". should_use_celery() therefore
requires both a reachable broker AND a live worker consuming the queue; when
that's not true the caller runs the pipeline in-process via BackgroundTasks.

Each fallback mirrors its Celery task exactly: run status transitions, task_steps
telemetry, content save, usage increment.
"""

import asyncio
import logging
import time

import redis

from app.config import get_settings
from app.db import queries

logger = logging.getLogger(__name__)

LINKEDIN_QUEUE = "linkedin_queue"
BLOG_QUEUE = "blog_queue"
YOUTUBE_QUEUE = "youtube_queue"


def is_redis_available() -> bool:
    try:
        r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


def celery_worker_consuming(queue: str, timeout: float = 0.75) -> bool:
    """True if at least one live Celery worker is consuming ``queue``.

    Uses Celery's control broadcast (active_queues). Returns False on any error
    or timeout so the safe default is in-process execution rather than a task
    that sits unconsumed in Redis.
    """
    try:
        from app.celery_app import celery_app

        active = celery_app.control.inspect(timeout=timeout).active_queues() or {}
        return any(
            q.get("name") == queue
            for worker_queues in active.values()
            for q in worker_queues
        )
    except Exception as exc:  # broker/control errors -> fall back in-process
        logger.warning("Could not inspect Celery workers for queue %s: %s", queue, exc)
        return False


def should_use_celery(queue: str) -> bool:
    """Dispatch to Celery only when Redis is reachable AND a worker is draining
    ``queue``; otherwise the caller must run the pipeline via BackgroundTasks."""
    return is_redis_available() and celery_worker_consuming(queue)


def _step_writer(run_id: str):
    def step_callback(agent_name: str, task_name: str, output: str):
        queries.insert_task_step(run_id, agent_name, task_name, str(output))
    return step_callback


def run_linkedin_fallback(run_id: str, topic: str, niche: str, user_id: str, provider: str):
    from app.services.linkedin_pipeline import LinkedInPipelineOrchestrator

    try:
        queries.update_run_status(run_id, "running")
        start = time.time()
        orchestrator = LinkedInPipelineOrchestrator(
            llm_provider=provider, run_id=run_id, step_callback=_step_writer(run_id)
        )
        result = asyncio.run(orchestrator.run(topic, niche, user_id))
        duration = round(time.time() - start, 2)
        queries.save_linkedin_post(
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            post_text=result["post_text"],
            hook=result["hook"],
            angle_type=result["angle_type"],
            word_count=result["word_count"],
            approved=result["approved"],
            niche=niche,
        )
        queries.update_run_status(run_id, "completed", final_result=result["post_text"], duration=duration)
        queries.increment_usage(user_id)
        logger.info("LinkedIn pipeline DONE (fallback) ▸ run_id=%s duration=%.2fs", run_id, duration)
    except Exception:
        logger.exception("LinkedIn pipeline FAILED (fallback) ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")


def run_blog_fallback(run_id: str, topic: str, target_keyword: str, user_id: str, provider: str):
    from app.services.blog_pipeline import BlogPipelineOrchestrator

    try:
        queries.update_run_status(run_id, "running")
        start = time.time()
        orchestrator = BlogPipelineOrchestrator(
            llm_provider=provider, run_id=run_id, step_callback=_step_writer(run_id)
        )
        result = asyncio.run(orchestrator.run(topic, target_keyword, user_id))
        duration = round(time.time() - start, 2)
        queries.save_blog_post(
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            title=result["title"],
            content=result["markdown"],
            niche="auto",
            approved=result["approved"],
            word_count=result["word_count"],
        )
        queries.update_run_status(run_id, "completed", final_result=result["markdown"], duration=duration)
        queries.increment_usage(user_id)
        logger.info("Blog pipeline DONE (fallback) ▸ run_id=%s duration=%.2fs", run_id, duration)
    except Exception:
        logger.exception("Blog pipeline FAILED (fallback) ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")


def run_youtube_fallback(run_id: str, topic: str, niche: str, user_id: str, provider: str,
                         video_format: str = "full"):
    from app.services.youtube_pipeline import YouTubeScriptOrchestrator

    try:
        queries.update_run_status(run_id, "running")
        start = time.time()
        orchestrator = YouTubeScriptOrchestrator(
            llm_provider=provider, run_id=run_id, step_callback=_step_writer(run_id)
        )
        result = asyncio.run(orchestrator.run(topic, niche, user_id, video_format=video_format))
        duration = round(time.time() - start, 2)
        queries.save_youtube_script(
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            title=result["title"],
            script=result["script"],
            word_count=result["word_count"],
            seo_title=result["seo_title"],
            seo_description=result["seo_description"],
            seo_tags=result["seo_tags"],
            approved=result["approved"],
            niche=niche,
        )
        queries.update_run_status(run_id, "completed", final_result=result["script"], duration=duration)
        queries.increment_usage(user_id)
        logger.info("YouTube pipeline DONE (fallback) ▸ run_id=%s duration=%.2fs", run_id, duration)
    except Exception:
        logger.exception("YouTube pipeline FAILED (fallback) ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")


# ── Shared pipeline launcher ─────────────────────────────────────────────────

CONTENT_TYPES = ("linkedin", "blog", "youtube_script")

# content_type -> lookup for the produced row by run_id
CONTENT_LOOKUP = {
    "linkedin": queries.get_linkedin_posts_by_run_id,
    "blog": queries.get_blog_posts_by_run_id,
    "youtube_script": queries.get_youtube_scripts_by_run_id,
}


def dispatch_pipeline(content_type: str, run_id: str, topic: str, niche: str, user_id: str,
                      provider: str, video_format: str, background_tasks) -> None:
    """Launch one content pipeline for an already-created run.

    Owner-agnostic on purpose: the caller has already created whatever link row
    it needs (plan_item_content, saved_topic_runs, ...). Everything here — the
    per-type task signatures, the queue names, the Celery-vs-BackgroundTasks
    decision — is shared, so a new owner type never has to copy it.
    """
    # Lazy imports so a broken Celery import can never take the API down.
    from app.tasks.blog_task import run_blog_pipeline
    from app.tasks.linkedin_task import run_linkedin_pipeline
    from app.tasks.youtube_task import run_youtube_pipeline

    celery_specs = {
        "linkedin": (run_linkedin_pipeline, LINKEDIN_QUEUE, [run_id, topic, niche, user_id, provider]),
        "blog": (run_blog_pipeline, BLOG_QUEUE, [run_id, topic, topic, user_id, provider]),  # target_keyword = topic
        "youtube_script": (run_youtube_pipeline, YOUTUBE_QUEUE, [run_id, topic, niche, user_id, provider, video_format]),
    }
    fallback_specs = {
        "linkedin": (run_linkedin_fallback, (run_id, topic, niche, user_id, provider)),
        "blog": (run_blog_fallback, (run_id, topic, topic, user_id, provider)),
        "youtube_script": (run_youtube_fallback, (run_id, topic, niche, user_id, provider, video_format)),
    }

    task, queue, args = celery_specs[content_type]
    fb_fn, fb_args = fallback_specs[content_type]

    dispatched_to_celery = False
    if should_use_celery(queue):
        try:
            task.apply_async(args=args, queue=queue, ignore_result=True)
            dispatched_to_celery = True
        except Exception as exc:
            logger.warning("Celery dispatch failed for %s, using BackgroundTasks: %s", content_type, exc)

    if not dispatched_to_celery:
        logger.info("Running %s pipeline in-process (no Celery worker) ▸ run_id=%s", content_type, run_id)
        background_tasks.add_task(fb_fn, *fb_args)
