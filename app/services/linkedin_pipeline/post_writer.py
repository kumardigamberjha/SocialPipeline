"""
Agent 2 — Post Writer.

Writes the ENTIRE LinkedIn post in ONE call. No section loops — the post is small
enough for single-shot generation. Python (the QA checker) does all counting; this
agent only writes.

Temperature: 0.7
"""

import json
import logging

from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.services.linkedin_pipeline.schemas import AnglePack, PostDraft
from app.services.linkedin_pipeline.style_spec import LINKEDIN_STYLE_SPEC

logger = logging.getLogger(__name__)

POST_WRITER_TEMPERATURE = 0.7

POST_WRITER_PROMPT = """
# THE MANDATE
Generate a deep, highly structured, long-form LinkedIn post based on the provided INPUT. 
- WORD COUNT: Strictly between 400 and 800 words. You MUST write a deep-dive. Do not summarize.
- FORMAT: Short punchy sentences. 1-3 lines per thought maximum. Use double line breaks between every thought.

To hit the word count, you MUST follow this exact structure:
1. THE HOOK (Use the exact selected_hook provided).
2. THE STATUS QUO (Why the current industry standard is failing).
3. THE TEARDOWN (The mathematical/logical reason why it fails).
4. THE FRAMEWORK (A deep, step-by-step breakdown of the new solution).
5. THE ROI (What happens when you deploy this).
6. THE CTA (Use the requested cta_type).

INPUT:
- topic: {topic}
- selected_hook: {selected_hook}
- angle_type: {angle_type}
- cta_type: {cta_type}
- niche: {niche}

STYLE SPEC:
{style_spec}

OUTPUT: 
You MUST output a single, valid JSON object. Do not include any explanations, prose, or markdown formatting outside of the JSON block.
Ensure your JSON starts with {{ and ends with }}.
Schema:
{schema}
```json
"""

_SCHEMA_HINT = json.dumps(
    {
        "hook": "string (first 1-2 lines, same as selected_hook)",
        "body": "string (the main content, lines with blank lines between ideas)",
        "cta": "string (exactly one call to action)",
        "hashtags": ["tag1", "tag2", "tag3"],
        "full_post": "string (hook + body + cta + #hashtags, rendered with blank lines)",
    },
    indent=2,
)


def _render_full_post(draft: PostDraft) -> str:
    """Deterministically assemble the renderable post from its parts."""
    tags = " ".join(f"#{t}" for t in draft.hashtags)
    parts = [p for p in (draft.hook.strip(), draft.body.strip(), draft.cta.strip(), tags) if p]
    return "\n\n".join(parts)


class PostWriterAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, POST_WRITER_TEMPERATURE, max_tokens=4096)

    async def write(self, angle_pack: AnglePack, niche: str) -> PostDraft:
        prompt = POST_WRITER_PROMPT.format(
            topic=angle_pack.topic,
            selected_hook=angle_pack.selected_hook,
            angle_type=angle_pack.angle_type,
            cta_type=angle_pack.cta_type,
            niche=niche,
            style_spec=LINKEDIN_STYLE_SPEC,
            schema=_SCHEMA_HINT,
        )

        draft: PostDraft = await call_llm_with_retry(
            self.llm,
            prompt,
            PostDraft,
            temperature=POST_WRITER_TEMPERATURE,
            max_retries=3,
            agent_name="PostWriter",
        )

        # The model often forgets full_post or renders it without the hashtags —
        # rebuild it deterministically so the orchestrator always has clean text.
        if not draft.full_post.strip() or "#" not in draft.full_post:
            draft.full_post = _render_full_post(draft)
        return draft
