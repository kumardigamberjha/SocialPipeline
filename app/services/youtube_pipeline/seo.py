"""
Agent 2 — YouTube SEO packer. Produces title / description / tags from the
finished script. Runs at a lower temperature than the writer.

Temperature: 0.5
"""

import json
import logging

from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.services.youtube_pipeline.schemas import SeoPack

logger = logging.getLogger(__name__)

SEO_TEMPERATURE = 0.5

SEO_PROMPT = """
ROLE: You are a YouTube SEO specialist. Produce SEO metadata for ONE video.

INPUT:
- topic: {topic}
- script excerpt (first 1500 chars): {excerpt}

RULES:
- seo_title: under 70 characters, keyword-front-loaded, curiosity without clickbait lies.
- seo_description: 2-4 sentences with the main keyword in sentence one, then a
  short value summary. End with "Timestamps below." (creator fills them later).
- seo_tags: 10-15 tags, mix of broad and specific, no '#' prefix.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose. No markdown fences.
{schema}
"""

_SCHEMA_HINT = json.dumps(
    {
        "seo_title": "string (<70 chars)",
        "seo_description": "string",
        "seo_tags": ["tag1", "tag2", "..."],
    },
    indent=2,
)


class SeoAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, SEO_TEMPERATURE, max_tokens=1024)

    async def run(self, topic: str, script_excerpt: str) -> SeoPack:
        prompt = SEO_PROMPT.format(topic=topic, excerpt=script_excerpt[:1500], schema=_SCHEMA_HINT)
        pack: SeoPack = await call_llm_with_retry(
            self.llm,
            prompt,
            SeoPack,
            temperature=SEO_TEMPERATURE,
            max_retries=3,
            agent_name="YouTubeSeoAgent",
        )
        return pack
