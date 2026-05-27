"""
Crew orchestration – assembles agents, tasks, and runs the pipeline.

Includes niche-locked auto-research: rotates between AI and Software Dev niches,
picks seed topics, researches them, deduplicates against the content tracker,
and selects the best non-duplicate topic for content generation.

Handles the NVIDIA → Groq automatic fallback on failure.
"""

import json
import logging
import os
import random
import time
import asyncio

from crewai import Crew

from app.agents import create_all_agents
from app.config import Settings
from app.db.content_tracker import (
    is_duplicate_topic,
    mark_topic_published,
    rotate_niche,
    get_niche_state,
)
from app.llm import build_llm
from app.task_factories import create_all_tasks
from app.tools.research_engine import run_multi_source_search
from app.ws_manager import manager
from app.db.queries import save_task_step, update_agent_run, create_agent_run

logger = logging.getLogger(__name__)


# ── Niche Seed Banks ────────────────────────────────────────────────────────

AI_NICHE_SEEDS = [
    "latest open-source LLM releases",
    "AI agent frameworks compared",
    "RAG pipeline optimization techniques",
    "fine-tuning small language models",
    "AI coding assistants benchmark",
    "multimodal AI models 2025",
    "LLM inference optimization",
    "vector database performance comparison",
    "AI safety and alignment research",
    "open-source image generation models",
    "local LLM deployment strategies",
    "AI-powered developer tools",
    "transformer architecture innovations",
    "LLM context window breakthroughs",
    "machine learning ops best tools",
    "edge AI and on-device models",
    "AI pair programming workflows",
    "synthetic data generation techniques",
    "prompt engineering advanced patterns",
    "AI model quantization methods",
]

SOFTWARE_DEV_SEEDS = [
    "Rust vs Go for backend services",
    "modern Python project setup 2025",
    "Docker alternatives gaining traction",
    "serverless vs containers tradeoffs",
    "database scaling patterns",
    "API design best practices REST vs GraphQL",
    "git workflows for large teams",
    "CI/CD pipeline optimization",
    "microservices vs monolith decision framework",
    "WebAssembly practical use cases",
    "open-source monitoring stack setup",
    "developer productivity tools",
    "backend performance profiling",
    "system design interview patterns",
    "event-driven architecture patterns",
    "Kubernetes alternatives for small teams",
    "testing strategies for fast-moving teams",
    "open-source self-hosted tools",
    "terminal and CLI productivity hacks",
    "developer experience engineering",
]


def _pick_seeds(niche: str, count: int = 3) -> list[str]:
    """Pick random seed topics for the given niche."""
    bank = AI_NICHE_SEEDS if niche == "ai" else SOFTWARE_DEV_SEEDS
    return random.sample(bank, min(count, len(bank)))


# ── Auto-Research Topic Selection ───────────────────────────────────────────

def auto_select_topic(max_retries: int = 3) -> tuple[str, str, str]:
    """
    Niche-locked auto-research flow:
        1. Rotate niche (ai ↔ software_dev)
        2. Pick 3 random seeds from the niche bank
        3. Research each seed via multi-source search
        4. Check each result against content tracker for duplicates
        5. Select the highest-scoring non-duplicate topic
        6. If all are duplicates, retry with new seeds (up to max_retries)

    Returns:
        (selected_topic, niche, research_context) — the topic string,
        which niche it belongs to, and the raw research context to inject.

    Raises:
        RuntimeError if all retries exhausted (all topics are duplicates).
    """
    niche = rotate_niche()
    logger.info("Auto-research: niche rotated to %r", niche)

    for attempt in range(1, max_retries + 1):
        seeds = _pick_seeds(niche, count=3)
        logger.info("Auto-research attempt %d: seeds=%s", attempt, seeds)

        best_topic = None
        best_context = ""
        best_score = -1.0

        for seed in seeds:
            # Research this seed
            search_results = run_multi_source_search(seed, max_results_per_source=5)

            if not search_results or "no results" in search_results.lower():
                logger.warning("No research results for seed: %r", seed)
                continue

            # The seed itself is a candidate topic, enriched with research
            is_dup, sim_score = is_duplicate_topic(seed)
            if not is_dup:
                # Use (1 - similarity) as a freshness score — lower sim = better
                freshness = 1.0 - sim_score
                if freshness > best_score:
                    best_score = freshness
                    best_topic = seed
                    best_context = search_results
            else:
                logger.info("Seed %r is duplicate (sim=%.3f), skipping", seed, sim_score)

        if best_topic:
            logger.info(
                "Auto-research selected: %r (niche=%s, freshness=%.3f)",
                best_topic, niche, best_score,
            )
            enriched = (
                f"{best_topic}\n\n"
                f"=== MULTI-SOURCE RESEARCH CONTEXT ===\n"
                f"{best_context}\n"
                f"=== END RESEARCH CONTEXT ===\n"
            )
            return best_topic, niche, enriched

        logger.warning("All seeds were duplicates on attempt %d, retrying...", attempt)

    raise RuntimeError(
        f"Auto-research exhausted {max_retries} retries — all topics are duplicates. "
        f"Consider adding more seeds to the {niche} seed bank."
    )


