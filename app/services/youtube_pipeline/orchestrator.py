"""
YouTubeScriptOrchestrator — controller for the lean YouTube script pipeline.

Flow:
    Write (single shot) -> Python QA -> SEO pack

Hard caps:
    - The Script Writer is called ONCE. No rewrite loops in v1 — Python QA only
      records what it found; a failing check flags the script (approved=False)
      for human review in the planner instead of burning editor calls.
    - Python (YouTubeQAChecker) does ALL counting / measuring / detection.

Run it standalone for testing:
    python -m app.services.youtube_pipeline.orchestrator --topic "vector databases"
"""

import json
import logging

from app.services.youtube_pipeline.qa_checker import YouTubeQAChecker
from app.services.youtube_pipeline.schemas import SeoPack
from app.services.youtube_pipeline.script_writer import ScriptWriterAgent
from app.services.youtube_pipeline.seo import SeoAgent

logger = logging.getLogger(__name__)


class YouTubeScriptOrchestrator:
    def __init__(self, llm_provider: str, run_id: str, step_callback=None):
        """
        Args:
            llm_provider: "nvidia" | "groq" | "ollama" | ...
            run_id:       Telemetry run id (for the step_callback consumer).
            step_callback: Optional sync callable (agent_name, task_name, output_str)
                           invoked after each phase. Exceptions inside it are swallowed.
        """
        self.llm_provider = llm_provider
        self.run_id = run_id
        self.step_callback = step_callback

    def _emit(self, agent_name: str, task_name: str, output) -> None:
        if not self.step_callback:
            return
        try:
            payload = output.model_dump_json() if hasattr(output, "model_dump_json") else str(output)
            self.step_callback(agent_name, task_name, payload)
        except Exception as exc:  # a broken callback must never kill generation
            logger.debug("step_callback raised (ignored): %s", exc)

    async def run(self, topic: str, niche: str, user_id: str, video_format: str = "full") -> dict:
        # ── PHASE 1 — WRITE SCRIPT (single shot) ──────────────────────────
        writer = ScriptWriterAgent(self.llm_provider)
        draft = await writer.write(topic, niche, video_format=video_format)
        self._emit("YouTube Script Writer", f"Write Script ({video_format})", draft)

        # ── PHASE 2 — PYTHON QA ───────────────────────────────────────────
        qa_results = YouTubeQAChecker().check(draft.script, video_format=video_format)
        self._emit("YouTube QA Checker", "Python QA", str(qa_results))

        # ── PHASE 3 — SEO PACK ────────────────────────────────────────────
        try:
            seo: SeoPack = await SeoAgent(self.llm_provider).run(topic, draft.script)
        except Exception as exc:  # SEO failure must not lose the script
            logger.warning("SEO agent failed: %s — continuing without SEO pack", exc)
            seo = SeoPack(seo_title=draft.title, seo_description="", seo_tags=[])
        self._emit("YouTube SEO Agent", "SEO Pack", seo)

        return {
            "title": draft.title,
            "script": draft.script,
            "word_count": qa_results["word_count"],
            "seo_title": seo.seo_title,
            "seo_description": seo.seo_description,
            "seo_tags": json.dumps(seo.seo_tags),
            "approved": qa_results["overall_pass"],
            "qa_results": qa_results,
        }


# ── Standalone CLI for isolated testing ──────────────────────────────────────


def _main() -> None:
    import argparse
    import asyncio

    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Run the YouTube script pipeline standalone.")
    parser.add_argument("--topic", required=True, help="Video topic")
    parser.add_argument("--niche", default="ai", help="Niche / audience (default: ai)")
    parser.add_argument("--provider", default=None, help="LLM provider (default: settings.default_provider)")
    parser.add_argument("--format", default="full", choices=["short", "full"], help="Video format (default: full)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    provider = args.provider or get_settings().default_provider

    def _print_step(agent_name: str, task_name: str, output: str) -> None:
        print(f"\n=== [{agent_name}] {task_name} ===")
        print(output[:1200])

    orchestrator = YouTubeScriptOrchestrator(
        llm_provider=provider, run_id="cli-test", step_callback=_print_step
    )
    result = asyncio.run(orchestrator.run(args.topic, args.niche, user_id="cli-user", video_format=args.format))

    print("\n" + "=" * 70)
    print(f"TITLE      : {result['title']}")
    print(f"WORD COUNT : {result['word_count']}")
    print(f"SEO TITLE  : {result['seo_title']}")
    print(f"APPROVED   : {result['approved']}")
    print("=" * 70 + "\n")
    print(result["script"][:3000])


if __name__ == "__main__":
    _main()
