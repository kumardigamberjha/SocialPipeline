"""
AI analysis of YouTube channel performance, powered by Gemini 3.6 Flash.

The router gathers a compact `context` dict (aggregate stats, top/low performers,
traffic sources) and hands it here; this module builds a strategist prompt, calls
Gemini through the shared crewai LLM + retry helper, and returns validated,
structured insights the dashboard renders as sections.

When Gemini is overloaded (its 503 "high demand" answer) the retry helper
switches to the NVIDIA NIM fallback model rather than failing the request —
see `_analysis_fallback` and `settings.analysis_fallback_model`.
"""

import logging

from crewai import LLM
from pydantic import Field

from app.config import get_settings
from app.llm import build_llm
from app.services.blog_pipeline.utils import CoercingBaseModel, call_llm_with_retry

logger = logging.getLogger(__name__)

ANALYSIS_TEMPERATURE = 0.4


class YoutubeAiInsights(CoercingBaseModel):
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

{directives}

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


def _build_analysis_llm_and_chain():
    """Build the primary analysis LLM (Gemini) and the 4-tier fallback cascade:
      Tier 1: Google Gemini Flash
      Tier 2: NVIDIA DeepSeek AI (NVIDIA NIM)
      Tier 3: Ollama Cloud (gemma4:31b-cloud)
      Tier 4: Local Ollama (qwen2.5:latest)
    """
    from app.llm import build_fallback_cascade
    settings = get_settings()
    # These prompts all return a compact JSON report, so the default
    # settings.llm_max_tokens is ample. The old 16384 was passed into a
    # parameter build_fallback_cascade ignored; now that it is honoured, a
    # ceiling that high just invites a long chain-of-thought from the slower
    # tiers and blows the cascade deadline.
    primary_llm, fallback_chain = build_fallback_cascade(
        settings,
        temperature=ANALYSIS_TEMPERATURE,
    )
    model = getattr(primary_llm, "model", None) or settings.analysis_model or "gemini/gemini-2.5-flash"
    return primary_llm, fallback_chain, model


_build_analysis_llm = _build_analysis_llm_and_chain
_build_qwen_llm = _build_analysis_llm_and_chain


def _analysis_fallback(primary_model: str):
    """Backwards-compatibility stand-in LLM builder."""
    from app.llm import build_fallback_cascade
    settings = get_settings()
    _, chain = build_fallback_cascade(settings, temperature=ANALYSIS_TEMPERATURE)
    if chain:
        return chain[0][1]
    return None


async def analyze_channel(context: str, time_range: str = "all_time", directives: str = "") -> dict:
    """Run AI analysis over the channel context and return structured insights.

    `context` is a pre-formatted, human-readable summary of the channel's data
    (built by the router). `directives` is the user's Personal Intelligence
    block (rules + goals) — see app.services.personal_intelligence — and
    defaults to "" so existing call sites keep working unchanged.
    Returns a dict: the insight fields plus `model`.
    """
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = ANALYSIS_PROMPT.format(
        time_range=time_range, context=context, schema=_SCHEMA_HINT, directives=directives
    )

    insights: YoutubeAiInsights = await call_llm_with_retry(
        llm,
        prompt,
        YoutubeAiInsights,
        temperature=ANALYSIS_TEMPERATURE,
        max_retries=3,
        agent_name="YouTubeAnalyst",
        fallback_chain=fallback_chain,
        used=_used,
    )

    result = insights.model_dump()
    result["model"] = _used.get("model") or model
    return result


# ── Playlist-wise trending topics ────────────────────────────────────────────


class TrendingTopic(CoercingBaseModel):
    title: str
    rationale: str = ""
    format: str = ""  # e.g. tutorial, shorts, deep-dive, series


class PlaylistTrends(CoercingBaseModel):
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

{directives}

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


