"""
AI topic suggester for content plans.

One LLM call proposes a period's worth of video topics for a niche, primed with
the user's recent history (published_topics in content_tracker.db + recent
plan_items in nexus.db) as a DO-NOT-REPEAT list, plus a real account-context
block (recent plan topics, else synced YouTube videos, else synced Instagram
posts) so suggestions stay grounded in what this channel actually makes rather
than drifting off-topic from the free-text niche alone. Suggestions are then
post-filtered through content_tracker.is_duplicate_topic; dates are assigned in
Python (spread evenly across the period), never by the LLM.
"""

import asyncio
import calendar
import json
import logging
from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.db import content_tracker, queries
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm
from app.services.personal_intelligence import get_directives

logger = logging.getLogger(__name__)

SUGGESTER_TEMPERATURE = 0.8

# Most ideas one Instagram generation round will ask for.
MAX_INSTAGRAM_IDEAS = 10


class NotSyncedError(RuntimeError):
    """The platform has no synced data to ground suggestions in."""


# Fraction of suggestions allowed to be dropped as duplicates before we ask the
# LLM once more for replacements.
MAX_DROP_RATIO = 0.2


class _TopicIdea(BaseModel):
    topic: str
    rationale: str = ""
    # Platform-specific extras that survive into plan_items.meta — Instagram's
    # type/caption/image_prompt, empty for YouTube.
    meta: dict = Field(default_factory=dict)


class _TopicPack(BaseModel):
    topics: list[_TopicIdea] = Field(default_factory=list)


SUGGESTER_PROMPT = """
ROLE: You plan video/content topics for a solo creator. Propose exactly {count} topics.

{directives}

INPUT:
- niche / audience: {niche}
- period: {plan_type} starting {start_date}

=== ACCOUNT CONTEXT ===
{channel_context}

=== TACTICS FOR THIS PERIOD'S ACTIVE GOAL (live web research, may be empty) ===
{goal_research}

RULES:
- Every topic must be a concrete, specific video idea — never generic ("intro to AI" is banned).
- Mix formats across the set: tutorials, contrarian takes, case studies, tool comparisons, lessons learned.
- Each topic must be phrased as a working title (under 15 words).
- rationale: one short sentence on why it would perform now.
- Ground every topic in the account context above when it is not empty — stay
  strictly within that channel's real subject matter. Never propose a topic
  outside the stated niche just because it sounds generically popular.
- DO NOT repeat, rephrase, or closely resemble ANY of these already-covered topics:
{recent_topics}

OUTPUT: Return ONLY valid JSON matching this schema exactly. No prose. No markdown fences.
{schema}
"""

_SCHEMA_HINT = json.dumps(
    {"topics": [{"topic": "working title (<15 words)", "rationale": "one sentence"}]},
    indent=2,
)


def _period_bounds(plan_type: str, start: date) -> tuple[date, int]:
    """Return (end_date, suggested_topic_count) for the plan period."""
    if plan_type == "weekly":
        return start + timedelta(days=6), 7
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    return start + timedelta(days=days_in_month - 1), 12


def spread_dates(start: date, end: date, count: int) -> list[date]:
    """Spread `count` dates evenly across [start, end], deterministic."""
    if count <= 0:
        return []
    total_days = (end - start).days
    if count == 1:
        return [start]
    return [start + timedelta(days=round(i * total_days / (count - 1))) for i in range(count)]


async def _gather_recent_topics(session, user_id: str, platform: str = "youtube") -> list[str]:
    seen: list[str] = []
    try:
        seen += [t["topic_original"] for t in content_tracker.get_recent_topics(limit=40)]
    except Exception as exc:  # tracker DB is best-effort context
        logger.warning("content_tracker history unavailable: %s", exc)
    try:
        seen += await queries.get_recent_plan_topics(session, user_id, days=90, platform=platform)
    except Exception as exc:
        logger.warning("plan topic history unavailable: %s", exc)
    # Dedup while preserving order.
    return list(dict.fromkeys(seen))


