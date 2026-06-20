"""
Agent 4 — QA / Assembler.

MOSTLY Python. All counting, arithmetic, and validation is deterministic Python
— no model is ever asked to count words or check headings. The LLM is called
ONLY to expand a section that Python flagged as thin.

Temperature for thin-section rewrite: 0.5
"""

import json
import logging
import re

from pydantic import BaseModel, Field

from app.services.blog_pipeline.schemas import (
    AssembledDraft,
    EditedSection,
    GroundingPack,
    SectionOutline,
    SectionQAResult,
)
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm

logger = logging.getLogger(__name__)

THIN_REWRITE_TEMPERATURE = 0.5
_THIN_RATIO = 0.8  # word_count < word_target * 0.8 => thin

THIN_SECTION_REWRITE_PROMPT = """
ROLE: You do exactly one thing: expand a thin blog section to meet its word target.

INPUT:
- heading: {heading}
- current_body: {current_body}
- word_target: {word_target}
- current_word_count: {current_word_count}
- words_needed: {words_needed}
- source_snippets: {source_snippets}
- target_keyword: {target_keyword}

RULES:
- Add content by expanding existing points with more detail, code examples, or real-world context.
- Use ONLY facts from source_snippets for any new claims.
- Do not add a new heading. Do not restructure. Expand in place.
- Preserve all existing code blocks exactly as written.
- The most important rule: return the COMPLETE expanded section, not just the additions.

OUTPUT: Return ONLY valid JSON: {{"heading": "...", "body_markdown": "...", "word_count_estimate": N}}
No prose. No markdown fences.
"""


class _ThinRewrite(BaseModel):
    heading: str = ""
    body_markdown: str
    word_count_estimate: int = Field(default=0)


class QAAssembler:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, THIN_REWRITE_TEMPERATURE, max_tokens=4096)

    # ── Python-only helpers (NO LLM) ─────────────────────────────────────────

    @staticmethod
    def count_words(text: str) -> int:
        return len((text or "").split())

    @staticmethod
    def count_keyword(text: str, keyword: str) -> int:
        if not text or not keyword:
            return 0
        return len(re.findall(re.escape(keyword), text, flags=re.IGNORECASE))

    @staticmethod
    def check_headings(text: str) -> int:
        """Count H2 (##) and H3 (###) heading lines."""
        return len(re.findall(r"^\s{0,3}#{2,3}\s+\S", text or "", flags=re.MULTILINE))

    @staticmethod
    def count_h3(text: str) -> int:
        return len(re.findall(r"^\s{0,3}###\s+\S", text or "", flags=re.MULTILINE))

    @staticmethod
    def flag_thin_section(word_count: int, word_target: int) -> bool:
        return word_count < max(1, word_target) * _THIN_RATIO

    def calculate_keyword_density(self, full_text: str, keyword: str) -> float:
        total = self.count_words(full_text)
        if total == 0:
            return 0.0
        return (self.count_keyword(full_text, keyword) / total) * 100

    @staticmethod
    def validate_structure(sections: list[EditedSection]) -> list[str]:
        """Return a list of structural problems (empty list = clean)."""
        problems: list[str] = []
        if not sections:
            return ["no sections produced"]

        first = sections[0].heading.lower()
        if "intro" not in first and "introduction" not in first and "overview" not in first:
            problems.append(f"missing introduction (first heading: {sections[0].heading!r})")

        last = sections[-1].heading.lower()
        if not any(k in last for k in ("conclusion", "summary", "next", "wrap")):
            problems.append(f"missing conclusion (last heading: {sections[-1].heading!r})")

        seen: set[str] = set()
        for s in sections:
            if not (s.revised_body or "").strip():
                problems.append(f"empty section: {s.heading!r}")
            key = s.heading.strip().lower()
            if key in seen:
                problems.append(f"duplicate heading: {s.heading!r}")
            seen.add(key)
        return problems

    # ── LLM method (only when a section is thin) ─────────────────────────────

    async def rewrite_thin_section(
        self, section: EditedSection, outline_section: SectionOutline, keyword: str
    ) -> EditedSection:
        current = section.revised_body
        current_wc = self.count_words(current)
        words_needed = max(0, outline_section.word_target - current_wc)

        prompt = THIN_SECTION_REWRITE_PROMPT.format(
            heading=section.heading,
            current_body=current,
            word_target=outline_section.word_target,
            current_word_count=current_wc,
            words_needed=words_needed,
            source_snippets=json.dumps(outline_section.source_snippets, ensure_ascii=False),
            target_keyword=keyword,
        )

        try:
            rewrite: _ThinRewrite = await call_llm_with_retry(
                self.llm, prompt, _ThinRewrite,
                temperature=THIN_REWRITE_TEMPERATURE, max_retries=3, agent_name="QA-ThinRewrite",
            )
        except Exception as exc:
            # Expansion failed — keep the original body rather than dropping the section.
            logger.warning("Thin-section rewrite failed for %r: %s", section.heading, exc)
            return section

        return EditedSection(
            heading=section.heading,
            revised_body=rewrite.body_markdown or current,
            violations_fixed=section.violations_fixed,
            still_problematic=section.still_problematic,
        )

    # ── Main assembly ────────────────────────────────────────────────────────

    async def assemble(
        self, edited_sections: list[EditedSection], grounding_pack: GroundingPack
    ) -> AssembledDraft:
        keyword = grounding_pack.target_keyword
        outline_by_heading = {o.heading.strip().lower(): o for o in grounding_pack.outline}
        # Positional fallback so a renamed heading still maps to its word_target.
        outline_list = list(grounding_pack.outline)

        qa_results: list[SectionQAResult] = []
        thin_headings: list[str] = []

        for idx, section in enumerate(edited_sections):
            outline = outline_by_heading.get(section.heading.strip().lower())
            if outline is None and idx < len(outline_list):
                outline = outline_list[idx]
            word_target = outline.word_target if outline else 500

            body = section.revised_body
            word_count = self.count_words(body)              # Python
            thin = self.flag_thin_section(word_count, word_target)  # Python

            # One LLM expansion attempt per thin section, then re-count (Python).
            if thin and outline is not None:
                section = await self.rewrite_thin_section(section, outline, keyword)
                body = section.revised_body
                word_count = self.count_words(body)
                thin = self.flag_thin_section(word_count, word_target)

            qa_results.append(
                SectionQAResult(
                    heading=section.heading,
                    body=body,
                    word_count=word_count,                                  # Python
                    keyword_present=self.count_keyword(body, keyword) > 0,  # Python
                    thin_flag=thin,
                    h3_count=self.count_h3(body),                           # Python
                    rewrite_needed=thin,
                )
            )
            if thin:
                thin_headings.append(section.heading)

        total_words = sum(r.word_count for r in qa_results)  # Python sum()
        full_text = "\n\n".join(r.body for r in qa_results)
        density = self.calculate_keyword_density(full_text, keyword)  # Python

        problems = self.validate_structure(edited_sections)
        if problems:
            logger.warning("Structural problems detected: %s", problems)

        return AssembledDraft(
            title=grounding_pack.title,
            target_keyword=keyword,
            sections=qa_results,
            total_word_count=total_words,
            thin_sections=thin_headings,
            keyword_density=round(density, 3),
        )
