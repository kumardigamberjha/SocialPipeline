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
from app.provider_tiers import UNKNOWN_GRADE
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


def _stamp_provenance(result: dict, used: dict, fallback_model: str) -> dict:
    """Record which cascade tier produced this result, on the result itself.

    ``result["model"]`` alone was not enough: it is a bare model string, so
    deciding whether a report may be exported meant pattern-matching model names
    at the export site. The grade is decided once, here, by the tier that
    answered — and defaults to ``internal_only`` when nothing answered with a
    tier stamp, so unknown provenance can never be exported.
    """
    result["model"] = used.get("model") or fallback_model
    result["tier"] = {
        "index": used.get("tier_index"),
        "name": used.get("tier_name"),
        "grade": used.get("tier_grade") or UNKNOWN_GRADE,
        "model": used.get("model") or fallback_model,
    }
    return result


import contextlib
from contextvars import ContextVar

_IS_AUDIT: ContextVar[bool] = ContextVar("_IS_AUDIT", default=False)


@contextlib.contextmanager
def audit_scope():
    token = _IS_AUDIT.set(True)
    try:
        yield
    finally:
        _IS_AUDIT.reset(token)


def _build_analysis_llm_and_chain():
    """Build the primary analysis LLM and the ordered fallback cascade.

    When ``_IS_AUDIT`` is set to True (by the channel audit page), uses the paid
    Gemini 3.8 Flash tier on the paid API key with fallback to Gemma. For general
    pages, uses the free Gemini key and model.
    """
    is_audit = _IS_AUDIT.get()
    from app.llm import build_fallback_cascade
    settings = get_settings()
    primary_llm, fallback_chain = build_fallback_cascade(
        settings,
        temperature=ANALYSIS_TEMPERATURE,
        is_audit=is_audit,
    )
    model = getattr(primary_llm, "model", None) or (settings.audit_model if is_audit else settings.analysis_model) or "gemini/gemini-3.6-flash"
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
    _stamp_provenance(result, _used, model)
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
    _stamp_provenance(result, _used, model)
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
    _stamp_provenance(result, _used, model)
    return result


# ── Channel strategy report ───────────────────────────────────────────────────

#: Appended to the directives of both models when
#: ``youtube_metrics.time_of_day_recommendation_allowed`` says this channel's
#: uploads do not carry enough publish timestamps to support an hour-level call.
#:
#: The audit used to be handed the raw hour buckets with no instruction attached,
#: and wrote "Saturday & Sunday between 09:00-12:00 UTC (2.27x channel median)"
#: onto page 1 while page 2's timing widget said, correctly, that there was not
#: enough timestamp data to name a window. Same report, same data, opposite
#: claims. The day finding is untouched by this — only the clock is.
TIME_OF_DAY_FORBIDDEN = """- TIME OF DAY IS NOT AVAILABLE FOR THIS CHANNEL. Too few of its uploads carry a
  publish timestamp to support an hour-level recommendation, and the report says
  so elsewhere. You may recommend DAYS OF THE WEEK, and you must not write a
  clock time, an hour, an hour range, a "between X and Y" window, or the letters
  UTC anywhere in your output — not in the verdict, not in format insights, not
  in the priorities, not in a rationale. Do not quote an average from a
  time-of-day breakdown as if it were a recommendation. Recommend the day and
  stop there."""

#: The counterpart when the gate is open: state the window the report computed,
#: not one derived independently.
TIME_OF_DAY_ALLOWED_NOTE = """- The upload-timing block above carries the one computed publishing window. If
  you name a time of day, name that window and no other."""


def _time_of_day_directive(allowed: bool) -> str:
    return TIME_OF_DAY_ALLOWED_NOTE if allowed else TIME_OF_DAY_FORBIDDEN



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

=== CURRENT TREND SIGNAL (external — not this channel's own data) ===
{web_context}

RULES:
- Every point must reference the creator's actual data (views, CTR, cadence,
  length buckets, upload timing, specific video titles) or a concrete item from the
  trend signal above.