# ── Research Enrichment ─────────────────────────────────────────────────────

def enrich_topic_with_search(topic: str) -> str:
    """Run the multi-source research engine to enrich the topic prompt with
    real-time context from Hacker News, Reddit, DuckDuckGo, DEV.to, ArXiv,
    GitHub Trending, and Product Hunt — all searched in parallel.

    This guarantees that the agents have access to fresh, cross-platform
    research without having to execute tool calls themselves, preventing
    tool-calling failures.
    """
    logger.info("Performing multi-source research for topic: %r", topic)
    try:
        query = topic
        if "LATEST AI TRENDS:" in topic:
            query = "latest AI trends today"

        search_results = run_multi_source_search(query, max_results_per_source=5)

        if search_results and "no results" not in search_results.lower():
            logger.info("Multi-source research succeeded. Appending results to context.")
            context = (
                "\n\n=== MULTI-SOURCE RESEARCH CONTEXT ===\n"
                f"{search_results}\n"
                "=== END RESEARCH CONTEXT ===\n\n"
            )
            return topic + context
        else:
            logger.warning("Multi-source research returned no valid results.")
    except Exception as e:
        logger.error("Multi-source research failed: %s", e)
    return topic


# ── Pipeline Results ────────────────────────────────────────────────────────

class PipelineResult:
    """Structured result from a pipeline run."""

    __slots__ = ("output", "provider_used", "duration_seconds", "topic", "niche")

    def __init__(self, output: str, provider_used: str, duration_seconds: float,
                 topic: str = "", niche: str = ""):
        self.output = output
        self.provider_used = provider_used
        self.duration_seconds = duration_seconds
        self.topic = topic
        self.niche = niche


# ── Sync Pipeline ───────────────────────────────────────────────────────────

def run_pipeline(
    topic: str,
    settings: Settings,
    provider: str | None = None,
    auto_research: bool = False,
) -> PipelineResult:
    """
    Execute the full content-generation pipeline.

    1. If auto_research=True, use niche-locked auto-topic selection.
    2. Build agents + tasks with the primary provider.
    3. On failure, automatically retry with the fallback provider.
    4. On success, mark the topic as published in the content tracker.

    Args:
        topic:          The content topic (ignored if auto_research=True).
        settings:       Application settings.
        provider:       Override LLM provider ("nvidia" / "groq" / "ollama").
        auto_research:  If True, auto-select topic via niche rotation + research.

    Returns:
        PipelineResult with the raw output, provider used, duration, topic, and niche.
    """
    primary = provider or settings.default_provider
    fallback = "ollama" if primary == "ollama" else ("groq" if primary == "nvidia" else "nvidia")

    start = time.perf_counter()

    # Auto-research topic selection
    niche = ""
    if auto_research:
        topic, niche, enriched_topic = auto_select_topic()
        logger.info("Auto-research topic: %r (niche=%s)", topic, niche)
    else:
        enriched_topic = enrich_topic_with_search(topic)

    # ── Attempt with primary provider ────────────────────────────────────
    try:
        logger.info("Pipeline START  ▸ topic=%r  provider=%s", topic, primary)

        llm = build_llm(primary, settings)
        agents = create_all_agents(llm, primary)
        tasks = create_all_tasks(agents, enriched_topic)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False,
        )

        result = crew.kickoff()
        elapsed = round(time.perf_counter() - start, 2)

        # Mark topic as published
        mark_topic_published(
            topic=topic,
            niche=niche or "unknown",
            content_types=["youtube", "linkedin", "twitter", "blog", "shorts", "course"],
            sources=[],
            run_id="sync-pipeline",
        )

        logger.info("Pipeline DONE   ▸ provider=%s  duration=%.2fs", primary, elapsed)
        return PipelineResult(
            output=str(result),
            provider_used=primary,
            duration_seconds=elapsed,
            topic=topic,
            niche=niche,
        )

    except Exception as exc:
        logger.warning(
            "Pipeline FAILED with %s (%s) — falling back to %s",
            primary, exc, fallback,
        )

    # ── Fallback ─────────────────────────────────────────────────────────
    try:
        llm = build_llm(fallback, settings)
        agents = create_all_agents(llm, fallback)
        tasks = create_all_tasks(agents, enriched_topic)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False,
        )

        result = crew.kickoff()
        elapsed = round(time.perf_counter() - start, 2)

        # Mark topic as published
        mark_topic_published(
            topic=topic,
            niche=niche or "unknown",
            content_types=["youtube", "linkedin", "twitter", "blog", "shorts", "course"],
            sources=[],
            run_id="sync-pipeline-fallback",
        )

        logger.info("Pipeline DONE (fallback)  ▸ provider=%s  duration=%.2fs", fallback, elapsed)
        return PipelineResult(
            output=str(result),
            provider_used=fallback,
            duration_seconds=elapsed,
            topic=topic,
            niche=niche,
        )

    except Exception as fallback_exc:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("Pipeline FAILED on both providers after %.2fs", elapsed)
        raise RuntimeError(
            f"All providers failed. Primary ({primary}): see logs. "
            f"Fallback ({fallback}): {fallback_exc}"
        ) from fallback_exc


