"""
AI analysis of YouTube channel performance, powered by a local Ollama qwen model.

The router gathers a compact `context` dict (aggregate stats, top/low performers,
traffic sources) and hands it here; this module builds a strategist prompt, calls
qwen through the shared crewai LLM + retry helper, and returns validated,
structured insights the dashboard renders as sections.
"""

import logging

from crewai import LLM
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.blog_pipeline.utils import call_llm_with_retry

logger = logging.getLogger(__name__)

ANALYSIS_TEMPERATURE = 0.4


class YoutubeAiInsights(BaseModel):
    """Structured YouTube analysis returned to the dashboard."""

    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    content_ideas: list[str] = Field(default_factory=list)


_SCHEMA_HINT = """{
  "summary": "2-3 sentence overview of channel health",
  "strengths": ["what is working, grounded in the numbers"],
  "weaknesses": ["what is underperforming, grounded in the numbers"],
  "opportunities": ["untapped angles suggested by the data"],
  "recommendations": ["concrete, prioritized next actions"],
  "content_ideas": ["specific next video titles that fit what performs"]
}"""

ANALYSIS_PROMPT = """ROLE: You are a senior YouTube growth strategist. Analyze this channel's
real performance data and produce a specific, data-grounded assessment.

=== CHANNEL DATA ({time_range}) ===
{context}

RULES:
- Reference the actual numbers (views, watch time, CTR, traffic sources) in your points.
- Be specific and actionable — no generic advice like "post consistently".
- 3-5 items per list, each one short sentence.
- content_ideas must be concrete working titles that resemble the top performers' themes.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


def _build_qwen_llm():
    """Build a crewai.LLM bound to the local Ollama qwen model."""
    settings = get_settings()
    model = settings.ollama_analysis_model
    if not model.startswith("ollama/"):
        model = f"ollama/{model}"
    kwargs = {
        "model": model,
        "base_url": settings.ollama_api_base,
        "temperature": ANALYSIS_TEMPERATURE,
    }
    logger.info("YouTube AI analysis ▸ model=%s base=%s", model, settings.ollama_api_base)
    return LLM(**kwargs), model


async def analyze_channel(context: str, time_range: str = "all_time") -> dict:
    """Run qwen over the channel context and return structured insights.

    `context` is a pre-formatted, human-readable summary of the channel's data
    (built by the router). Returns a dict: the insight fields plus `model`.
    """
    llm, model = _build_qwen_llm()
    prompt = ANALYSIS_PROMPT.format(time_range=time_range, context=context, schema=_SCHEMA_HINT)

    insights: YoutubeAiInsights = await call_llm_with_retry(
        llm,
        prompt,
        YoutubeAiInsights,
        temperature=ANALYSIS_TEMPERATURE,
        max_retries=3,
        agent_name="YouTubeAnalyst",
    )

    result = insights.model_dump()
    result["model"] = model
    return result


# ── Playlist-wise trending topics ────────────────────────────────────────────


class TrendingTopic(BaseModel):
    title: str
    rationale: str = ""
    format: str = ""  # e.g. tutorial, shorts, deep-dive, series


class PlaylistTrends(BaseModel):
    theme: str = ""
    trending_topics: list[TrendingTopic] = Field(default_factory=list)


_TRENDS_SCHEMA_HINT = """{
  "theme": "one phrase naming this playlist's core theme",
  "trending_topics": [
    {"title": "concrete next-video working title (<12 words)",
     "rationale": "one sentence: why it's trending / why it fits this channel now",
     "format": "tutorial | shorts | deep-dive | series | comparison"}
  ]
}"""

TRENDS_PROMPT = """ROLE: You are a YouTube content strategist for a specific creator. Propose the
next batch of TRENDING video topics for ONE of their playlists, grounded in both
their own recent videos and current web trends.

=== PLAYLIST: {playlist_title} ===

THEIR RECENT VIDEOS IN THIS PLAYLIST (newest first, with performance where known):
{videos}

CURRENT WEB TRENDS (live search results for this theme):
{web_context}

