"""The orchestrator: one question in, one answer (and maybe some offers) out.

Owns the deadline arithmetic and the ordering guarantee that makes this safe:

    ask()     reads planner data and writes ONLY assistant_* rows.
    confirm() is the only path that writes planner data, and it cannot run
              without an action_id that ask() created.

There is no code path from a question straight to a mutation. That is the whole
design, and it is worth preserving through future edits.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import user_today, user_today_iso, week_bounds
from app.db import queries
from app.db.queries import _now
from app.services.assistant import actions as action_service
from app.services.assistant import context as context_service
from app.services.assistant import history as history_service
from app.services.assistant.answerer import synthesize_answer
from app.services.assistant.language import detect_language
from app.services.assistant.resolver import default_plan, resolve_query
from app.services.blog_pipeline.utils import AgentFailedError

logger = logging.getLogger(__name__)


async def ask(
    session: AsyncSession,
    user_id: str,
    question: str,
    conversation_id: str | None,
) -> dict:
    """Answer one question. Performs no planner writes — see the module docstring."""
    t0 = time.monotonic()
    deadline = t0 + get_settings().llm_timeout
    # Computed once and threaded everywhere, so a request that straddles local
    # midnight cannot answer half in one day and half in the next.
    today = user_today()

    conversation = await history_service.ensure_conversation(
        session, user_id, conversation_id, question
    )
    raw_history = await history_service.load_history(session, user_id, conversation["id"])
    history = history_service.trim_history(raw_history)
    previous_language = history_service.last_language(raw_history)

    await queries.create_assistant_message(
        session, conversation["id"], user_id, "user", question,
        meta={"language": detect_language(question, previous_language)},
    )

    resolver_used: dict[str, Any] = {}
    plan, fell_back = await resolve_query(
        question, history, today, deadline=deadline, used=resolver_used
    )

    # The deterministic verdict overrides the model for hinglish specifically —
    # a false positive is readable, a false negative is the actual complaint.
    language = detect_language(question, previous_language, plan.language)

    pack = await context_service.build_context(session, user_id, plan, today=today)
    context_block = context_service.render_context(pack)

    from app.services.personal_intelligence import get_directives

    directives = await get_directives(session, user_id, scope="all")

    answer_used: dict[str, Any] = {}
    try:
        answer = await synthesize_answer(
            question, directives, context_block, history, plan, language,
            deadline=deadline, used=answer_used,
        )
    except AgentFailedError as exc:
        logger.error("assistant: answer synthesis failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=502,
            detail="The AI service is unavailable right now. Please try again in a minute.",
        )

    validated = []
    for proposed in answer.proposed_actions[: action_service.MAX_ACTIONS * 2]:
        checked = await action_service.validate_proposal(session, user_id, proposed, pack)
        if checked:
            validated.append(checked)
        if len(validated) >= action_service.MAX_ACTIONS:
            break

    meta = {
        "intent": plan.intent,
        "date_from": pack.range_from,
        "date_to": pack.range_to,
        "platforms": pack.platforms,
        "language": language,
        "model": answer_used.get("model"),
        "tier": answer_used.get("tier"),
        "resolver_fallback": fell_back,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "row_counts": {
            "items": len(pack.items),
            "review": len(pack.review),
            "backlog": len(pack.backlog),
        },
        "truncated": pack.truncated,
        # Ids only, for next turn's anaphora — never the rows themselves.
        "last_items": [
            {"short_id": i["short_id"], "topic": i["topic"], "platform": i["platform"]}
            for i in pack.items[: history_service.MAX_LAST_ITEMS]
        ],
    }

    message = await queries.create_assistant_message(
        session, conversation["id"], user_id, "assistant", answer.answer_markdown, meta=meta
    )
    action_rows = await action_service.persist_actions(
        session, user_id, message["id"], validated
    )
    await queries.touch_assistant_conversation(session, conversation["id"], user_id)

    return {
        "conversation_id": conversation["id"],
        "message_id": message["id"],
        "answer_markdown": answer.answer_markdown,
        "resolved": {
            "intent": plan.intent,
            "date_from": pack.range_from,
            "date_to": pack.range_to,
            "platforms": pack.platforms,
        },
        "actions": [_action_out(a, pack) for a in action_rows],
        "sources": pack.sources(),
        "meta": {
            "model": meta["model"],
            "tier": meta["tier"],
            "latency_ms": meta["latency_ms"],
            "resolver_fallback": fell_back,
            "truncated": pack.truncated,
        },
    }


def _action_out(row: dict, pack: context_service.ContextPack | None = None) -> dict:
    """Shape one action row for the API, enriching it with its item's identity."""
    topic = platform = ""
    if pack:
        for item in pack.items:
            if item["id"] == row["item_id"]:
                topic, platform = item["topic"], item["platform"]
                break
        if not topic:
            for review in pack.review:
                if review["item_id"] == row["item_id"]:
                    topic, platform = review["topic"], review["platform"]
                    break
    return {
        "id": row["id"],
        # Needed by the frontend to re-attach actions to their bubble when a
        # conversation is reloaded; the batch fetch returns them flat.
        "message_id": row.get("message_id"),
        "verb": row["verb"],
        "label": row["label"],
        "item_id": row["item_id"],
        "content_id": row.get("content_id"),
        "item_topic": topic,
        "item_platform": platform,
        "params": row.get("params") or {},
        "status": row["status"],
        "expires_at": row["expires_at"],
    }


