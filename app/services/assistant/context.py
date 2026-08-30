"""Deterministic retrieval: the user's real rows, bounded.

No LLM touches this module. It takes a QueryPlan and returns a ContextPack —
capped, projected, sanitized rows plus the set of ids the answerer is permitted
to name. That id set is what makes the write path safe: an action naming an id
outside it is dropped before it is ever persisted.

Three independent limits, applied in this order:

1. **Row caps in SQL.** Never fetch-then-truncate; a Python-side cap over
   per-platform queries can drop the only YouTube item of the day.
2. **Field projection.** Rows are mapped to a whitelist before they can reach a
   prompt. Notably absent: ``PlanItem.meta`` (unbounded JSONB, holds generated
   image prompts), ``YoutubeAnalysis.payload`` (a whole report), and full draft
   bodies.
3. **Character budget.** Sections are dropped whole, in reverse priority, until
   the rendered block fits — and the prompt is told what was dropped, so the
   model says "showing the first 30 of 47" instead of quietly implying 30 is all.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import get_args

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import clamp_range, parse_iso_date, user_today
from app.db import queries
from app.models.planner import (
    GENERIC_PRODUCTION_STATUSES,
    Platform,
    VIDEO_PRODUCTION_STATUSES,
)
from app.services.assistant.schemas import QueryPlan

logger = logging.getLogger(__name__)

# ── Caps ─────────────────────────────────────────────────────────────────────
MAX_ITEMS = 60
MAX_ITEMS_SINGLE_DAY = 30
MAX_REVIEW = 25
MAX_HYDRATE = 5          # per-row extra query; the excerpt is worth 5, not 25
MAX_RECONCILE = 10       # 'generating' rows worth re-checking against their run
MAX_BACKLOG = 20
MAX_BASELINE_ITEMS = 10
MAX_SEARCH_TERMS = 5

# Overdue is unbounded backwards, so it is the one read that can return hundreds
# of rows. Past this many, a per-platform/per-month breakdown is both cheaper and
# more useful than a list nobody will read to the end of.
OVERDUE_LIST_CEILING = 40

# ── Text limits ──────────────────────────────────────────────────────────────
TOPIC_CHARS = 120
NOTES_CHARS = 200
EXCERPT_CHARS = 300      # LLM-written text fed back to an LLM: the riskiest text here
TERM_CHARS = 60
CONTEXT_CHAR_BUDGET = 12_000

# Reconciling every backlog topic fans out one query per row; past this many,
# report the count instead.
BACKLOG_RECONCILE_CEILING = 100

VALID_PLATFORMS = frozenset(get_args(Platform))
VALID_STATUSES = frozenset(VIDEO_PRODUCTION_STATUSES) | frozenset(
    GENERIC_PRODUCTION_STATUSES
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def sanitize(text: str | None, limit: int) -> str:
    """Make user- or model-authored text safe to place in a prompt.

    Strips control characters, collapses whitespace, neutralises backticks and
    HTML comment markers (the two cheapest ways to break out of a rendered
    block), and truncates. Length alone defeats most injection payloads; the
    delimiter discipline in ``render_context`` handles the rest.
    """
    if not text:
        return ""
    out = _CONTROL_CHARS.sub("", str(text))
    out = out.replace("`", "'").replace("<!--", "").replace("-->", "")
    out = _WHITESPACE.sub(" ", out).strip()
    if len(out) > limit:
        out = out[: limit - 1].rstrip() + "…"
    return out


def _short_id(value: str | None) -> str:
    """First UUID segment. Short enough that the model reproduces it verbatim."""
    return (value or "")[:8]


@dataclass
class ContextPack:
    """Everything the answerer is allowed to see, plus what it may act on."""

    today: str
    range_from: str | None = None
    range_to: str | None = None
    intent: str = "unknown"
    platforms: list[str] = field(default_factory=list)

    items: list[dict] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)
    backlog: list[dict] = field(default_factory=list)
    backlog_total: int = 0
    # Overdue rows live in `items`; these two carry the true total (which may
    # exceed what was fetched) and the grouped breakdown used in its place.
    overdue_total: int = 0
    overdue_summary: list[dict] = field(default_factory=list)
    analytics: dict | None = None
    reports: list[dict] = field(default_factory=list)

    # The authorization surface. An action naming anything outside these is
    # dropped in validate_proposal.
    item_ids: set[str] = field(default_factory=set)
    content_ids: set[str] = field(default_factory=set)

    truncated: dict[str, bool] = field(default_factory=dict)

    def sources(self) -> list[dict]:
        """Citation chips for the UI, built from real rows — never from the
        model's ``cited_item_ids``, so a fabricated citation gets no chip."""
        out = [
            {
                "kind": "plan_item",
                "id": it["id"],
                "label": it["topic"],
                "platform": it["platform"],
            }
            for it in self.items[:10]
        ]
        out += [
            {
                "kind": "review",
                "id": r["content_id"],
                "label": r.get("title") or r["topic"],
                "platform": r["platform"],
            }
            for r in self.review[:5]
        ]
        return out