RULES:
- Propose 6-8 specific, concrete working titles that fit THIS playlist's theme.
- Bias toward what the web trends show is hot right now, but keep it consistent
  with what this creator already makes (don't drift off-brand).
- Each rationale must tie to either a trend from the search results or a pattern
  in their own videos.
- Titles must be specific (never "Intro to X").

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_playlist_trends(playlist_title: str, videos_block: str, web_context: str) -> dict:
    """Given a playlist's recent videos and live web-trend context, return
    structured trending next-video topic suggestions from qwen."""
    llm, model = _build_qwen_llm()
    prompt = TRENDS_PROMPT.format(
        playlist_title=playlist_title,
        videos=videos_block or "(no videos found)",
        web_context=web_context or "(no live results available)",
        schema=_TRENDS_SCHEMA_HINT,
    )
    trends: PlaylistTrends = await call_llm_with_retry(
        llm,
        prompt,
        PlaylistTrends,
        temperature=ANALYSIS_TEMPERATURE,
        max_retries=3,
        agent_name="YouTubeTrends",
    )
    result = trends.model_dump()
    result["model"] = model
    return result


# ── Channel strategy report ───────────────────────────────────────────────────


class StrategyReport(BaseModel):
    verdict: str = ""
    whats_working: list[str] = Field(default_factory=list)
    underperforming: list[str] = Field(default_factory=list)
    format_insights: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)


_STRATEGY_SCHEMA_HINT = """{
  "verdict": "2-3 sentence overall assessment of channel health & direction",
  "whats_working": ["specific strengths, grounded in the numbers"],
  "underperforming": ["specific weak spots, grounded in the numbers"],
  "format_insights": ["patterns about length / cadence / format that affect performance"],
  "content_gaps": ["topics the audience/web-trends want that this channel hasn't covered"],
  "priorities": ["ordered, concrete next actions — most important first"]
}"""

STRATEGY_PROMPT = """ROLE: You are a YouTube growth strategist writing a decisive action brief for
ONE creator, so they never need to ask a generic AI for planning again.

=== CHANNEL DATA ({time_range}) ===
{context}

=== CURRENT WEB TRENDS (live search for this channel's niche) ===
{web_context}

RULES:
- Every point must reference the creator's actual data (views, CTR, cadence,
  length buckets, specific video titles) or a concrete trend from the search.
- format_insights: call out which video LENGTHS and posting CADENCE perform best
  for THIS channel, with the numbers.
- content_gaps: use the web trends to name topics they should cover but haven't.
- priorities: 4-6 ranked, concrete actions (not "post consistently").

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_strategy(context: str, web_context: str, time_range: str = "all_time") -> dict:
    """Channel-level strategy brief: what's working, gaps, and ranked priorities."""
    llm, model = _build_qwen_llm()
    prompt = STRATEGY_PROMPT.format(
        time_range=time_range,
        context=context,
        web_context=web_context or "(no live results available)",
        schema=_STRATEGY_SCHEMA_HINT,
    )
    report: StrategyReport = await call_llm_with_retry(
        llm, prompt, StrategyReport,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="YouTubeStrategy",
    )
    result = report.model_dump()
    result["model"] = model
    return result


# ── 30-day content roadmap ────────────────────────────────────────────────────


class RoadmapItem(BaseModel):
    title: str
    format: str = ""
    theme: str = ""
    rationale: str = ""


class RoadmapWeek(BaseModel):
    focus: str = ""
    items: list[RoadmapItem] = Field(default_factory=list)


class ContentRoadmap(BaseModel):
    cadence: str = ""
    weeks: list[RoadmapWeek] = Field(default_factory=list)


_ROADMAP_SCHEMA_HINT = """{
  "cadence": "recommended posting cadence for this channel (e.g. '2 videos/week')",
  "weeks": [
    {"focus": "the theme/goal for this week",
     "items": [
       {"title": "concrete video working title (<12 words)",
        "format": "tutorial | shorts | deep-dive | series | comparison",
        "theme": "which content pillar/playlist it serves",
        "rationale": "why now — tie to a trend or the channel's data"}
     ]}
  ]
}"""

ROADMAP_PROMPT = """ROLE: You are a YouTube content planner. Build a {weeks}-week posting roadmap for
ONE creator, grounded in their real performance and current web trends.

=== CHANNEL DATA ===
{context}

=== CURRENT WEB TRENDS ===
{web_context}

RULES:
- Produce exactly {weeks} weeks. Each week has a clear focus and 2-3 concrete video ideas.
- Bias toward formats/lengths/themes that ALREADY perform for this channel, while
  weaving in the trending angles from the search results.
- Titles must be specific working titles (never "Intro to X").
- Do NOT include dates — they are assigned separately.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def generate_roadmap(context: str, web_context: str, weeks: int = 4) -> dict:
    """A multi-week posting roadmap (dates assigned by the caller)."""
    llm, model = _build_qwen_llm()
    prompt = ROADMAP_PROMPT.format(
        weeks=weeks,
        context=context,
        web_context=web_context or "(no live results available)",
        schema=_ROADMAP_SCHEMA_HINT,
    )
    roadmap: ContentRoadmap = await call_llm_with_retry(
        llm, prompt, ContentRoadmap,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="YouTubeRoadmap",
    )
    result = roadmap.model_dump()
    result["model"] = model
    return result
