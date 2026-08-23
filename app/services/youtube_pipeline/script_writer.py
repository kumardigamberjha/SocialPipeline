"""
Agent 1 — YouTube Script Writer.

Single-shot writer producing the full script in the Fireship + Hormozi style.
The style DNA comes from app.services.style_guide.YOUTUBE_SCRIPT_STYLE (shared
with the legacy CrewAI full-suite crew); the requirements block mirrors
create_script_task in app/task_factories.py.

Temperature: 0.7
"""

import json
import logging

from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.services.style_guide import YOUTUBE_SCRIPT_STYLE
from app.services.youtube_pipeline.schemas import ScriptDraft

logger = logging.getLogger(__name__)

SCRIPT_WRITER_TEMPERATURE = 0.7

SCRIPT_WRITER_PROMPT = """
ROLE: You are a YouTube script writer. Write ONE complete video script.

INPUT:
- topic: {topic}
- niche / audience: {niche}

{style}

ADDITIONAL REQUIREMENTS:
{requirements}

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose. No markdown fences.
The "script" value is the complete script as one markdown string (escape newlines as \\n).
{schema}
"""

# Full-length (7-9 min) requirements — mirrors create_script_task.
_FULL_REQUIREMENTS = """- Script length: 7-9 minutes when read aloud (~1,400-1,800 words)
- Include [VISUAL CUE: description] tags for B-roll and screen recordings
- Include [B-ROLL: description] tags for supplementary footage
- Mark energy levels: [ENERGY: HIGH] for hype sections, [ENERGY: CALM] for explanations
- Every code demo must have a [SCREEN RECORDING] tag before it
- The hook must be deliverable in under 10 seconds
- Include at least 2 pattern interrupts (questions, visual changes, energy shifts)
- Close with a value-stack CTA (Hormozi close), not a plain "subscribe" ask"""

# Short-form (YouTube Short / Reel, <60s vertical) requirements.
_SHORT_REQUIREMENTS = """- This is a SHORT vertical video (YouTube Short / Reel), UNDER 60 seconds
- Script length: ~120-220 words total. Be ruthless — one idea only.
- The hook must land in the FIRST 3 seconds (first line). No intro, no context-setting.
- Fast pace, extremely short sentences. No multi-part segments, no chapters.
- Include at least 1-2 [VISUAL CUE: description] tags for fast on-screen b-roll/text
- Mark energy with [ENERGY: HIGH]; keep it high throughout
- Deliver ONE concrete takeaway, then a single punchy CTA (e.g. "follow for more")
- Do NOT pad to fill time — a tight 90-word script is better than a loose 220-word one"""

_FULL_SCHEMA_HINT = json.dumps(
    {
        "title": "string (working video title)",
        "script": "string (the FULL 1,400-1,800 word script with all cue tags)",
    },
    indent=2,
)

_SHORT_SCHEMA_HINT = json.dumps(
    {
        "title": "string (punchy Short title)",
        "script": "string (the ~120-220 word Short script with 1-2 cue tags)",
    },
    indent=2,
)


class ScriptWriterAgent:
    def __init__(self, llm_provider: str):
        self.llm_provider = llm_provider
        self.llm = make_llm(llm_provider, SCRIPT_WRITER_TEMPERATURE, max_tokens=8192)

    async def write(self, topic: str, niche: str, video_format: str = "full") -> ScriptDraft:
        is_short = video_format == "short"
        prompt = SCRIPT_WRITER_PROMPT.format(
            topic=topic,
            niche=niche,
            # Full-length leans on the 7-min structure template; a Short must not.
            style="" if is_short else YOUTUBE_SCRIPT_STYLE,
            requirements=_SHORT_REQUIREMENTS if is_short else _FULL_REQUIREMENTS,
            schema=_SHORT_SCHEMA_HINT if is_short else _FULL_SCHEMA_HINT,
        )
        draft: ScriptDraft = await call_llm_with_retry(
            self.llm,
            prompt,
            ScriptDraft,
            temperature=SCRIPT_WRITER_TEMPERATURE,
            max_retries=3,
            agent_name="YouTubeScriptWriter",
        )
        return draft