- format_insights: call out which video LENGTHS, posting CADENCE, and optimal upload DAYS perform best
  for THIS channel, with the numbers. Name a time of day ONLY if the directives
  above permit it — the timing gate, not your reading of the hour buckets,
  decides whether this channel has enough timestamp data for an hour-level call.
- content_gaps: use the trend signal above to name topics this channel's audience
  wants and it has not covered. If no trend signal was supplied, derive the gaps
  from this channel's own catalogue — never from assumptions about what its
  subject area ought to be talking about.
- priorities: 4-6 concrete actions as plain strings, most important first
  (not "post consistently"). The array order carries the ranking — do not number
  them or wrap them in objects.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


async def analyze_strategy(
    context: str, web_context: str, time_range: str = "all_time", directives: str = "",
    cadence=None, time_of_day_allowed: bool = True,
) -> dict:
    """Channel-level strategy brief: what's working, gaps, and ranked priorities.

    ``cadence`` (a ``youtube_report_rules.Cadence``) is appended to the directives
    as the single permitted phrasing, because this model and the roadmap model were
    previously free to state the publishing rate independently — and did, four
    different ways in one document.

    ``time_of_day_allowed`` is the verdict of the one timing gate,
    ``youtube_metrics.time_of_day_recommendation_allowed``. When it is ``False``
    the model is told, as a hard constraint, that it may name days and not hours;
    the caller re-checks the prose afterwards, because a constraint in a prompt
    is a request, not a guarantee.
    """
    directives = f"{directives}\n{_time_of_day_directive(time_of_day_allowed)}".strip()
    if cadence is not None:
        directives = (
            f"{directives}\n"
            f"- RECOMMENDED CADENCE IS ALREADY COMPUTED: \"{cadence.label}\". State the "
            f"publishing rate only in those terms. Do not derive, round, or restate it as a "
            f"different number of days, videos per week, or releases per month."
        ).strip()
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
    _stamp_provenance(result, _used, model)
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
  "cadence": "recommended posting cadence for this channel (e.g. '1 video/week (3-4 releases/month)')",
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
ONE creator, grounded in their real performance, the strategy audit directives, and current web trends.

{directives}

=== CHANNEL DATA ===
{context}

{strategy_constraints}

{flagged_block}