async def _gather_channel_context(session, user_id: str, platform: str = "youtube") -> str:
    """Real account grounding, first non-empty source wins: past plans, then
    synced YouTube videos, then synced Instagram posts.
    """
    try:
        recent_plan_topics = await queries.get_recent_plan_topics(session, user_id, days=90, platform=platform)
        if recent_plan_topics:
            block = "\n".join(f"- {t}" for t in recent_plan_topics[:20])
            return f"Recently planned/published topics for this channel:\n{block}"
    except Exception as exc:
        logger.warning("plan topic context unavailable: %s", exc)

    try:
        videos = await queries.get_recent_youtube_titles(session, user_id, limit=12)
        if videos:
            lines = []
            for v in videos:
                tags = ", ".join(v["tags"] or []) if v.get("tags") else ""
                lines.append(f"- {v['title']}" + (f" [tags: {tags}]" if tags else ""))
            return "Channel's actual YouTube videos:\n" + "\n".join(lines)
    except Exception as exc:
        logger.warning("YouTube context unavailable: %s", exc)

    try:
        from app.services.instagram_cache import get_cached_instagram_data

        cached = get_cached_instagram_data(user_id)
        if cached and (cached.get("profile") or cached.get("posts")):
            profile = cached.get("profile") or {}
            posts = cached.get("posts") or []
            lines = []
            bio = profile.get("bio")
            if bio:
                lines.append(f"Bio: {bio}")
            for p in posts[:10]:
                title = p.get("title") or p.get("caption") or ""
                if title:
                    lines.append(f"- {title[:120]}")
            if lines:
                return "Instagram bio & recent posts:\n" + "\n".join(lines)
    except Exception as exc:
        logger.warning("Instagram context unavailable: %s", exc)

    return ""


async def _gather_goal_research(session, user_id: str, niche: str) -> str:
    """Live web research on the user's nearest active goal, for goal-aware plans.

    Best-effort: an empty string here just means the prompt's TACTICS section
    reads "(no active goal, or research unavailable)" — never fatal to plan
    generation.
    """
    try:
        goals = await queries.list_user_goals(session, user_id, status="active")
    except Exception as exc:
        logger.warning("goal lookup for research failed: %s", exc)
        return ""
    if not goals:
        return ""

    goal = min(goals, key=lambda g: g.get("deadline") or "9999-12-31")
    query = f"how to {goal['title']} youtube {niche} 2026"
    try:
        from app.tools.custom import run_web_search

        return await asyncio.to_thread(run_web_search, query, 5)
    except Exception as exc:
        logger.warning("goal-aware web research failed for %r: %s", query, exc)
        return ""


async def _ask_llm(llm, niche: str, plan_type: str, start: date, count: int,
                   recent: list[str], channel_context: str = "", directives: str = "",
                   goal_research: str = "", fallback_chain: list | None = None) -> list[_TopicIdea]:
    recent_block = "\n".join(f"- {t}" for t in recent) if recent else "(none yet)"
    prompt = SUGGESTER_PROMPT.format(
        count=count,
        niche=niche,
        plan_type=plan_type,
        start_date=start.isoformat(),
        channel_context=channel_context or "(no synced content yet — use the niche field only)",
        recent_topics=recent_block,
        directives=directives,
        goal_research=goal_research or "(no active goal, or research unavailable)",
        schema=_SCHEMA_HINT,
    )
    pack: _TopicPack = await call_llm_with_retry(
        llm, prompt, _TopicPack,
        temperature=SUGGESTER_TEMPERATURE,
        max_retries=3,
        agent_name="TopicSuggester",
        fallback_chain=fallback_chain,
    )
    return pack.topics


def _filter_duplicates(ideas: list[_TopicIdea], extra_seen: set[str]) -> list[_TopicIdea]:
    kept: list[_TopicIdea] = []
    for idea in ideas:
        norm = content_tracker.normalize_topic(idea.topic)
        if not idea.topic.strip() or norm in extra_seen:
            continue
        try:
            dup, score = content_tracker.is_duplicate_topic(idea.topic)
        except Exception:
            dup = False
        if dup:
            logger.info("Suggester dropped duplicate topic: %s", idea.topic)
            continue
        extra_seen.add(norm)
        kept.append(idea)
    return kept


