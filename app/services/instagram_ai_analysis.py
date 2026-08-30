"""
AI content-idea generation for Instagram plan items, powered by Gemini.

The router gathers a compact `context` string (the account's real synced
profile/stats/posts/hashtags, plus already-planned titles to avoid repeats) and
hands it here; this module builds a strategist prompt, calls Gemini through the
shared crewai LLM + retry helper, and returns validated, structured content
ideas the caller turns into plan items.

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


class ContentIdea(CoercingBaseModel):
    title: str
    type: str = "reel"  # "reel" | "carousel" | "single"
    caption: str = ""
    image_prompt: str = ""
    rationale: str = ""


class InstagramContentIdeas(CoercingBaseModel):
    ideas: list[ContentIdea] = Field(default_factory=list)


_SCHEMA_HINT = """{
  "ideas": [
    {"title": "concrete post working title (<12 words)",
     "type": "reel | carousel | single",
     "caption": "ready-to-post caption with 3-6 relevant hashtags",
     "image_prompt": "visual/thumbnail generation prompt matching this account's aesthetic",
     "rationale": "why this idea, grounded in the account's real data below"}
  ]
}"""

IDEA_GENERATION_PROMPT = """ROLE: You are a senior Instagram content strategist. Analyze this account's
real profile, stats, recent posts and hashtag performance, then propose {count} NEW content ideas
that are NOT duplicates of existing posts or already-planned items below.

{directives}

=== ACCOUNT DATA ===
{context}

RULES:
- Ground every idea in what already performs (best format, best hashtag category, engagement patterns).
- Do not repeat a title/topic already listed under EXISTING POSTS or ALREADY PLANNED.
- type must be one of: reel, carousel, single.
- caption must include hashtags in-line, ready to post.
- Exactly {count} ideas.

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


def _analysis_fallback(primary_model: str):
    """Backwards-compatibility stand-in LLM builder."""
    from app.llm import build_fallback_cascade
    settings = get_settings()
    _, chain = build_fallback_cascade(settings, temperature=ANALYSIS_TEMPERATURE)
    if chain:
        return chain[0][1]
    return None


def build_account_context(cached: dict, existing_items: list[dict]) -> str:
    """Plain-text account summary fed to the LLM for idea/strategy generation.

    Lives here rather than in the router because the planner's topic suggester
    grounds Instagram suggestions on exactly the same text — one description of
    the account, not two that can drift apart.

    ``existing_items`` are unified plan items (``platform='instagram'``); the
    legacy board shape carried the title under ``title`` instead of ``topic``,
    so both keys are accepted.
    """
    profile = cached.get("profile") or {}
    stats = cached.get("stats") or {}
    posts = cached.get("posts") or []
    hashtags = cached.get("hashtags") or []

    # An unmeasured metric is reported as unmeasured. Substituting 0 tells the
    # model the account got no reach, which is a different claim from "Meta did
    # not return reach for this account" — and one it will happily build a
    # strategy around.
    def measured(value, suffix: str = "") -> str:
        return "not measured" if value is None else f"{value}{suffix}"

    lines = [
        f"Handle: {profile.get('handle', 'unknown')}",
        f"Bio: {profile.get('bio', '')}",
        f"Followers: {profile.get('followers', 0)}",
        f"Avg engagement rate: {measured(profile.get('avg_engagement_rate'), '%')}",
        "",
        f"STATS ({stats.get('time_range', 'recent')}):",
        f"- Reach: {measured(stats.get('total_reach'))}, views: {measured(stats.get('total_views'))}",
        f"- Followers gained: {measured(stats.get('followers_gained'))}, "
        f"accounts engaged: {measured(stats.get('accounts_engaged'))}",
        f"- Reels published: {stats.get('total_reels_published', 0)}, "
        f"avg reel views: {measured(stats.get('avg_reel_views'))}",
        f"- Carousels published: {stats.get('total_carousels_published', 0)}, "
        f"avg carousel saves: {measured(stats.get('avg_carousel_saves'))}",
        "",
        "EXISTING POSTS:",
    ]
    for post in posts[:15]:
        lines.append(f"- ({post.get('type', 'post')}) {post.get('caption', '')[:120]}")

    lines.append("")
    lines.append("TOP HASHTAGS:")
    for tag in hashtags[:10]:
        lines.append(
            f"- {tag.get('tag', '')} (avg reach {measured(tag.get('avg_reach'))}, "
            f"{tag.get('category', '')})"
        )

    lines.append("")
    lines.append("ALREADY PLANNED:")
    for item in existing_items[:30]:
        lines.append(f"- {item.get('topic') or item.get('title') or ''}")

    return "\n".join(lines)


