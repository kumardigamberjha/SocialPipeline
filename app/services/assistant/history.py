"""Conversation persistence and the prompt's history window.

The window is small on purpose. This is a task assistant, not a companion:
questions are near-independent, and the only carry-over that actually matters is
one hop of anaphora — "usko kal shift kar do" referring to an item named in the
previous answer.

The important rule here is what is NOT replayed: a previous turn's context pack
never re-enters the prompt. Stale rows returning is exactly how an assistant ends
up saying an item is pending that the user published an hour ago. Instead the
assistant message carries `meta.last_items` — ids and topics only — which is
replayed as one line and re-validated against the *current* pack before any
action can touch it.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries

logger = logging.getLogger(__name__)

HISTORY_TURNS = 6          # 3 user/assistant exchanges
RESOLVER_TURNS = 2         # the resolver only needs anaphora
USER_CHARS = 500
ASSISTANT_CHARS = 400
HISTORY_CHAR_BUDGET = 3_000
MAX_LAST_ITEMS = 5
TITLE_CHARS = 60


async def ensure_conversation(
    session: AsyncSession, user_id: str, conversation_id: str | None, title_seed: str
) -> dict:
    """Fetch the named conversation, or start one titled from the question."""
    if conversation_id:
        existing = await queries.get_assistant_conversation(session, conversation_id, user_id)
        if existing:
            return existing
        # A stale id from a deleted thread starts a fresh one rather than 404ing
        # the user's question — they typed something; it should get an answer.
        logger.info("assistant: conversation %s not found for %s; starting a new one",
                    conversation_id, user_id)

    title = (title_seed or "New chat").strip()[:TITLE_CHARS] or "New chat"
    return await queries.create_assistant_conversation(session, user_id, title)


async def load_history(
    session: AsyncSession, user_id: str, conversation_id: str, turns: int = HISTORY_TURNS
) -> list[dict]:
    return await queries.get_recent_assistant_messages(
        session, conversation_id, user_id, limit=turns
    )


def _last_items_line(meta: dict) -> str:
    items = (meta or {}).get("last_items") or []
    if not isinstance(items, list) or not items:
        return ""
    rendered = "; ".join(
        f"[{i.get('short_id')}] {i.get('topic')} ({i.get('platform')})"
        for i in items[:MAX_LAST_ITEMS]
        if isinstance(i, dict)
    )
    return f"\n(previously referenced: {rendered})" if rendered else ""


def trim_history(rows: list[dict], turns: int = HISTORY_TURNS) -> list[dict]:
    """Role + content only, truncated, oldest dropped first when over budget."""
    out: list[dict] = []
    for row in rows[-turns:]:
        role = row.get("role", "user")
        limit = USER_CHARS if role == "user" else ASSISTANT_CHARS
        content = (row.get("content") or "").strip()[:limit]
        if role == "assistant":
            content += _last_items_line(row.get("meta") or {})
        out.append({"role": role, "content": content})

    while out and sum(len(m["content"]) for m in out) > HISTORY_CHAR_BUDGET:
        out.pop(0)
    return out


def last_language(rows: list[dict]) -> str | None:
    """The language of the most recent assistant turn, for short-turn inheritance."""
    for row in reversed(rows):
        if row.get("role") == "assistant":
            lang = (row.get("meta") or {}).get("language")
            if lang in ("en", "hinglish"):
                return lang
    return None
