"""
Celery task for the lean 5-agent blog pipeline.

Routing note
------------
The task is NOT pinned to a queue on the decorator (Celery's @task has no
``queue`` option). The API routes it at dispatch time with
``run_blog_pipeline.apply_async(args=[...], queue="blog_queue")`` and the
dedicated worker consumes that queue (``celery -A app.tasks worker -Q blog_queue``).

soft_time_limit=600 (10 minutes) — a ~20k-word blog runs Researcher + a per-section
write/edit loop, so it is far slower than the LinkedIn pipeline.

step_callback writes one ``task_steps`` row per agent / section; the blog
WebSocket poller reads those rows to stream progress to the client.
"""

import asyncio
import logging
import time

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.db import queries
from app.services.blog_pipeline import BlogPipelineOrchestrator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="run_blog_pipeline",
    max_retries=1,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def run_blog_pipeline(self, run_id: str, topic: str, target_keyword: str, user_id: str, provider: str):
    try:
        queries.update_run_status(run_id, "running")
        start = time.time()

        def step_callback(agent_name: str, task_name: str, output: str):
            queries.insert_task_step(run_id, agent_name, task_name, str(output))

        orchestrator = BlogPipelineOrchestrator(
            llm_provider=provider,
            run_id=run_id,
            step_callback=step_callback,
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
        logger.info(
            "Blog pipeline DONE ▸ run_id=%s duration=%.2fs words=%d approved=%s",
            run_id, duration, result["word_count"], result["approved"],
        )
        return result

    except SoftTimeLimitExceeded:
        logger.error("Blog pipeline TIMEOUT ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise

    except Exception as exc:
        logger.exception("Blog pipeline FAILED ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise self.retry(exc=exc, countdown=15)
