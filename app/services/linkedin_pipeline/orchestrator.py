"""
LinkedInPipelineOrchestrator — the controller that wires the lean 4-agent
LinkedIn pipeline together.

Flow:
    Hook & Angle -> Write (single shot) -> [Python QA -> Edit] x<=2 -> Final QA -> Approve

Hard caps (never violated):
    - The Post Writer is called ONCE. No section loops.
    - Max 2 editor rewrite cycles, then the post is accepted as-is / flagged still_weak.
    - Python (LinkedInQAChecker) does ALL counting / measuring / detection.
    - The editor is only invoked when Python QA actually finds a problem.

Run it standalone for testing:
    python -m app.services.linkedin_pipeline.orchestrator --topic "vector databases" --niche "ai"
"""

import logging

from app.services.linkedin_pipeline.approver import LinkedInApproverAgent
from app.services.linkedin_pipeline.editor import LinkedInEditorAgent
from app.services.linkedin_pipeline.hook_finder import HookFinderAgent
from app.services.linkedin_pipeline.post_writer import PostWriterAgent
from app.services.linkedin_pipeline.qa_checker import LinkedInQAChecker

logger = logging.getLogger(__name__)

MAX_REWRITE_CYCLES = 2


class LinkedInPipelineOrchestrator:
    def __init__(self, llm_provider: str, run_id: str, step_callback=None):
        """
        Args:
            llm_provider: "nvidia" | "groq" | "ollama".
            run_id:       Telemetry run id (for the step_callback consumer).
            step_callback: Optional sync callable (agent_name, task_name, output_str)
                           invoked after each agent so a WebSocket layer can stream
                           progress. Exceptions inside it are swallowed.
        """
        self.llm_provider = llm_provider
        self.run_id = run_id
        self.step_callback = step_callback

    # ── callback safety wrapper ──────────────────────────────────────────────

    def _emit(self, agent_name: str, task_name: str, output) -> None:
        if not self.step_callback:
            return
        try:
            payload = output.model_dump_json() if hasattr(output, "model_dump_json") else str(output)
            self.step_callback(agent_name, task_name, payload)
        except Exception as exc:  # a broken callback must never kill generation
            logger.debug("step_callback raised (ignored): %s", exc)

    # ── main entry point ─────────────────────────────────────────────────────

    async def run(self, topic: str, niche: str, user_id: str) -> dict:
        # ── PHASE 1 — HOOK & ANGLE ────────────────────────────────────────
        hook_finder = HookFinderAgent(self.llm_provider)
        angle_pack = await hook_finder.run(topic, niche, trending_context="")
        self._emit("LinkedIn Hook Finder", "Find Angle & Hooks", angle_pack)

        # ── PHASE 2 — WRITE POST (single shot) ────────────────────────────
        writer = PostWriterAgent(self.llm_provider)
        draft = await writer.write(angle_pack, niche)
        self._emit("LinkedIn Post Writer", "Write LinkedIn Post", draft)
        current_post_text = draft.full_post

        # ── PHASE 3 — EDIT LOOP (max 2 cycles, only when QA finds problems) ─
        editor = LinkedInEditorAgent(self.llm_provider)
        qa = LinkedInQAChecker()
        still_weak = False
        cycles_taken = 0

        for cycle in range(1, MAX_REWRITE_CYCLES + 1):
            cycles_taken = cycle

            # Run Python QA first (deterministic).
            qa_results = qa.check(current_post_text)
            self._emit("LinkedIn QA Checker", f"Python QA cycle {cycle}", str(qa_results))

            if qa_results["overall_pass"]:
                break  # Python says it's clean — no need to call the editor.

            # Only call the editor when Python QA actually found problems.
            try:
                edited = await editor.edit(current_post_text, qa_results, cycle)
                self._emit("LinkedIn Editor", f"Edit cycle {cycle}", edited)
                current_post_text = edited.revised_post
                still_weak = edited.still_weak
            except Exception as exc:  # editor failure must not lose the post
                logger.warning("Editor failed on cycle %d: %s — keeping current text", cycle, exc)
                self._emit("LinkedIn Editor", f"Edit cycle {cycle} (failed)", str(exc))
                still_weak = cycle == MAX_REWRITE_CYCLES

            if still_weak and cycle == MAX_REWRITE_CYCLES:
                break  # Hit the hard cap — move on with the best attempt.

        # ── PHASE 4 — FINAL PYTHON QA ─────────────────────────────────────
        final_qa = qa.check(current_post_text)
        self._emit("LinkedIn QA Checker", "Final Python QA", str(final_qa))

        # ── PHASE 5 — APPROVER ────────────────────────────────────────────
        approver = LinkedInApproverAgent(self.llm_provider)
        approval = await approver.approve(topic, final_qa, still_weak)
        self._emit("LinkedIn Approver", "Final Approval", approval)

        return {
            "post_text": current_post_text,
            "hook": final_qa.get("first_line", ""),
            "angle_type": angle_pack.angle_type,
            "word_count": final_qa.get("word_count", 0),
            "hashtag_count": final_qa.get("hashtag_count", 0),
            "approved": approval.approved,
            "approval_reasons": approval.reasons,
            "qa_results": final_qa,
            "cycles_taken": cycles_taken,
        }


# ── Standalone CLI for isolated testing ──────────────────────────────────────


def _main() -> None:
    import argparse
    import asyncio

    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Run the 4-agent LinkedIn pipeline standalone.")
    parser.add_argument("--topic", required=True, help="LinkedIn post topic")
    parser.add_argument("--niche", default="ai", help="Niche / audience (default: ai)")
    parser.add_argument("--provider", default=None, help="LLM provider (default: settings.default_provider)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    provider = args.provider or get_settings().default_provider

    def _print_step(agent_name: str, task_name: str, output: str) -> None:
        print(f"\n=== [{agent_name}] {task_name} ===")
        print(output[:1200])

    orchestrator = LinkedInPipelineOrchestrator(
        llm_provider=provider, run_id="cli-test", step_callback=_print_step
    )
    result = asyncio.run(orchestrator.run(args.topic, args.niche, user_id="cli-user"))

    print("\n" + "=" * 70)
    print(f"ANGLE      : {result['angle_type']}")
    print(f"WORD COUNT : {result['word_count']}")
    print(f"HASHTAGS   : {result['hashtag_count']}")
    print(f"APPROVED   : {result['approved']}")
    print(f"REASONS    : {result['approval_reasons']}")
    print(f"CYCLES     : {result['cycles_taken']}")
    print("=" * 70 + "\n")
    print(result["post_text"])


if __name__ == "__main__":
    _main()
