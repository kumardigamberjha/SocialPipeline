"""
Celery task for the lean 4-agent LinkedIn pipeline.

Routing note
------------
The task is NOT pinned to a queue on the decorator (Celery's @task has no
``queue`` option). The API routes it at dispatch time with
``run_linkedin_pipeline.apply_async(args=[...], queue="linkedin_queue")`` and the
dedicated worker consumes that queue (``celery -A app.tasks worker -Q linkedin_queue``).

soft_time_limit=180 (3 minutes) — the LinkedIn pipeline is fast; if it runs
longer than that, something is wrong.
"""

import asyncio
import logging
import time

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.db import queries
from app.services.linkedin_pipeline import LinkedInPipelineOrchestrator

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="run_linkedin_pipeline",
    max_retries=1,
    soft_time_limit=180,
    time_limit=210,
    acks_late=True,
)
def run_linkedin_pipeline(self, run_id: str, topic: str, niche: str, user_id: str, provider: str):
    try:
        queries.update_run_status(run_id, "running")
        start = time.time()

        def step_callback(agent_name: str, task_name: str, output: str):
            queries.insert_task_step(run_id, agent_name, task_name, str(output))

        orchestrator = LinkedInPipelineOrchestrator(
            llm_provider=provider,
            run_id=run_id,
            step_callback=step_callback,
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
        logger.info("LinkedIn pipeline DONE ▸ run_id=%s duration=%.2fs approved=%s", run_id, duration, result["approved"])
        return result

    except SoftTimeLimitExceeded:
        logger.error("LinkedIn pipeline TIMEOUT ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise

    except Exception as exc:
        logger.exception("LinkedIn pipeline FAILED ▸ run_id=%s", run_id)
        queries.update_run_status(run_id, "failed")
        raise self.retry(exc=exc, countdown=10)
