"""
Agent 3 — Editor.

Critiques AND fixes one section in a single call. Called once per section per
rewrite cycle (max 2 cycles, enforced by the orchestrator).

Temperature: 0.3
"""

import json
import logging

from app.services.blog_pipeline.schemas import EditedSection, SectionDraft
from app.services.blog_pipeline.style_spec import STYLE_CHECKLIST, STYLE_SPEC
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm

logger = logging.getLogger(__name__)

EDITOR_TEMPERATURE = 0.3

EDITOR_PROMPT_TEMPLATE = """
ROLE: You do exactly one thing: check one blog section against a style rubric and return a corrected version.

INPUT:
- heading: {heading}
- body_markdown: {body_markdown}
- source_snippets: {source_snippets}
- style_checklist: {style_checklist}
- rewrite_cycle: {rewrite_cycle} (current cycle number, max is 2)

RULES:
- Check body_markdown against EVERY item in style_checklist.
- For each violation: identify the exact offending text, fix it, log the fix.
- Do NOT change technical facts. Do NOT add new claims not in source_snippets.
- Do NOT restructure the section. Fix violations in place.
- If rewrite_cycle is 2 and violations still remain: set still_problematic to true and return your best attempt anyway.
- Do not remove code blocks. Do not rewrite code.
- The most important rule: if a claim in body_markdown is NOT supported by source_snippets, remove it entirely — do not replace it with a different unsupported claim.

STYLE SPEC:
{style_spec}

OUTPUT: 
You MUST output a single, valid JSON object. Do not include any explanations, prose, or markdown formatting outside of the JSON block.
Ensure your JSON starts with {{ and ends with }}.
Schema:
{schema}
```json"""

_SCHEMA_HINT = json.dumps(
    {
        "heading": "string",
        "revised_body": "string (full corrected section markdown)",
        "violations_fixed": [
            {"rule": "checklist key", "location": "offending text", "fix_applied": "what you changed"}
        ],
        "still_problematic": False,
    },
    indent=2,
)


class EditorAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, EDITOR_TEMPERATURE, max_tokens=8192)

    async def edit_section(
        self, draft: SectionDraft, source_snippets: list[str], cycle: int
    ) -> EditedSection:
        prompt = EDITOR_PROMPT_TEMPLATE.format(
            heading=draft.heading,
            body_markdown=draft.body_markdown,
            source_snippets=json.dumps(source_snippets, ensure_ascii=False),
            style_checklist=json.dumps(STYLE_CHECKLIST, ensure_ascii=False),
            rewrite_cycle=cycle,
            style_spec=STYLE_SPEC,
            schema=_SCHEMA_HINT,
        )

        edited: EditedSection = await call_llm_with_retry(
            self.llm, prompt, EditedSection,
            temperature=EDITOR_TEMPERATURE, max_retries=3, agent_name="Editor",
        )
        if not edited.heading:
            edited.heading = draft.heading
        if not edited.revised_body:
            # Never lose the section — fall back to the writer's body.
            edited.revised_body = draft.body_markdown
        return edited