# ── Filtering LLM-supplied vocabulary ────────────────────────────────────────


def _clean_platforms(raw: list[str] | None) -> list[str]:
    """Keep known platforms, drop the rest with a warning.

    Dropping rather than raising is deliberate: an unrecognised platform
    degrades to "all platforms", which is a broader answer, whereas raising
    would 502 a question that was perfectly answerable.
    """
    if not raw:
        return []
    kept = [p for p in (str(x).strip().lower() for x in raw) if p in VALID_PLATFORMS]
    dropped = len(raw) - len(kept)
    if dropped:
        logger.warning("assistant: dropped %d unknown platform value(s): %s", dropped, raw)
    return kept


def _clean_statuses(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    kept = [s for s in (str(x).strip().lower() for x in raw) if s in VALID_STATUSES]
    dropped = len(raw) - len(kept)
    if dropped:
        logger.warning("assistant: dropped %d unknown status value(s): %s", dropped, raw)
    return kept


def clean_search_terms(raw: list[str] | None) -> list[str]:
    """Sanitize free-text search terms for use in an ILIKE.

    ``%``, ``_`` and ``\\`` are escaped because an unescaped ``%`` from the model
    turns a topic search into a full-table match. Callers must pair this with an
    explicit ``ESCAPE '\\'``.
    """
    if not raw:
        return []
    out = []
    for term in raw[:MAX_SEARCH_TERMS]:
        cleaned = sanitize(term, TERM_CHARS)
        if not cleaned:
            continue
        cleaned = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        out.append(cleaned)
    return out


# ── Date resolution ──────────────────────────────────────────────────────────


def resolve_range(plan: QueryPlan, today: date) -> tuple[str | None, str | None]:
    """Turn the plan's dates into a clamped ISO range.

    A plan with no dates at all means "no date filter" for the backlog and
    review intents — those are not date-scoped questions — and "today" for
    everything else.

    The overdue intent is the one case with a genuinely half-open range, and it
    is resolved here rather than trusted from the plan: the model used to emit
    ``null .. today-1`` and the collapse below rewrote it to a single day, which
    is how "list my overdue items" came back with one row against a count of 15.
    """
    if plan.intent == "overdue":
        # Open-ended backwards on purpose — an item missed in June is still
        # overdue. The row cap and the summary fallback bound the answer, not
        # the range. Any dates the model sent are ignored; they cannot improve
        # on this and have only ever narrowed it wrongly.
        return None, (today - timedelta(days=1)).isoformat()

    start = parse_iso_date(plan.date_from)
    end = parse_iso_date(plan.date_to)

    if start is None and end is None:
        if plan.intent in ("backlog", "review_queue", "analytics", "smalltalk"):
            return None, None
        return today.isoformat(), today.isoformat()

    # A half-open range is treated as a single day rather than an unbounded scan.
    start = start or end
    end = end or start
    start, end = clamp_range(start, end)
    return start.isoformat(), end.isoformat()


# ── Projection ───────────────────────────────────────────────────────────────


def _project_item(row: dict) -> dict:
    return {
        "id": row["id"],
        "short_id": _short_id(row["id"]),
        "plan_id": row.get("plan_id"),
        "platform": row.get("platform") or "youtube",
        "topic": sanitize(row.get("topic"), TOPIC_CHARS),
        "scheduled_date": row.get("scheduled_date"),
        "event_time": row.get("event_time"),
        "production_status": row.get("production_status"),
        "video_format": row.get("video_format"),
        "notes": sanitize(row.get("notes"), NOTES_CHARS),
    }


def _project_review(row: dict) -> dict:
    return {
        "content_id": row["id"],
        "short_id": _short_id(row["id"]),
        "item_id": row.get("item_id"),
        "plan_id": row.get("plan_id"),
        "content_type": row.get("content_type"),
        "review_status": row.get("review_status"),
        "topic": sanitize(row.get("topic"), TOPIC_CHARS),
        "platform": row.get("platform"),
        "title": sanitize(row.get("title"), TOPIC_CHARS),
        "excerpt": sanitize(row.get("body"), EXCERPT_CHARS),
        "created_at": row.get("created_at"),
    }


def _project_backlog(row: dict) -> dict:
    return {
        "id": row["id"],
        "short_id": _short_id(row["id"]),
        "topic": sanitize(row.get("topic"), TOPIC_CHARS),
        "status": row.get("status"),
        "rationale": sanitize(row.get("rationale"), NOTES_CHARS),
    }


def _project_report(row: dict, kind: str) -> dict:
    # The two tables spell the column differently: youtube_analyses.payload_json
    # vs instagram_ai_reports.payload.
    payload = row.get("payload_json") or row.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    recs = payload.get("recommendations") or payload.get("action_items") or []
    if not isinstance(recs, list):
        recs = []
    return {
        "kind": kind,
        "created_at": row.get("created_at"),
        "summary": sanitize(
            payload.get("summary") or payload.get("overview"), EXCERPT_CHARS
        ),
        "recommendations": [
            sanitize(r if isinstance(r, str) else str(r), NOTES_CHARS) for r in recs[:3]
        ],
    }


# ── Builders ─────────────────────────────────────────────────────────────────


async def _load_review(
    session: AsyncSession, user_id: str, platforms: list[str], hydrate: bool
) -> list[dict]:
    """The review queue, reconciled just enough to be truthful.

    Only 'generating' rows are reconciled (capped): a row already 'ready' is
    terminal for our purposes, and reconciling all 25 would be 25 extra queries.
    Reporting a finished draft as still generating is the most likely wrong
    answer this feature can give, which is why the reconcile happens at all.
    """
    from app.services import plan_service

    rows = await queries.get_pending_review_contents(
        session, user_id, platforms=platforms or None, limit=MAX_REVIEW
    )

    reconciled = 0
    out = []
    for row in rows:
        if row.get("review_status") == "generating" and reconciled < MAX_RECONCILE:
            try:
                row = {**row, **await plan_service.reconcile_plan_item_content(session, row)}
            except Exception as exc:  # a stale row must not fail the answer
                logger.warning("assistant: reconcile failed for content %s: %s", row.get("id"), exc)
            reconciled += 1
        out.append(row)

    if hydrate:
        ready = [r for r in out if r.get("review_status") == "ready"][:MAX_HYDRATE]
        for row in ready:
            try:
                hydrated = await plan_service.hydrate_content(session, row)
                row["title"] = hydrated.get("title")
                row["body"] = hydrated.get("body")
            except Exception as exc:
                logger.warning("assistant: hydrate failed for content %s: %s", row.get("id"), exc)

    return [_project_review(r) for r in out]


async def _load_backlog(session: AsyncSession, user_id: str) -> tuple[list[dict], int]:
    from app.services import saved_topic_service

    total = await queries.count_uncovered_topics(session, user_id)
    if total > BACKLOG_RECONCILE_CEILING:
        # list_topics_reconciled reconciles every topic before filtering, which
        # fans out one query per row. Past this size the count is the answer.
        return [], total
    try:
        rows = await saved_topic_service.list_topics_reconciled(
            session, user_id, status="uncovered", include_dismissed=False
        )
    except Exception as exc:
        logger.warning("assistant: backlog read failed for user %s: %s", user_id, exc)
        return [], total
    return [_project_backlog(r) for r in rows[:MAX_BACKLOG]], total


# Both report tables key their newest row by a kind/type discriminator, and both
# use these two names. 'strategy' first: it is the one that reads as advice.
_REPORT_KINDS = ("strategy", "roadmap")


async def _load_reports(session: AsyncSession, user_id: str) -> list[dict]:
    """The most recent saved AI report per channel, summary only.

    Never the full payload — a YouTube channel audit is a whole JSON report and
    inlining one would consume the entire context budget by itself.
    """
    out: list[dict] = []
    for kind in _REPORT_KINDS:
        try:
            yt = await queries.get_latest_youtube_analysis(session, user_id, kind)
            if yt:
                out.append(_project_report(yt, f"youtube/{kind}"))
                break
        except Exception as exc:
            logger.debug("assistant: no youtube %s analysis for %s: %s", kind, user_id, exc)
    for report_type in _REPORT_KINDS:
        try:
            ig = await queries.get_latest_instagram_ai_report(session, user_id, report_type)
            if ig:
                out.append(_project_report(ig, f"instagram/{report_type}"))
                break
        except Exception as exc:
            logger.debug("assistant: no instagram %s report for %s: %s", report_type, user_id, exc)
    return out


async def build_context(
    session: AsyncSession, user_id: str, plan: QueryPlan, today: date | None = None
) -> ContextPack:
    """Assemble the bounded snapshot for one question.

    A baseline — today's items and the review-queue size — is included whatever
    the intent, so an ``unknown`` intent still produces a useful answer rather
    than an empty one. It costs two index reads.
    """
    today = today or user_today()
    platforms = _clean_platforms(plan.platforms)
    statuses = _clean_statuses(plan.statuses)
    range_from, range_to = resolve_range(plan, today)

    pack = ContextPack(
        today=today.isoformat(),
        range_from=range_from,
        range_to=range_to,
        intent=plan.intent,
        platforms=platforms,
    )

    single_day = bool(range_from) and range_from == range_to
    cap = MAX_ITEMS_SINGLE_DAY if single_day else MAX_ITEMS

    wants_items = plan.intent in (
        "daily_digest", "schedule_lookup", "item_lookup",
        "action_request", "unknown", "smalltalk",
    )
    if plan.intent == "overdue":
        # Its own read, not the range query: `statuses` is deliberately ignored
        # here because the unpublished predicate *is* the status filter, and
        # intersecting a model-supplied ["published"] with it returns nothing.
        # `platforms` still applies — "what's overdue on YouTube" is a fair ask.
        pack.overdue_total = await queries.count_overdue_plan_items(
            session, user_id, today=today.isoformat(), platforms=platforms or None
        )
        if pack.overdue_total > OVERDUE_LIST_CEILING:
            pack.overdue_summary = await queries.summarize_overdue_plan_items(
                session, user_id, today=today.isoformat(), platforms=platforms or None
            )
        else:
            rows = await queries.get_overdue_plan_items(
                session, user_id, today=today.isoformat(),
                platforms=platforms or None, limit=OVERDUE_LIST_CEILING,
            )
            pack.items = [_project_item(r) for r in rows]
    elif wants_items or range_from:
        rows = await queries.get_plan_items_across_platforms(
            session,
            user_id,
            platforms=platforms or None,
            statuses=statuses or None,
            date_from=range_from,
            date_to=range_to,
            include_undated=plan.intent in ("item_lookup", "backlog"),
            order="scheduled",
            limit=cap + 1,
        )
        pack.truncated["items"] = len(rows) > cap
        pack.items = [_project_item(r) for r in rows[:cap]]
    else:
        # Baseline: even a backlog question benefits from knowing what today holds.
        rows = await queries.get_plan_items_across_platforms(
            session,
            user_id,
            date_from=today.isoformat(),
            date_to=today.isoformat(),
            order="scheduled",
            limit=MAX_BASELINE_ITEMS,
        )
        pack.items = [_project_item(r) for r in rows]

    # Review queue: always at least counted, hydrated only when it is the subject.
    review_focus = plan.intent in ("review_queue", "action_request", "daily_digest", "unknown")
    pack.review = await _load_review(session, user_id, platforms, hydrate=review_focus)

    if plan.intent in ("backlog", "daily_digest", "unknown"):
        pack.backlog, pack.backlog_total = await _load_backlog(session, user_id)
    else:
        pack.backlog_total = await queries.count_uncovered_topics(session, user_id)

    if plan.needs_analytics or plan.intent == "analytics":
        try:
            # today= is what keeps overdue/upcoming honest: without it those two
            # counts come from Postgres current_date, which in a UTC container is
            # a day behind IST between midnight and 05:30.
            analytics = await queries.get_planner_analytics(
                session, user_id, platform=platforms[0] if len(platforms) == 1 else None,
                today=today.isoformat(),
            )
            pack.analytics = {
                "kpis": analytics.get("kpis"),
                "schedule": analytics.get("schedule"),
                "content_by_review": analytics.get("content_by_review"),
            }
        except Exception as exc:
            logger.warning("assistant: analytics read failed for %s: %s", user_id, exc)
        pack.reports = await _load_reports(session, user_id)

    pack.item_ids = {i["id"] for i in pack.items}
    pack.content_ids = {r["content_id"] for r in pack.review}
    return pack


# ── Rendering ────────────────────────────────────────────────────────────────

# Sections are dropped in this order when the budget is exceeded — least
# load-bearing first. Items are last because without them there is no answer.
_DROP_ORDER = ("reports", "analytics", "backlog", "review", "overdue", "items")


def _item_line(it: dict) -> str:
    return (
        f"[{it['short_id']}] {it['platform']} | {it['scheduled_date'] or 'no date'} "
        f"| {it['event_time'] or '--:--'} | {it['production_status']} "
        f"| {it['video_format']} | {it['topic']}"
        + (f" | notes: {it['notes']}" if it["notes"] else "")
    )


def _render_items(pack: ContextPack) -> str:
    if pack.intent == "overdue":
        # The summary replaces the rows entirely; without this the block would
        # read "none scheduled in this range" beside a count of 137.
        if pack.overdue_summary:
            return ""
        if not pack.items:
            return "OVERDUE: nothing is past due. Every dated item is published or still ahead."
        header = (
            f"OVERDUE ({pack.overdue_total} item(s) past their scheduled date and not yet "
            "published — this is the complete list, oldest first) "
            "(id | platform | date | time | status | format | topic):"
        )
        return "\n".join([header] + [_item_line(it) for it in pack.items])

    if not pack.items:
        return "ITEMS: none scheduled in this range."
    lines = ["ITEMS (id | platform | date | time | status | format | topic):"]
    lines += [_item_line(it) for it in pack.items]
    if pack.truncated.get("items"):
        lines.append(f"(showing the first {len(pack.items)}; there are more)")
    return "\n".join(lines)


def _render_review(pack: ContextPack) -> str:
    """Ready and generating drafts, counted separately.

    Only 'ready' is waiting on the user — that is what the dashboard's "To
    review" tile counts. Blending the two here is what made the assistant say
    "one item in the review queue" beside a tile reading 0.
    """
    if not pack.review:
        return "REVIEW QUEUE: empty."
    ready = sum(1 for r in pack.review if r.get("review_status") == "ready")
    generating = sum(1 for r in pack.review if r.get("review_status") == "generating")
    lines = [
        f"REVIEW QUEUE ({ready} ready for the user to decide on, "
        f"{generating} still generating) "
        "(content_id | type | status | platform | topic):"
    ]
    for r in pack.review:
        line = (
            f"[{r['short_id']}] {r['content_type']} | {r['review_status']} "
            f"| {r['platform']} | {r['topic']}"
        )
        if r.get("title"):
            line += f" | title: {r['title']}"
        if r.get("excerpt"):
            line += f" | excerpt: {r['excerpt']}"
        lines.append(line)
    return "\n".join(lines)


def _render_backlog(pack: ContextPack) -> str:
    if not pack.backlog:
        return f"BACKLOG: {pack.backlog_total} uncovered topic(s)."
    lines = [f"BACKLOG ({pack.backlog_total} uncovered, showing {len(pack.backlog)}):"]
    lines += [f"[{b['short_id']}] {b['topic']}" for b in pack.backlog]
    return "\n".join(lines)


def _render_overdue(pack: ContextPack) -> str:
    """The grouped breakdown, used only when there are too many rows to list."""
    if not pack.overdue_summary:
        return ""
    by_platform: dict[str, list[str]] = {}
    oldest = None
    for row in pack.overdue_summary:
        platform = row.get("platform") or "unknown"
        by_platform.setdefault(platform, []).append(
            f"{row.get('month')}: {row.get('count')}"
        )
        row_oldest = str(row.get("oldest") or "")
        if row_oldest and (oldest is None or row_oldest < oldest):
            oldest = row_oldest

    lines = [
        f"OVERDUE SUMMARY: {pack.overdue_total} items are past their scheduled date "
        f"and not yet published — too many to list individually."
    ]
    if oldest:
        lines.append(f"Oldest is scheduled {oldest}.")
    lines.append("Counts by platform and month:")
    lines += [f"  {p}: {', '.join(months)}" for p, months in sorted(by_platform.items())]
    return "\n".join(lines)


def _render_analytics(pack: ContextPack) -> str:
    if not pack.analytics:
        return ""
    sched = pack.analytics.get("schedule") or {}
    kpis = pack.analytics.get("kpis") or {}
    return (
        "ANALYTICS: "
        f"published={sched.get('published')} overdue={sched.get('overdue')} "
        f"upcoming={sched.get('upcoming')} | kpis={kpis}"
    )


def _render_reports(pack: ContextPack) -> str:
    if not pack.reports:
        return ""
    lines = ["LATEST AI REPORTS:"]
    for r in pack.reports:
        lines.append(f"- {r['kind']} ({r['created_at']}): {r['summary']}")
        lines += [f"  * {rec}" for rec in r["recommendations"]]
    return "\n".join(lines)


_RENDERERS = {
    "overdue": _render_overdue,
    "items": _render_items,
    "review": _render_review,
    "backlog": _render_backlog,
    "analytics": _render_analytics,
    "reports": _render_reports,
}


def render_context(pack: ContextPack) -> str:
    """Render the pack as the prompt's data block.

    Compact one-line-per-row rather than JSON: roughly half the tokens, and
    leading with a short bracketed id makes it something the model copies
    verbatim instead of paraphrasing.

    The whole block is wrapped in explicit delimiters and the answer prompt
    carries a standing rule that nothing inside them is an instruction. Topics
    and notes are user-authored free text, and reach this table from AI topic
    suggestion and roadmap import as well as from typing.
    """
    if pack.intent == "overdue":
        # "any .. 2026-08-23" reads like a bounded range the model should quote
        # back; "on or before" says what the window actually is.
        range_line = f"RANGE: everything on or before {pack.range_to}"
    else:
        range_line = f"RANGE: {pack.range_from or 'any'} .. {pack.range_to or 'any'}"
    header = (
        f"TODAY: {pack.today} (Asia/Kolkata)\n"
        f"{range_line}\n"
        f"INTENT: {pack.intent}\n"
    )

    sections = {name: fn(pack) for name, fn in _RENDERERS.items()}
    dropped: list[str] = []
    for name in _DROP_ORDER:
        body = "\n\n".join(s for s in sections.values() if s)
        if len(header) + len(body) <= CONTEXT_CHAR_BUDGET:
            break
        if sections.get(name):
            sections[name] = ""
            dropped.append(name)
            pack.truncated[name] = True

    body = "\n\n".join(s for s in sections.values() if s)
    if dropped:
        body += f"\n\n(omitted for length: {', '.join(dropped)})"

    return f"{header}\n<<<USER_DATA\n{body}\nUSER_DATA>>>"