async def generate_board_ideas(context: str, count: int = 6, directives: str = "") -> dict:
    """New content ideas grounded in the account's real Instagram data.

    Dates are not produced here — the caller assigns scheduled_date, same
    separation of concerns as the YouTube roadmap generator.
    """
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = IDEA_GENERATION_PROMPT.format(
        count=count, context=context, schema=_SCHEMA_HINT, directives=directives
    )
    result: InstagramContentIdeas = await call_llm_with_retry(
        llm, prompt, InstagramContentIdeas,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="InstagramBoardIdeas",
        fallback_chain=fallback_chain,
        used=_used,
    )
    out = result.model_dump()
    out["model"] = _used.get("model") or model
    return out


# ── Content strategy brief ──────────────────────────────────────────────────


class FormatInsight(CoercingBaseModel):
    format: str
    reach_multiplier: str = ""
    save_multiplier: str = ""
    recommendation: str = ""


class StrategyBrief(CoercingBaseModel):
    executive_summary: str = ""
    top_performing_formats: list[FormatInsight] = Field(default_factory=list)
    viral_reel_hooks: list[str] = Field(default_factory=list)
    content_pillar_distribution: dict[str, str] = Field(default_factory=dict)


_STRATEGY_SCHEMA_HINT = """{
  "executive_summary": "2-3 sentence assessment of what's driving reach/saves for this account",
  "top_performing_formats": [
    {"format": "a specific format this account's data shows working",
     "reach_multiplier": "e.g. '3.2x' if reach-driven, else empty string",
     "save_multiplier": "e.g. '4.1x' if save-driven, else empty string",
     "recommendation": "concrete production tip for this format"}
  ],
  "viral_reel_hooks": ["5 specific opening-line hooks tailored to this account's niche and tone"],
  "content_pillar_distribution": {"pillar name": "target % of posts, e.g. '40%'"}
}"""

STRATEGY_PROMPT = """ROLE: You are a senior Instagram growth strategist writing a decisive brief for
ONE creator, grounded strictly in their real account data below.

{directives}

=== ACCOUNT DATA ({time_range}) ===
{context}

RULES:
- Reference the actual numbers (reach, engagement rate, reel vs carousel performance, hashtag
  categories) in your points — no generic advice.
- top_performing_formats: 2-3 entries, each tied to what this account's data actually shows.
- viral_reel_hooks: exactly 5, written in this account's own voice/niche, not generic templates.
- content_pillar_distribution: 3-5 pillars that reflect what this account already posts about,
  with percentages summing to roughly 100%.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_strategy(context: str, time_range: str = "30_days", directives: str = "") -> dict:
    """Account-grounded strategy brief: top formats, reel hooks, content pillars."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = STRATEGY_PROMPT.format(
        time_range=time_range, context=context, schema=_STRATEGY_SCHEMA_HINT, directives=directives
    )
    result: StrategyBrief = await call_llm_with_retry(
        llm, prompt, StrategyBrief,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="InstagramStrategy",
        fallback_chain=fallback_chain,
        used=_used,
    )
    out = result.model_dump()
    out["model"] = _used.get("model") or model
    return out


# ── Multi-week content roadmap ──────────────────────────────────────────────


class RoadmapItem(CoercingBaseModel):
    title: str
    type: str = "reel"  # "reel" | "carousel" | "single"
    tags: str = ""
    call_to_action: str = ""
    visual_prompt: str = ""


class RoadmapWeek(CoercingBaseModel):
    theme: str = ""
    items: list[RoadmapItem] = Field(default_factory=list)


class ContentRoadmap(CoercingBaseModel):
    weeks: list[RoadmapWeek] = Field(default_factory=list)


_ROADMAP_SCHEMA_HINT = """{
  "weeks": [
    {"theme": "the focus/theme for this week, grounded in the account's niche",
     "items": [
       {"title": "concrete post working title (<12 words)",
        "type": "reel | carousel | single",
        "tags": "3-6 relevant hashtags, space-separated",
        "call_to_action": "specific CTA for this post",
        "visual_prompt": "visual/thumbnail generation prompt matching this account's aesthetic"}
     ]}
  ]
}"""

ROADMAP_PROMPT = """ROLE: You are an Instagram content planner. Build a {weeks}-week posting roadmap
for ONE creator, grounded in their real account data below.

{directives}

=== ACCOUNT DATA ===
{context}

RULES:
- Produce exactly {weeks} weeks, each with a clear theme and 2 concrete post ideas.
- Bias toward formats/topics that already perform for this account.
- Titles must be specific working titles, never generic ("Intro to X").
- Do NOT include dates — they are assigned separately.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def generate_content_roadmap(context: str, weeks: int = 4, directives: str = "") -> dict:
    """A multi-week posting roadmap grounded in the account's real data (dates assigned by the caller)."""
    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = ROADMAP_PROMPT.format(
        weeks=weeks, context=context, schema=_ROADMAP_SCHEMA_HINT, directives=directives
    )
    result: ContentRoadmap = await call_llm_with_retry(
        llm, prompt, ContentRoadmap,
        temperature=ANALYSIS_TEMPERATURE, max_retries=3, agent_name="InstagramRoadmap",
        fallback_chain=fallback_chain,
        used=_used,
    )
    out = result.model_dump()
    out["model"] = _used.get("model") or model
    return out