# ── Streaming Pipeline (WebSocket) ──────────────────────────────────────────

def _sync_ws_event(client_id: str, loop: asyncio.AbstractEventLoop, event_type: str, payload: dict):
    """Emit generic JSON events to WS."""
    data = {"type": event_type}
    data.update(payload)
    asyncio.run_coroutine_threadsafe(manager.send_json(data, client_id), loop)


async def run_pipeline_streaming(
    topic: str,
    settings: Settings,
    provider: str,
    client_id: str,
    run_id: str,
    auto_research: bool = False,
):
    loop = asyncio.get_running_loop()

    # Run already created in ws.py; we just update it as we go.
    from app.db.queries import update_run_status
    update_run_status(run_id, 'running')

    def task_callback(task_name, output):
        save_task_step(run_id, "Agent", task_name, output, "done")
        _sync_ws_event(client_id, loop, "task_finished", {
            "task": task_name,
            "output": output
        })

    def _run():
        nonlocal topic

        # Auto-research or manual enrichment
        niche = ""
        if auto_research:
            topic_selected, niche, enriched_topic = auto_select_topic()
            # Update topic to the auto-selected one
            topic_ref = topic_selected
        else:
            enriched_topic = enrich_topic_with_search(topic)
            topic_ref = topic

        from app.db.qdrant import search_memory, search_document

        # Pull Context from Qdrant
        memories = search_memory(run_id, topic_ref, limit=3)
        docs = search_document(run_id, topic_ref, limit=2)

        context_str = ""
        if memories:
            context_str += "\n\nPast Memory Context:\n" + "\n".join(memories)
        if docs:
            context_str += "\n\nDocument Reference Context:\n" + "\n".join(docs)

        final_topic = enriched_topic + context_str

        llm = build_llm(provider, settings)
        agents = create_all_agents(llm, provider)
        tasks = create_all_tasks(agents, final_topic, task_callback=task_callback)

        # Fire initial task_started sequence
        if tasks:
            _sync_ws_event(client_id, loop, "task_started", {"task": tasks[0].description})

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process="sequential",
            verbose=True,
            memory=False,
        )

        result = crew.kickoff()

        # Mark topic as published after successful completion
        mark_topic_published(
            topic=topic_ref,
            niche=niche or "unknown",
            content_types=["youtube", "linkedin", "twitter", "blog", "shorts", "course"],
            sources=[],
            run_id=run_id,
        )

        return str(result), topic_ref

    try:
        await manager.send_json({"type": "status", "message": "Pipeline started"}, client_id)
        result_tuple = await asyncio.to_thread(_run)
        final_output, resolved_topic = result_tuple

        # Extract a clean title for the Telemetry Ledger
        generated_title = resolved_topic
        lines = [l.strip() for l in final_output.split("\n") if l.strip()]
        if lines:
            for line in lines:
                clean_line = line.lstrip("#* ").strip()
                if clean_line:
                    generated_title = (clean_line[:75] + '...') if len(clean_line) > 75 else clean_line
                    break

        update_agent_run(run_id, final_output, 0.0, "completed", topic=generated_title)

        # Save local JSON
        os.makedirs("output", exist_ok=True)
        try:
            with open(f"output/{run_id}.json", "w", encoding="utf-8") as f:
                json.dump({"run_id": run_id, "topic": resolved_topic, "result": final_output}, f, indent=2)
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
