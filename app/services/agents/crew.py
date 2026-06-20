"""
Crew orchestration – assembles agents, tasks, and runs the pipeline.

Handles the NVIDIA → Groq automatic fallback on failure.
"""

import logging
import time

from crewai import Crew

from app.agents import create_all_agents
from app.core.config import Settings
from app.core.llm import build_llm
from app.task_factories import create_all_tasks

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
            max_rpm=10,
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
            max_rpm=10,
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
