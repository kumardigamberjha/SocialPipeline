"""
Celery task for the lean YouTube script pipeline.

Routing note
------------
Routed at dispatch time with
``run_youtube_pipeline.apply_async(args=[...], queue="youtube_queue")``; a
worker consumes it with ``celery -A app.tasks worker -Q youtube_queue`` (or add
the queue to an existing worker's -Q list).
"""

import asyncio
import logging
import time

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.db import queries
from app.services.youtube_pipeline import YouTubeScriptOrchestrator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="run_youtube_pipeline",
    max_retries=1,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True,
)
def run_youtube_pipeline(self, run_id: str, topic: str, niche: str, user_id: str, provider: str,
                         video_format: str = "full"):
    try:
        queries.update_run_status(run_id, "running")
        start = time.time()

        def step_callback(agent_name: str, task_name: str, output: str):
            queries.insert_task_step(run_id, agent_name, task_name, str(output))

        orchestrator = YouTubeScriptOrchestrator(
            llm_provider=provider,
            run_id=run_id,
            step_callback=step_callback,
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
        logger.info("YouTube pipeline DONE ▸ run_id=%s duration=%.2fs approved=%s", run_id, duration, result["approved"])
        return {"title": result["title"], "word_count": result["word_count"], "approved": result["approved"]}

    except SoftTimeLimitExceeded:
        logger.error("YouTube pipeline TIMEOUT ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise

    except Exception as exc:
        logger.exception("YouTube pipeline FAILED ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise self.retry(exc=exc, countdown=10)