async def confirm(
    session: AsyncSession,
    user_id: str,
    action_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Execute a proposed action. The only path that writes planner data."""
    row = await queries.get_assistant_action(session, action_id, user_id, for_update=True)
    if not row:
        # 404 for both "does not exist" and "not yours", deliberately
        # indistinguishable — the id is a capability, and probing it should not
        # reveal whether someone else holds one.
        raise HTTPException(status_code=404, detail="That suggestion is no longer available.")

    if row["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail=f"That suggestion was already {row['status']}.",
        )
    if _is_expired(row):
        await queries.update_assistant_action(session, action_id, user_id, status="expired")
        raise HTTPException(
            status_code=409, detail="That suggestion expired. Ask again to get a fresh one."
        )

    # Flip before any planner write, so a double-click's second request finds
    # 'executing' and stops rather than repeating the mutation.
    await queries.update_assistant_action(session, action_id, user_id, status="executing")

    try:
        result = await action_service.execute_action(session, user_id, row, background_tasks)
    except HTTPException:
        await queries.update_assistant_action(session, action_id, user_id, status="proposed")
        raise
    except Exception as exc:
        logger.exception("assistant: action %s failed", action_id)
        await queries.update_assistant_action(
            session, action_id, user_id, status="failed", result={"error": str(exc)[:500]}
        )
        raise HTTPException(status_code=502, detail=f"That action failed: {exc}")

    await queries.update_assistant_action(
        session, action_id, user_id,
        status="executed",
        result={"dispatched": result.get("dispatched", [])},
        executed_at=_now(),
    )
    updated = await queries.get_assistant_action(session, action_id, user_id)
    return {
        "action": _action_out(updated),
        "item": result.get("item"),
        "content": result.get("content"),
        "dispatched": result.get("dispatched", []),
    }


async def cancel(session: AsyncSession, user_id: str, action_id: str) -> dict:
    row = await queries.get_assistant_action(session, action_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="That suggestion is no longer available.")
    if row["status"] != "proposed":
        raise HTTPException(
            status_code=409, detail=f"That suggestion was already {row['status']}."
        )
    await queries.update_assistant_action(session, action_id, user_id, status="cancelled")
    updated = await queries.get_assistant_action(session, action_id, user_id)
    return {"action": _action_out(updated)}


def _is_expired(row: dict) -> bool:
    """Rows come back with ISO-string timestamps (see db/_util._iso)."""
    from datetime import datetime

    raw = row.get("expires_at")
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return False
    return expires < _now()


async def digest(session: AsyncSession, user_id: str) -> dict:
    """Today at a glance, with no LLM involved.

    Worth its own endpoint twice over: the chat page renders it instantly
    instead of showing an empty box for eight seconds, and it is the debug
    surface that separates "retrieval is wrong" from "the prompt is wrong".
    """
    today = user_today()
    week_start, week_end = week_bounds(today)

    plan = default_plan(today)
    pack = await context_service.build_context(session, user_id, plan, today=today)

    week_items = await queries.get_plan_items_across_platforms(
        session, user_id,
        date_from=week_start.isoformat(),
        date_to=week_end.isoformat(),
        order="scheduled",
        limit=200,
    )

    overdue = 0
    try:
        analytics = await queries.get_planner_analytics(
            session, user_id, today=user_today_iso()
        )
        overdue = (analytics.get("schedule") or {}).get("overdue") or 0
    except Exception as exc:
        logger.warning("assistant: digest analytics failed for %s: %s", user_id, exc)

    return {
        "today": today.isoformat(),
        "week_from": week_start.isoformat(),
        "week_to": week_end.isoformat(),
        "items_today": pack.items,
        "items_this_week": len(week_items),
        "pending_review": len([r for r in pack.review if r["review_status"] == "ready"]),
        "backlog_uncovered": pack.backlog_total,
        "overdue": overdue,
    }


async def get_conversation_detail(
    session: AsyncSession, user_id: str, conversation_id: str
) -> dict:
    conversation = await queries.get_assistant_conversation(session, conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await queries.get_assistant_messages(session, conversation_id, user_id)
    action_rows = await queries.get_assistant_actions_for_messages(
        session, [m["id"] for m in messages], user_id
    )
    return {
        "conversation": conversation,
        "messages": messages,
        "actions": [_action_out(a) for a in action_rows],
    }