=== CURRENT TREND SIGNAL (external — not this channel's own data) ===
{web_context}

RULES:
- Produce exactly {weeks} weeks.
- For each week, provide a clear focus and EXACTLY {items_per_week} concrete video release concept(s) matching the target cadence of "{target_cadence}". Do not over-schedule items.
- STRICT STRATEGY AUDIT COMPLIANCE: Every single video concept must directly advance the strategic priorities and double down on what is working.
- FORBIDDEN TOPICS & FRAMINGS: Do not propose titles, themes or framings that
  resemble anything the Strategy Audit above listed as underperforming or advised
  dropping. The audit's own bullets are the complete list — do not add categories
  it did not name, and do not assume a subject area, format or audience it did not
  describe. Every title must be concrete and specific to THIS channel's subject matter.
- JUSTIFICATION & RATIONALE RULES (MANDATORY):
  * Every item rationale MUST be anchored primarily to the channel's OWN proven performance: cite a specific named high-performing video of theirs with its view count, a winning format/length bucket, or a validated topic cluster from their catalogue.
  * An external trend may ONLY be mentioned as a secondary thematic hook, and NEVER with raw external metrics attached.
  * FORBIDDEN IN RATIONALES: never cite a number that belongs to someone else's
    platform or post — another creator's view count, subscriber count, follower
    count, star count, upvote count or launch date — and never say something "went
    viral" or "trended". If the only evidence for an idea is a third party's
    popularity, justify it from this channel's own results instead, or drop the idea.
- Titles must be specific working titles (<12 words, never "Intro to X").
- The "cadence" field in the output JSON MUST state "{target_cadence}" verbatim, and no
  rationale may state a different publishing rate. Cadence is computed from this
  channel's measured upload history; restating it differently contradicts the audit.
- Do NOT include dates, weekday names or clock times — publishing days are
  assigned separately in Python from the channel's measured history, and an hour
  may only be named when the directives above allow one.

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose, no markdown fences.
{schema}
"""


def _format_flagged_videos(flagged_videos: list[dict] | None) -> str:
    """The specific videos the roadmap may not cite as proof that something works.

    ``_format_strategy_constraints`` forwards the audit's prose bullets, which is
    not enough: a bullet reading "abstract theory underdelivers" does not stop the
    model naming a specific abstract-theory video as a proven pillar. That is what
    shipped — "I Found A Neuroscience Paper On Messi's Brain" (213,644 views) was
    listed as underperforming on page 1 and cited as a "high-engagement brain
    research pillar" on page 3. So the titles go in as data.
    """
    if not flagged_videos:
        return ""
    rows = "\n".join(
        f"  * {v.get('title', '')} — {int(v.get('views') or 0):,} views"
        for v in flagged_videos[:15]
    )
    return (
        "=== VIDEOS FLAGGED UNDERPERFORMING (DO NOT CITE AS POSITIVE EVIDENCE) ===\n"
        f"{rows}\n"
        "  --> ABSOLUTE RULE: none of the videos above may be referenced as a proven\n"
        "      pillar, a success, a 'high-engagement' format, or a reason to make more\n"
        "      of anything. They are the channel's weakest results. If a rationale would\n"
        "      cite one of them as evidence, make a different point or drop the concept.\n"
        "  --> Do not propose concepts that match the framings the audit told this\n"
        "      channel to abandon, even under a new title."
    )


def _format_strategy_constraints(
    audit_strategy: dict | None, target_cadence: str, items_per_week: int, weeks: int = 4
) -> str:
    if not audit_strategy:
        return (
            f"=== TARGET CADENCE ===\n"
            f"- Recommended Cadence: {target_cadence}\n"
            f"- Video Count Target: EXACTLY {items_per_week} primary video concept per week."
        )

    sections = [
        "=== STRATEGY AUDIT DIRECTIVES & CONSTRAINTS (MANDATORY COHERENCE WITH PAGE 1) ===",
        "This roadmap MUST be 100% coherent with the Strategy Audit findings on Page 1 of the report:",
    ]

    under = audit_strategy.get("underperforming") or []
    if under:
        under_bullets = "\n".join(f"  * {u}" for u in under)
        sections.append(
            f"1. FORBIDDEN / UNDERPERFORMING FRAMINGS TO DROP (DO NOT PROPOSE):\n{under_bullets}\n"
            f"  --> MANDATORY NEGATIVE CONSTRAINT: NEVER propose a video title or theme that uses "
            f"one of the framings listed immediately above, or a synonym or light rewording of one. "
            f"That list is the complete definition of what is banned here: do not generalise it into "
            f"a whole subject area, and do not ban anything it does not name. Replace each dropped "
            f"framing with a concrete, specific, audience-facing treatment of the SAME subject "
            f"matter this channel already covers."
        )

    ww = audit_strategy.get("whats_working") or []
    if ww:
        ww_bullets = "\n".join(f"  * {w}" for w in ww)
        sections.append(f"2. CORE WINNING FORMATS & TOPICS TO SCALE:\n{ww_bullets}")

    gaps = audit_strategy.get("content_gaps") or []
    if gaps:
        gap_bullets = "\n".join(f"  * {g}" for g in gaps)
        sections.append(f"3. IDENTIFIED AUDIENCE CONTENT GAPS:\n{gap_bullets}")

    fmt = audit_strategy.get("format_insights") or []
    if fmt:
        fmt_bullets = "\n".join(f"  * {f}" for f in fmt)
        sections.append(f"4. FORMAT & CADENCE RULES:\n{fmt_bullets}")

    pri = audit_strategy.get("priorities") or []
    if pri:
        pri_bullets = "\n".join(f"  {idx+1}. {p}" for idx, p in enumerate(pri))
        sections.append(
            f"5. RANKED STRATEGIC PRIORITIES:\n{pri_bullets}\n"
            f"  --> MANDATORY RULE: The {weeks}-week roadmap must directly execute these priorities in order."
        )

    sections.append(
        f"6. CADENCE & SCHEDULE VOLUME TARGET:\n"
        f"  - Target Cadence: {target_cadence}\n"
        f"  - Weekly Release Count: EXACTLY {items_per_week} primary video idea per week "
        f"({items_per_week * weeks} videos total across {weeks} weeks). "
        f"Do NOT over-schedule or list more videos than the target cadence."
    )
    return "\n\n".join(sections)


async def generate_roadmap(
    context: str,
    web_context: str,
    weeks: int = 4,
    directives: str = "",
    audit_strategy: dict | None = None,
    upload_timing: dict | None = None,
    cadence=None,
    flagged_videos: list[dict] | None = None,
    violation_note: str = "",
    time_of_day_allowed: bool | None = None,
) -> dict:
    """A multi-week posting roadmap (dates assigned by the caller).

    ``cadence`` is a ``youtube_report_rules.Cadence`` and is the only authority on
    how many items to produce and what rate to state. This function used to derive
    its own from ``uploads_per_week``/``upload_frequency`` literals while the audit
    model independently wrote a different rate into its own prose — that is how one
    report managed to claim an 8-10 day loop, 3-4 releases a month, one documentary
    a week, and then list eight videos across four weeks.

    ``violation_note`` is set on a regeneration pass to quote the model's previous
    breach back at it.

    ``time_of_day_allowed`` defaults to the gate's verdict for ``upload_timing``;
    when it is false the roadmap may schedule days but never hours.
    """
    from app.services.youtube_metrics import timing_allows_time_of_day
    from app.services.youtube_report_rules import Cadence, compute_cadence

    if cadence is None:
        cadence = compute_cadence({}, upload_timing)
    assert isinstance(cadence, Cadence)

    # Scheduling notes are prose too, and a roadmap rationale naming an hour
    # contradicts page 2 exactly as loudly as a priority does. Default read from
    # the timing block this call was already given, so a caller cannot forget.
    if time_of_day_allowed is None:
        time_of_day_allowed = timing_allows_time_of_day(upload_timing)
    directives = f"{directives}\n{_time_of_day_directive(time_of_day_allowed)}".strip()

    items_per_week = cadence.items_per_week
    target_cadence = cadence.label

    strategy_constraints = _format_strategy_constraints(
        audit_strategy, target_cadence=target_cadence, items_per_week=items_per_week,
        weeks=weeks,
    )
    flagged_block = _format_flagged_videos(flagged_videos)
    if violation_note:
        flagged_block = f"{flagged_block}\n\n{violation_note}".strip()

    llm, fallback_chain, model = _build_analysis_llm_and_chain()
    _used: dict = {}  # filled in with the tier that actually answered
    prompt = ROADMAP_PROMPT.format(
        weeks=weeks,
        context=context,
        strategy_constraints=strategy_constraints,
        flagged_block=flagged_block,
        target_cadence=target_cadence,
        items_per_week=items_per_week,
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

    # The cadence the report displays is computed, never quoted from the model —
    # it is rendered verbatim in the roadmap header and the PDF.
    result["cadence"] = cadence.label

    # Trim over-scheduling rather than letting the item count become a fifth,
    # contradicting statement of the cadence.
    for week in result.get("weeks") or []:
        items = week.get("items") or []
        if len(items) > items_per_week:
            week["items"] = items[:items_per_week]

    _stamp_provenance(result, _used, model)
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