async def _suggest_instagram(session, user_id: str, start_date: date, end: date,
                             count: int, extra_recent: list[str] | None) -> list[dict]:
    """Instagram suggestions, grounded in the account's own synced data.

    Reuses the Instagram idea generator that used to sit behind
    POST /api/instagram-analytics/board/generate — the endpoint is gone, the
    capability moved here so the planner is the only place ideas are proposed.
    Dates are assigned in Python exactly like the YouTube path.
    """
    from app.services import instagram_ai_analysis
    from app.services.instagram_cache import get_cached_instagram_data
    from app.services.roadmap_to_plan import covered_topics

    cached = get_cached_instagram_data(user_id) or {}
    if not (cached.get("profile") or cached.get("posts")):
        raise NotSyncedError(
            "No Instagram data synced yet. Connect and sync your account first."
        )

    existing = await queries.get_plan_items_by_platform(
        session, user_id, "instagram", order="created_desc"
    )
    context = instagram_ai_analysis.build_account_context(cached, existing)
    directives = await get_directives(session, user_id, scope="instagram")

    result = await instagram_ai_analysis.generate_board_ideas(
        context, count=min(count, MAX_INSTAGRAM_IDEAS), directives=directives
    )

    ideas = [
        _TopicIdea(
            topic=(idea.get("title") or "").strip(),
            rationale=idea.get("rationale", ""),
            meta={
                "type": idea.get("type") or "reel",
                "caption": idea.get("caption", ""),
                "image_prompt": idea.get("image_prompt", ""),
                "source": "ai_generated",
            },
        )
        for idea in result.get("ideas", [])
    ]

    # Same duplicate guard the YouTube path uses, seeded with what is already
    # planned for this platform plus any caller-supplied backlog titles.
    seen = covered_topics(existing)
    seen.update(content_tracker.normalize_topic(t) for t in (extra_recent or []) if t)
    ideas = _filter_duplicates(ideas, seen)[:count]

    dates = spread_dates(start_date, end, len(ideas))
    return [
        {
            "topic": idea.topic,
            "rationale": idea.rationale,
            "scheduled_date": d.isoformat(),
            "meta": idea.meta,
        }
        for idea, d in zip(ideas, dates)
    ]


async def suggest_topics(session, user_id: str, plan_type: str, niche: str, start_date: date,
                         count: int | None = None, provider: str = None,
                         extra_recent: list[str] | None = None,
                         platform: str = "youtube") -> list[dict]:
    """Return [{topic, rationale, scheduled_date, meta}] for a weekly/monthly plan.

    extra_recent adds more "already covered" titles to the do-not-repeat list —
    used by auto-research to avoid re-proposing topics already sitting in the
    saved-topic backlog, which _gather_recent_topics does not know about.

    `platform` picks the grounding: YouTube uses the channel/competitor/goal
    prompt below, Instagram delegates to the account-data idea generator.
    """
    from app.services.blog_pipeline.utils import build_fallback_chain

    end, default_count = _period_bounds(plan_type, start_date)
    count = count or default_count

    if platform == "instagram":
        return await _suggest_instagram(session, user_id, start_date, end, count, extra_recent)

    recent = await _gather_recent_topics(session, user_id, platform) + list(extra_recent or [])
    channel_context = await _gather_channel_context(session, user_id, platform)

    from app.services.youtube_competitor_context import build_competitor_block

    competitor_block = await build_competitor_block(session, user_id)
    if competitor_block:
        channel_context = f"{channel_context}\n\n{competitor_block}" if channel_context else competitor_block

    # scope="all": a plan can produce blog/LinkedIn/YouTube content, so every
    # active rule applies, not just one surface's.
    directives = await get_directives(session, user_id, scope="all")
    goal_research = await _gather_goal_research(session, user_id, niche)
    
    # Resilient 4-tier fallback cascade
    llm, fallback_chain = build_fallback_chain(temperature=SUGGESTER_TEMPERATURE, max_tokens=4096)

    seen: set[str] = set()
    ideas = _filter_duplicates(
        await _ask_llm(
            llm, niche, plan_type, start_date, count, recent, channel_context,
            directives=directives, goal_research=goal_research,
            fallback_chain=fallback_chain,
        ),
        seen,
    )

    # One replacement round if too many suggestions were duplicates.
    if len(ideas) < count * (1 - MAX_DROP_RATIO):
        missing = count - len(ideas)
        logger.info("Suggester retrying for %d replacement topics", missing)
        try:
            more = await _ask_llm(
                llm, niche, plan_type, start_date, missing,
                recent + [i.topic for i in ideas], channel_context,
                directives=directives, goal_research=goal_research,
                fallback_chain=fallback_chain,
            )
            ideas += _filter_duplicates(more, seen)
        except Exception as exc:
            logger.warning("Replacement round failed (%s) — returning %d topics", exc, len(ideas))

    ideas = ideas[:count]
    dates = spread_dates(start_date, end, len(ideas))
    return [
        {
            "topic": idea.topic,
            "rationale": idea.rationale,
            "scheduled_date": d.isoformat(),
            "meta": idea.meta,
        }
        for idea, d in zip(ideas, dates)
    ]