async def analyze_playlist_trends(
    playlist_title: str, videos_block: str, web_context: str, directives: str = ""
) -> dict:
    """Given a playlist's recent videos and live web-trend context, return
    structured trending next-video topic suggestions from Gemini Flash (with cascade fallback)."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = TRENDS_PROMPT.format(
        playlist_title=playlist_title,
        videos=videos_block or "(no videos found)",
        web_context=web_context or "(no live results available)",
        schema=_TRENDS_SCHEMA_HINT,
        directives=directives,
    )
    trends: PlaylistTrends = await call_llm_with_retry(
        llm,
        prompt,
        PlaylistTrends,
        temperature=ANALYSIS_TEMPERATURE,
        max_retries=3,
        agent_name="YouTubeTrends",
        fallback_chain=fallback_chain,
        used=_used,
    )
    result = trends.model_dump()
    result["model"] = _used.get("model") or model
    return result


# ── Per-video growth recommendations ──────────────────────────────────────────


class VideoGrowthRecommendations(CoercingBaseModel):
    verdict: str = ""
    title_options: list[str] = Field(default_factory=list)
    thumbnail_ideas: list[str] = Field(default_factory=list)
    hook_rewrite: str = ""
    description_fixes: list[str] = Field(default_factory=list)
    tag_fixes: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)


_VIDEO_GROWTH_SCHEMA_HINT = """{
  "verdict": "2-3 sentences: how this video is actually doing and why, grounded in its real numbers",
  "title_options": ["3-5 rewritten titles that would likely lift CTR, each under 70 chars"],
  "thumbnail_ideas": ["3-5 concrete thumbnail concepts (subject, expression, text overlay, contrast) that fit current trends"],
  "hook_rewrite": "a rewritten first 5-10 seconds script/hook to reduce early drop-off",
  "description_fixes": ["specific description/SEO fixes"],
  "tag_fixes": ["specific tag additions or removals"],
  "priority_actions": ["the 3 highest-impact fixes to do first, ranked"]
}"""

VIDEO_GROWTH_PROMPT = """ROLE: You are a senior YouTube growth strategist. A creator wants concrete,
specific fixes to grow VIEWS and CTR for ONE video. Do not give generic advice —
every suggestion must be tied to this video's real data or a current trend below.

{directives}

=== VIDEO DATA ===
{video_context}

=== CURRENT WEB TRENDS (live search, for title/thumbnail ideas) ===
{web_context}

RULES:
- If real CTR/impressions data is present, diagnose using it (e.g. low CTR with
  high average-view-% means the thumbnail/title under-sells a video that
  retains well; the reverse means the title over-promises).
- If CTR data says "not synced", reason from title length/structure, tag count,
  description quality, and the video's format/niche instead — say so, don't
  invent a CTR number.
- title_options and thumbnail_ideas must reflect what the web trends show is
  working right now, adapted to this video's actual topic — never generic
  ("Ultimate Guide", "You Won't Believe").
- priority_actions must be ranked, most-impactful first.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_video_growth(video_context: str, web_context: str, directives: str = "") -> dict:
    """Per-video CTR/views growth recommendations, grounded in that video's
    real stats (and real CTR when synced) plus live web trends."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = VIDEO_GROWTH_PROMPT.format(
        video_context=video_context,
        web_context=web_context or "(no live results available)",
        schema=_VIDEO_GROWTH_SCHEMA_HINT,
        directives=directives,
    )
    recs: VideoGrowthRecommendations = await call_llm_with_retry(
        llm,
        prompt,
        VideoGrowthRecommendations,
        temperature=ANALYSIS_TEMPERATURE,
        max_retries=3,
        agent_name="YouTubeVideoGrowth",
        fallback_chain=fallback_chain,
        used=_used,
    )
    result = recs.model_dump()
    result["model"] = _used.get("model") or model
    return result


# ── Channel strategy report ───────────────────────────────────────────────────


class StrategyReport(CoercingBaseModel):
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
}

Every array above is an array of PLAIN STRINGS. Do not wrap items in objects and
do not add a "priority", "rank", or "action" field — the order of the array is
the ranking."""

STRATEGY_PROMPT = """ROLE: You are a YouTube growth strategist writing a decisive action brief for
ONE creator, so they never need to ask a generic AI for planning again.

{directives}

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
- priorities: 4-6 concrete actions as plain strings, most important first
  (not "post consistently"). The array order carries the ranking — do not number
  them or wrap them in objects.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_strategy(
    context: str, web_context: str, time_range: str = "all_time", directives: str = ""
) -> dict:
    """Channel-level strategy brief: what's working, gaps, and ranked priorities."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = STRATEGY_PROMPT.format(
        time_range=time_range,
        context=context,
        web_context=web_context or "(no live results available)",
        schema=_STRATEGY_SCHEMA_HINT,
        directives=directives,
    )
    report: StrategyReport = await call_llm_with_retry(
        llm, prompt, StrategyReport,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="YouTubeStrategy",
        fallback_chain=fallback_chain,
        used=_used,
    )
    result = report.model_dump()
    result["model"] = _used.get("model") or model
    return result


