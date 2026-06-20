"""
BlogPipelineOrchestrator — the controller that wires all 5 agents together.

Flow:
    Research -> [Write -> Edit(x<=2)] per section -> QA/Assemble -> Approve -> Render

Hard caps (never violated):
    - Writer and Editor are called PER SECTION, never on the whole blog.
    - Max 2 rewrite cycles per section, then the section is flagged for human review.
    - Python (QAAssembler) does all counting / arithmetic / validation.

Run it standalone for testing:
    python -m app.services.blog_pipeline.orchestrator --topic "Building RAG" --keyword "RAG"
"""

import asyncio
import logging

from app.services.blog_pipeline.approver import ApproverAgent
from app.services.blog_pipeline.editor import EditorAgent
from app.services.blog_pipeline.qa_assembler import QAAssembler
from app.services.blog_pipeline.researcher import ResearcherAgent
from app.services.blog_pipeline.schemas import (
    EditedSection,
    SectionDraft,
    SectionOutline,
    SectionQAResult,
)
from app.services.blog_pipeline.writer import SectionWriterAgent

logger = logging.getLogger(__name__)

MAX_REWRITE_CYCLES = 2


class BlogPipelineOrchestrator:
    def __init__(self, llm_provider: str, run_id: str, step_callback=None):
        """
        Args:
            llm_provider: "nvidia" | "groq" | "ollama".
            run_id:       Telemetry run id (for the step_callback consumer).
            step_callback: Optional sync callable (agent_name, task_name, output)
                           invoked after each agent / section so a WebSocket layer
                           can stream progress. Exceptions inside it are swallowed.
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

    async def run(self, topic: str, target_keyword: str, user_id: str) -> dict:
        # ── PHASE 1 — RESEARCH ────────────────────────────────────────────
        researcher = ResearcherAgent(self.llm_provider)
        grounding_pack = await researcher.run(topic, target_keyword)
        self._emit("Blog Researcher", "Build Grounding Pack", grounding_pack)
        target_keyword = grounding_pack.target_keyword or target_keyword

        # ── PHASE 2 — SECTION LOOP (write -> edit, max 2 cycles) ──────────
        writer = SectionWriterAgent(self.llm_provider)
        editor = EditorAgent(self.llm_provider)
        flagged_sections: list[str] = []

        edited_sections: list[EditedSection] = list(
            await asyncio.gather(*[
                self._write_and_edit(writer, editor, so, target_keyword, flagged_sections)
                for so in grounding_pack.outline
            ])
        )

        # ── PHASE 3 — QA & ASSEMBLY (Python-first) ────────────────────────
        qa = QAAssembler(self.llm_provider)
        assembled = await qa.assemble(edited_sections, grounding_pack)
        self._emit("Blog QA Assembler", "Validate & Assemble", assembled)

        # ── PHASE 4 — APPROVER ────────────────────────────────────────────
        approver = ApproverAgent(self.llm_provider)
        approval = await approver.approve(assembled, flagged_sections=flagged_sections)
        self._emit("Blog Approver", "Final Approval", approval)

        # ── PHASE 5 — RENDER FINAL MARKDOWN ───────────────────────────────
        markdown = self.render_markdown(assembled.title, assembled.sections)

        return {
            "title": assembled.title,
            "markdown": markdown,
            "word_count": assembled.total_word_count,
            "approved": approval.approved,
            "approval_reasons": approval.reasons,
            "sections_flagged": flagged_sections,
        }

    # ── per-section write + bounded edit loop ────────────────────────────────

    async def _write_and_edit(
        self,
        writer: SectionWriterAgent,
        editor: EditorAgent,
        section_outline: SectionOutline,
        target_keyword: str,
        flagged_sections: list[str],
    ) -> EditedSection:
        # WRITE
        try:
            draft = await writer.write_section(section_outline, target_keyword)
        except Exception as exc:
            logger.error("Writer failed for %r: %s — using outline fallback", section_outline.heading, exc)
            flagged_sections.append(section_outline.heading)
            fallback_body = "\n\n".join(f"- {p}" for p in section_outline.key_points) or section_outline.intent
            return EditedSection(
                heading=section_outline.heading, revised_body=fallback_body, still_problematic=True
            )
        self._emit("Blog Writer", f"Write: {section_outline.heading}", draft)

        # EDIT LOOP — max 2 cycles
        edited: EditedSection | None = None
        for cycle in range(1, MAX_REWRITE_CYCLES + 1):
            try:
                edited = await editor.edit_section(draft, section_outline.source_snippets, cycle)
            except Exception as exc:
                logger.warning("Editor failed (cycle %d) for %r: %s", cycle, section_outline.heading, exc)
                edited = EditedSection(
                    heading=draft.heading, revised_body=draft.body_markdown, still_problematic=(cycle == MAX_REWRITE_CYCLES)
                )
            self._emit("Blog Editor", f"Edit cycle {cycle}: {section_outline.heading}", edited)

            if not edited.still_problematic:
                break
            if cycle == MAX_REWRITE_CYCLES and edited.still_problematic:
                flagged_sections.append(section_outline.heading)
                break
            # Feed the revised body back in for the next cycle.
            draft = SectionDraft(heading=edited.heading, body_markdown=edited.revised_body, claims_used=[])

        return edited

    # ── rendering ─────────────────────────────────────────────────────────────

    @staticmethod
    def render_markdown(title: str, sections: list[SectionQAResult]) -> str:
        parts = [f"# {title}", ""]
        for section in sections:
            parts.append(f"## {section.heading}")
            parts.append("")
            parts.append(section.body.strip())
            parts.append("")
        return "\n".join(parts).strip() + "\n"


# ── Standalone CLI for isolated testing ──────────────────────────────────────


def _main() -> None:
    import argparse

    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Run the 5-agent blog pipeline standalone.")
    parser.add_argument("--topic", required=True, help="Blog topic")
    parser.add_argument("--keyword", required=True, help="Target SEO keyword")
    parser.add_argument("--provider", default=None, help="LLM provider (default: settings.default_provider)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    provider = args.provider or get_settings().default_provider

    def _print_step(agent_name: str, task_name: str, output: str) -> None:
        print(f"\n=== [{agent_name}] {task_name} ===")
        print(output[:1200])

    orchestrator = BlogPipelineOrchestrator(
        llm_provider=provider, run_id="cli-test", step_callback=_print_step
    )
    result = asyncio.run(orchestrator.run(args.topic, args.keyword, user_id="cli-user"))

    print("\n" + "=" * 70)
    print(f"TITLE      : {result['title']}")
    print(f"WORD COUNT : {result['word_count']}")
    print(f"APPROVED   : {result['approved']}")
    print(f"REASONS    : {result['approval_reasons']}")
    print(f"FLAGGED    : {result['sections_flagged']}")
    print("=" * 70 + "\n")
    print(result["markdown"])


if __name__ == "__main__":
    _main()
