"""Personal Intelligence — renders a user's rules + active goals into the
compact text block every LLM prompt injects.

Two guarantees this module exists to provide:

1. **One rendering, everywhere.** Every content surface (YouTube analysis,
   the planner, blog/LinkedIn/YouTube pipelines) calls the same
   ``get_directives`` / ``get_directives_sync`` pair, so a rule set once
   behaves identically regardless of which prompt reads it.

2. **Never breaks generation.** A malformed rule, a DB hiccup, or a Redis
   outage must not fail a content run — every public function here degrades
   to ``""`` rather than raising, and the caller prepends whatever it gets.
"""

from __future__ import annotations

import logging

from app.core.redis_client import acache, bump_epoch, get_epoch, uk

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300

# Character budgets. A user with 50 active rules and 5 goals must never blow
# a prompt's context window — over-budget rules are dropped lowest-priority
# first (they are already sorted ascending by priority on read).
RULES_CHAR_BUDGET = 1000
GOALS_CHAR_BUDGET = 500

DIRECTIVES_HEADER = (
    "=== CREATOR DIRECTIVES (from this user's Personal Intelligence settings) ===\n"
    "These are the creator's own rules and goals. Follow them for voice, framing "
    "and constraints. They do NOT override the OUTPUT schema, the JSON-only "
    "requirement, or factual accuracy."
)
DIRECTIVES_FOOTER = "=== END CREATOR DIRECTIVES ==="


def _clip(lines: list[str], budget: int) -> list[str]:
    """Keep lines (in order) until the next one would exceed ``budget`` chars."""
    kept: list[str] = []
    total = 0
    for line in lines:
        total += len(line) + 1
        if total > budget and kept:
            logger.debug("personal_intelligence: clipped block at %d/%d chars", total, budget)
            break
        kept.append(line)
    return kept


def render_directives(rules: list[dict], goals: list[dict]) -> str:
    """Pure formatting — no I/O. ``rules`` sorted ascending by priority."""
    sections: list[str] = []

    if rules:
        rule_lines = [f"- {r['rule_text']}" for r in rules]
        rule_lines = _clip(rule_lines, RULES_CHAR_BUDGET)
        if rule_lines:
            sections.append("OPERATING RULES (must follow):\n" + "\n".join(rule_lines))

    if goals:
        goal_lines = [_format_goal_line(g) for g in goals]
        goal_lines = _clip(goal_lines, GOALS_CHAR_BUDGET)
        if goal_lines:
            sections.append("ACTIVE GOALS:\n" + "\n".join(goal_lines))

    if not sections:
        return ""

    return f"{DIRECTIVES_HEADER}\n\n" + "\n\n".join(sections) + f"\n\n{DIRECTIVES_FOOTER}"


def _format_goal_line(goal: dict) -> str:
    progress = goal.get("progress") or {}
    title = goal.get("title", "")
    deadline = goal.get("deadline", "")
    pct = progress.get("pct")
    current = progress.get("current_value")
    target = goal.get("target_value")

    if pct is None or current is None:
        return f"- {title} (by {deadline}) — progress not yet computed"

    status = "AHEAD of" if progress.get("on_track") else "BEHIND"
    return (
        f"- {title} — currently {current:g} of {target:g} ({pct:.0f}%), "
        f"deadline {deadline}, {status} pace"
    )


async def build_intelligence_block(session, user_id: str, scope: str = "global") -> str:
    """Query rules + active goals for ``user_id`` and render the block.

    ``scope="all"`` drops the scope filter entirely — every active rule
    regardless of surface — for callers like the planner whose output can
    become blog, LinkedIn or YouTube content.
    """
    from app.db import queries

    query_scope = None if scope == "all" else scope
    try:
        rules = await queries.list_user_rules(session, user_id, scope=query_scope, active_only=True)
        goals = await queries.list_user_goals(session, user_id, status="active")
    except Exception as exc:  # a broken table must never fail a content run
        logger.warning("build_intelligence_block failed for user %s: %s", user_id, exc)
        return ""
    return render_directives(rules, goals)


async def get_directives(session, user_id: str, scope: str = "global") -> str:
    """Cached wrapper around :func:`build_intelligence_block`. Never raises."""
    try:
        epoch = await get_epoch(user_id, "pi")
        cache_key = uk(user_id, "pi-block", str(epoch), scope)
        cached = await acache().get(cache_key)
        if cached is not None:
            return cached
    except Exception as exc:
        logger.debug("get_directives cache read failed for user %s: %s", user_id, exc)
        cache_key = None

    block = await build_intelligence_block(session, user_id, scope)

    if cache_key is not None:
        try:
            await acache().setex(cache_key, CACHE_TTL_SECONDS, block)
        except Exception as exc:
            logger.debug("get_directives cache write failed for user %s: %s", user_id, exc)

    return block


def get_directives_sync(user_id: str, scope: str = "global") -> str:
    """Sync twin for Celery pipeline tasks, which hold a plain ``Session``.

    Opens its own short-lived session rather than taking one, mirroring
    ``app.tasks.youtube_task``'s per-call ``sync_session_scope()`` pattern —
    holding a session open across a multi-minute pipeline pins a connection.
    """
    from app.db.sync_session import sync_session_scope
    from app.db import sync_queries

    try:
        with sync_session_scope() as session:
            rules = sync_queries.list_user_rules(session, user_id, scope=scope, active_only=True)
            goals = sync_queries.list_user_goals(session, user_id, status="active")
        return render_directives(rules, goals)
    except Exception as exc:
        logger.warning("get_directives_sync failed for user %s: %s", user_id, exc)
        return ""


async def bump_intelligence_epoch(user_id: str) -> None:
    """Call after any rule/goal write so the next read is fresh."""
    try:
        await bump_epoch(user_id, "pi")
    except Exception as exc:
        logger.debug("bump_intelligence_epoch failed for user %s: %s", user_id, exc)