# ── 30-day content roadmap ────────────────────────────────────────────────────


class RoadmapItem(CoercingBaseModel):
    title: str
    format: str = ""
    theme: str = ""
    rationale: str = ""


class RoadmapWeek(CoercingBaseModel):
    focus: str = ""
    items: list[RoadmapItem] = Field(default_factory=list)


class ContentRoadmap(CoercingBaseModel):
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

{directives}

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


async def generate_roadmap(
    context: str, web_context: str, weeks: int = 4, directives: str = ""
) -> dict:
    """A multi-week posting roadmap (dates assigned by the caller)."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = ROADMAP_PROMPT.format(
        weeks=weeks,
        context=context,
        web_context=web_context or "(no live results available)",
        schema=_ROADMAP_SCHEMA_HINT,
        directives=directives,
    )
    roadmap: ContentRoadmap = await call_llm_with_retry(
        llm, prompt, ContentRoadmap,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="YouTubeRoadmap",
        fallback_chain=fallback_chain,
        used=_used,
    )
    result = roadmap.model_dump()
    result["model"] = _used.get("model") or model
    return result


# ── Competitor discovery ──────────────────────────────────────────────────────


class CompetitorCandidate(CoercingBaseModel):
    name: str
    handle: str = ""       # "@handle", if the model knows it — makes verification 1 quota unit
    channel_id: str = ""   # "UC...", if the model knows it — skips verification entirely
    why: str = ""
    tier: str = "peer"     # peer | aspirational | adjacent


class CompetitorCandidatePack(CoercingBaseModel):
    candidates: list[CompetitorCandidate] = Field(default_factory=list)


_COMPETITOR_SCHEMA_HINT = """{
  "candidates": [
    {"name": "channel name", "handle": "@handle (if known, else empty string)",
     "channel_id": "UC... (if known, else empty string)",
     "why": "one sentence: why this channel is a real competitor in this niche",
     "tier": "peer | aspirational | adjacent"}
  ]
}"""

COMPETITOR_DISCOVERY_PROMPT = """ROLE: You are a YouTube competitive-research analyst. Propose real, currently
active YouTube channels that compete with this creator's channel in their niche.

=== THIS CREATOR'S CHANNEL ===
{own_context}

=== NICHE ===
{niche}

=== CURRENT WEB CONTEXT (live search) ===
{web_context}

=== ALREADY TRACKED — DO NOT PROPOSE ANY OF THESE AGAIN ===
{exclude_block}

RULES:
- Propose exactly {count} channels. Every one must be a REAL, currently active YouTube channel —
  never invent a channel name. If you are not confident a channel is real, do not include it.
- Prefer channels you can name a "@handle" or a "UC..." channel_id for — leave the field empty
  string only when you genuinely don't know it, since that costs the caller far more to verify.
- Do not propose anything in the DO-NOT-PROPOSE list above, or anything that closely resembles it.
- tier: "peer" = similar size/niche, "aspirational" = bigger channel to learn from,
  "adjacent" = overlapping audience but a different core topic.
- why must be specific to this channel's actual content, not generic ("popular in AI").

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def propose_competitors(
    own_context: str, niche: str, web_context: str, exclude_names: list[str],
    count: int = 40, directives: str = "",
) -> list[dict]:
    """Ask the LLM for candidate competitor channels. Nothing here is verified —
    the caller (app.services.youtube_competitor) must confirm every candidate
    against the real YouTube Data API before it is ever persisted."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    exclude_block = "\n".join(f"- {n}" for n in exclude_names[:150]) or "(none yet)"
    if len(exclude_names) > 150:
        exclude_block += f"\n(and {len(exclude_names) - 150} more already tracked)"

    prompt = COMPETITOR_DISCOVERY_PROMPT.format(
        own_context=own_context or "(no synced channel data)",
        niche=niche or "(unspecified — infer from the channel data above)",
        web_context=web_context or "(no live results available)",
        exclude_block=exclude_block,
        count=count,
        schema=_COMPETITOR_SCHEMA_HINT,
        directives=directives,
    )
    pack: CompetitorCandidatePack = await call_llm_with_retry(
        llm, prompt, CompetitorCandidatePack,
        temperature=0.6, max_retries=3, agent_name="YouTubeCompetitorDiscovery",
        fallback_chain=fallback_chain,
        used=_used,
    )
    return [c.model_dump() for c in pack.candidates]
