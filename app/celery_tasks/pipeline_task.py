import json
import logging
import os
import time

from celery import states
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.config import get_settings
from app.crew import enrich_topic_with_search
from app.db import queries
from app.llm import build_llm
from app.agents import create_all_agents
from app.task_factories import create_all_tasks

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="run_content_pipeline",
    max_retries=2,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def run_content_pipeline(self, run_id: str, topic: str, provider: str, user_id: str):
    settings = get_settings()
    
    try:
        queries.update_run_status(run_id, 'running')
        
        # Check and enforce usage limits
        queries.reset_usage_if_expired(user_id)
        usage = queries.get_usage(user_id)
        if usage and usage['runs_this_month'] >= usage['max_runs_per_month']:
            queries.update_run_status(run_id, 'failed')
            raise Exception("Usage limit exceeded for this billing period.")
            
        start = time.perf_counter()

        primary = provider or settings.default_provider
        fallback = "ollama" if primary == "ollama" else ("groq" if primary == "nvidia" else "nvidia")

        def _execute(use_provider: str) -> str:
            enriched_topic = enrich_topic_with_search(topic)

            from app.db.qdrant import search_memory, search_document
            memories = search_memory(user_id, enriched_topic, limit=3)
            docs = search_document(user_id, enriched_topic, limit=2)

            context_str = ""
            if memories:
                context_str += "\n\nPast Memory Context:\n" + "\n".join(memories)
            if docs:
                context_str += "\n\nDocument Reference Context:\n" + "\n".join(docs)

            full_topic = enriched_topic + context_str

            llm = build_llm(use_provider, settings)
            agents = create_all_agents(llm, use_provider)

            def task_callback(task_name: str, output: str):
                queries.insert_task_step(run_id, "Agent", task_name, output, "done")

            tasks = create_all_tasks(agents, full_topic, task_callback=task_callback)

            from crewai import Crew
            crew = Crew(
                agents=agents,
                tasks=tasks,
                process="sequential",
                verbose=True,
                memory=False,
            )
            result = crew.kickoff()
            return str(result)

        try:
            logger.info("Pipeline START ▸ run_id=%s topic=%r provider=%s", run_id, topic, primary)
            final_output = _execute(primary)

        except SoftTimeLimitExceeded:
            elapsed = round(time.perf_counter() - start, 2)
            logger.error("Pipeline TIMEOUT after %.2fs ▸ run_id=%s", elapsed, run_id)
            queries.update_run_status(run_id, 'failed', duration=elapsed)
            raise

        except Exception as primary_exc:
            logger.warning(
                "Pipeline FAILED with %s (%s) — falling back to %s ▸ run_id=%s",
                primary, primary_exc, fallback, run_id,
            )
            try:
                final_output = _execute(fallback)
            except Exception as fallback_exc:
                elapsed = round(time.perf_counter() - start, 2)
                logger.error("Pipeline FAILED on both providers after %.2fs ▸ run_id=%s", elapsed, run_id)
                queries.update_run_status(run_id, 'failed', duration=elapsed)
                try:
                    self.retry(exc=fallback_exc, countdown=10)
                except self.MaxRetriesExceededError:
                    queries.update_run_status(run_id, 'failed', final_result=f"All retries exhausted: {fallback_exc}", duration=elapsed)
                    raise

        elapsed = round(time.perf_counter() - start, 2)
        logger.info("Pipeline DONE ▸ run_id=%s duration=%.2fs", run_id, elapsed)

        queries.update_run_status(run_id, 'completed', final_result=final_output, duration=elapsed)
        queries.increment_usage(user_id)

        os.makedirs("output", exist_ok=True)
        try:
            with open(f"output/{run_id}.json", "w", encoding="utf-8") as f:
                json.dump({"run_id": run_id, "topic": topic, "result": final_output}, f, indent=2)
        except Exception as e:
            logger.error("Failed to save local output JSON: %s", e)

        return {"run_id": run_id, "status": "completed", "duration_seconds": elapsed}

    except Exception as exc:
        queries.update_run_status(run_id, 'failed')
        raise self.retry(exc=exc, countdown=10)
