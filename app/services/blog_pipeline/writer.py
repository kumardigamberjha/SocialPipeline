"""
Agent 2 — Section Writer.

Called once PER SECTION in a loop. Deliberately small context: it only ever
sees one outline section, never the whole blog.

Temperature: 0.7
"""

import json
import logging

from app.services.blog_pipeline.schemas import SectionDraft, SectionOutline
from app.services.blog_pipeline.style_spec import STYLE_SPEC
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm

logger = logging.getLogger(__name__)

WRITER_TEMPERATURE = 0.7

WRITER_PROMPT_TEMPLATE = """
ROLE: You do exactly one thing: write one blog section in markdown.

INPUT:
- heading: {heading}
- intent: {intent}
- key_points: {key_points}
- source_snippets: {source_snippets}
- word_target: {word_target} words
- target_keyword: {target_keyword}

RULES:
- Use ONLY facts present in source_snippets. If a claim is not in source_snippets, omit it.
- Cover every item in key_points. Do not add points not in the list.
- Do not write an introduction to this section. Start immediately with the hook sentence.
- Do not summarize what you just wrote at the end of the section.
- Include the target_keyword naturally at least once.
- Write between {word_min} and {word_max} words (word_target +/- 20%).
- The most important rule: open with a concrete story, specific number, or contrarian line — never a generic opener.

STYLE:
{style_spec}

OUTPUT: Return ONLY valid JSON matching this schema. No prose. No markdown fences.
{schema}
"""

_SCHEMA_HINT = json.dumps(
    {
        "heading": "string (same as input heading)",
        "body_markdown": "string (the full section body in markdown)",
        "claims_used": ["the source_snippet text you relied on", "..."],
    },
    indent=2,
)


class SectionWriterAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, WRITER_TEMPERATURE, max_tokens=4096)

    async def write_section(self, section: SectionOutline, target_keyword: str) -> SectionDraft:
        word_min = int(section.word_target * 0.8)
        word_max = int(section.word_target * 1.2)

        prompt = WRITER_PROMPT_TEMPLATE.format(
            heading=section.heading,
            intent=section.intent,
            key_points=json.dumps(section.key_points, ensure_ascii=False),
            source_snippets=json.dumps(section.source_snippets, ensure_ascii=False),
            word_target=section.word_target,
            target_keyword=target_keyword,
            word_min=word_min,
            word_max=word_max,
            style_spec=STYLE_SPEC,
            schema=_SCHEMA_HINT,
        )

        draft: SectionDraft = await call_llm_with_retry(
            self.llm, prompt, SectionDraft,
            temperature=WRITER_TEMPERATURE, max_retries=3, agent_name="Writer",
        )
        # Keep the heading authoritative even if the model rephrased it.
        if not draft.heading:
            draft.heading = section.heading
        return draft
