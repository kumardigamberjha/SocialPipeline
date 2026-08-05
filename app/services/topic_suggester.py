"""
AI topic suggester for content plans.

One LLM call proposes a period's worth of video topics for a niche, primed with
the user's recent history (published_topics in content_tracker.db + recent
plan_items in nexus.db) as a DO-NOT-REPEAT list. Suggestions are then
post-filtered through content_tracker.is_duplicate_topic; dates are assigned in
Python (spread evenly across the period), never by the LLM.
"""

import calendar
import json
import logging
from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.db import content_tracker, queries
from app.services.blog_pipeline.utils import call_llm_with_retry, make_llm

logger = logging.getLogger(__name__)

SUGGESTER_TEMPERATURE = 0.8

# Fraction of suggestions allowed to be dropped as duplicates before we ask the
# LLM once more for replacements.
MAX_DROP_RATIO = 0.2


class _TopicIdea(BaseModel):
    topic: str
    rationale: str = ""


class _TopicPack(BaseModel):
    topics: list[_TopicIdea] = Field(default_factory=list)


SUGGESTER_PROMPT = """
ROLE: You plan video/content topics for a solo creator. Propose exactly {count} topics.

INPUT:
- niche / audience: {niche}
- period: {plan_type} starting {start_date}

RULES:
- Every topic must be a concrete, specific video idea — never generic ("intro to AI" is banned).
- Mix formats across the set: tutorials, contrarian takes, case studies, tool comparisons, lessons learned.
- Each topic must be phrased as a working title (under 15 words).
- rationale: one short sentence on why it would perform now.
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


def _gather_recent_topics(user_id: str) -> list[str]:
    seen: list[str] = []
    try:
        seen += [t["topic_original"] for t in content_tracker.get_recent_topics(limit=40)]
    except Exception as exc:  # tracker DB is best-effort context
        logger.warning("content_tracker history unavailable: %s", exc)
    try:
        seen += queries.get_recent_plan_topics(user_id, days=90)
    except Exception as exc:
        logger.warning("plan topic history unavailable: %s", exc)
    # Dedup while preserving order.
    return list(dict.fromkeys(seen))


async def _ask_llm(llm, niche: str, plan_type: str, start: date, count: int,
                   recent: list[str]) -> list[_TopicIdea]:
    recent_block = "\n".join(f"- {t}" for t in recent) if recent else "(none yet)"
    prompt = SUGGESTER_PROMPT.format(
        count=count,
        niche=niche,
        plan_type=plan_type,
        start_date=start.isoformat(),
        recent_topics=recent_block,
        schema=_SCHEMA_HINT,
    )
    pack: _TopicPack = await call_llm_with_retry(
        llm, prompt, _TopicPack,
        temperature=SUGGESTER_TEMPERATURE,
        max_retries=3,
        agent_name="TopicSuggester",
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


async def suggest_topics(user_id: str, plan_type: str, niche: str, start_date: date,
                         count: int | None = None, provider: str = None,
                         extra_recent: list[str] | None = None) -> list[dict]:
    """Return [{topic, rationale, scheduled_date}] for a weekly/monthly plan.

    extra_recent adds more "already covered" titles to the do-not-repeat list —
    used by auto-research to avoid re-proposing topics already sitting in the
    saved-topic backlog, which _gather_recent_topics does not know about.
    """
    from app.config import get_settings

    provider = provider or get_settings().default_provider
    end, default_count = _period_bounds(plan_type, start_date)
    count = count or default_count

    recent = _gather_recent_topics(user_id) + list(extra_recent or [])
    llm = make_llm(provider, SUGGESTER_TEMPERATURE, max_tokens=4096)

    seen: set[str] = set()
    ideas = _filter_duplicates(await _ask_llm(llm, niche, plan_type, start_date, count, recent), seen)

    # One replacement round if too many suggestions were duplicates.
    if len(ideas) < count * (1 - MAX_DROP_RATIO):
        missing = count - len(ideas)
        logger.info("Suggester retrying for %d replacement topics", missing)
        try:
            more = await _ask_llm(
                llm, niche, plan_type, start_date, missing,
                recent + [i.topic for i in ideas],
            )
            ideas += _filter_duplicates(more, seen)
        except Exception as exc:
            logger.warning("Replacement round failed (%s) — returning %d topics", exc, len(ideas))

    ideas = ideas[:count]
    dates = spread_dates(start_date, end, len(ideas))
    return [
        {"topic": idea.topic, "rationale": idea.rationale, "scheduled_date": d.isoformat()}
        for idea, d in zip(ideas, dates)
    ]
