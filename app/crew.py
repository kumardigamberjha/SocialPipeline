"""
Crew orchestration – assembles agents, tasks, and runs the pipeline.

Handles the NVIDIA → Groq automatic fallback on failure.
"""

import logging
import time

from crewai import Crew

from app.agents import create_all_agents
from app.config import Settings
from app.llm import build_llm
from app.tasks import create_all_tasks

logger = logging.getLogger(__name__)


class PipelineResult:
    """Structured result from a pipeline run."""

    __slots__ = ("output", "provider_used", "duration_seconds")

    def __init__(self, output: str, provider_used: str, duration_seconds: float):
        self.output = output
        self.provider_used = provider_used
        self.duration_seconds = duration_seconds


def run_pipeline(topic: str, settings: Settings, provider: str | None = None) -> PipelineResult:
    """
    Execute the full content-generation pipeline.

    1. Build agents + tasks with the primary provider.
    2. On failure, automatically retry with the fallback provider.

    Args:
        topic:    The content topic.
        settings: Application settings.
        provider: Override LLM provider ("nvidia" / "groq").

    Returns:
        PipelineResult with the raw output, provider used, and duration.
    """
    primary = provider or settings.default_provider
    fallback = "groq" if primary == "nvidia" else "nvidia"

    start = time.perf_counter()

    # ── Attempt with primary provider ────────────────────────────────────
    try:
        logger.info("Pipeline START  ▸ topic=%r  provider=%s", topic, primary)

        llm = build_llm(primary, settings)
        agents = create_all_agents(llm)
        tasks = create_all_tasks(agents, topic)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False, # disabled native memory
        )

        result = crew.kickoff()
        elapsed = round(time.perf_counter() - start, 2)

        logger.info("Pipeline DONE   ▸ provider=%s  duration=%.2fs", primary, elapsed)
        return PipelineResult(
            output=str(result),
            provider_used=primary,
            duration_seconds=elapsed,
        )

    except Exception as exc:
        logger.warning(
            "Pipeline FAILED with %s (%s) — falling back to %s",
            primary,
            exc,
            fallback,
        )

    # ── Fallback ─────────────────────────────────────────────────────────
    try:
        llm = build_llm(fallback, settings)
        agents = create_all_agents(llm)
        tasks = create_all_tasks(agents, topic)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False,
        )

        result = crew.kickoff()
        elapsed = round(time.perf_counter() - start, 2)

        logger.info("Pipeline DONE (fallback)  ▸ provider=%s  duration=%.2fs", fallback, elapsed)
        return PipelineResult(
            output=str(result),
            provider_used=fallback,
            duration_seconds=elapsed,
        )

    except Exception as fallback_exc:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("Pipeline FAILED on both providers after %.2fs", elapsed)
        raise RuntimeError(
            f"All providers failed. Primary ({primary}): see logs. "
            f"Fallback ({fallback}): {fallback_exc}"
        ) from fallback_exc


import json
import os
import asyncio
from app.ws_manager import manager
from app.db.supabase import save_task_step, update_agent_run, create_agent_run

def _sync_ws_event(client_id: str, loop: asyncio.AbstractEventLoop, event_type: str, payload: dict):
    """Emit generic JSON events to WS."""
    data = {"type": event_type}
    data.update(payload)
    asyncio.run_coroutine_threadsafe(manager.send_json(data, client_id), loop)

async def run_pipeline_streaming(topic: str, settings: Settings, provider: str, client_id: str, run_id: str):
    loop = asyncio.get_running_loop()
    
    # Insert entry into the database before agents start
    # Using dummy ID for anonymous runs without auth context hooked up
    dummy_user_id = "00000000-0000-0000-0000-000000000000"
    create_agent_run(run_id, dummy_user_id, topic, provider) 
    
    def task_callback(task_name, output):
        # 1. Save to DB synchronously in this thread
        save_task_step(run_id, "Agent", task_name, output, "done")
        
        # 2. Emit WS Event
        _sync_ws_event(client_id, loop, "task_finished", {
            "task": task_name,
            "output": output
        })
        
    def _run():
        from app.db.qdrant import search_memory, search_document
        
        # 3. Pull Context from Qdrant
        memories = search_memory(run_id, topic, limit=3)
        docs = search_document(run_id, topic, limit=2)
        
        context_str = ""
        if memories:
            context_str += "\n\nPast Memory Context:\n" + "\n".join(memories)
        if docs:
            context_str += "\n\nDocument Reference Context:\n" + "\n".join(docs)
            
        enriched_topic = topic + context_str
        
        llm = build_llm(provider, settings)
        agents = create_all_agents(llm)
        tasks = create_all_tasks(agents, enriched_topic, task_callback=task_callback)
        
        # Fire initial task_started sequence
        if tasks:
            _sync_ws_event(client_id, loop, "task_started", {"task": tasks[0].description})
            
        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False, # Disabled native memory to avoid OpenAI API Key dependency; custom Qdrant context is already injected.
        )
        return crew.kickoff()
        
    try:
        await manager.send_json({"type": "status", "message": "Pipeline started"}, client_id)
        result = await asyncio.to_thread(_run)
        final_output = str(result)
        
        # Extract a clean title for the Telemetry Ledger (first line, stripping Markdown headers)
        generated_title = topic
        lines = [l.strip() for l in final_output.split("\n") if l.strip()]
        if lines:
            # Look for the first line that isn't just a header symbol
            for line in lines:
                clean_line = line.lstrip("#* ").strip()
                if clean_line:
                    # Truncate if it's too long
                    generated_title = (clean_line[:75] + '...') if len(clean_line) > 75 else clean_line
                    break

        # Update DB run with the final result and the new user-friendly title
        update_agent_run(run_id, final_output, 0.0, "completed", topic=generated_title)
        
        # Save local JSON
        os.makedirs("output", exist_ok=True)
        try:
            with open(f"output/{run_id}.json", "w", encoding="utf-8") as f:
                json.dump({"run_id": run_id, "topic": topic, "result": final_output}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save local output JSON: {e}")
            
        await manager.send_json({
            "type": "complete", 
            "result": final_output
        }, client_id)
    except Exception as e:
        logger.error(f"Streaming pipeline failed: {e}")
        update_agent_run(run_id, "", 0.0, "failed")
        await manager.send_json({"type": "error", "message": str(e)}, client_id)
