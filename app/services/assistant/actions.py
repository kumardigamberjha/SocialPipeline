"""Validating and executing the assistant's proposed writes.

This is the security boundary. Nothing the model emits is trusted here — not the
ids, not the status values, not the wording on the button.

Two gates run at proposal time and both run again at confirm time:

1. **Pack membership.** The id must be one the model was actually shown on this
   turn. An id it invented, or carried over from an earlier conversation, is
   rejected before any database access.
2. **Owner-scoped re-read.** The row is fetched with ``user_id`` in the WHERE
   clause. This is redundant with (1) — the pack is already user-scoped — and
   that is the point: two independent gates, so neither one being wrong is
   sufficient to leak or mutate another tenant's data.

Confirm-time re-validation is not optional. Up to 24 hours can pass between
proposal and confirmation, and the user may have done the same thing by hand in
the Planner meanwhile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import parse_iso_date, user_today
from app.db import queries
from app.models.planner import (
    GENERATION_PLATFORMS,
    TIME_PATTERN,
    VIDEO_PLATFORMS,
)
from app.services.assistant.context import ContextPack, sanitize
from app.services.assistant.schemas import ProposedAction

logger = logging.getLogger(__name__)

import re

_TIME_RE = re.compile(TIME_PATTERN)

# At most this many actions survive one assistant message. Three confirm buttons
# is already a lot to put in front of someone who asked a question.
MAX_ACTIONS = 3

# How long a proposal stays confirmable.
ACTION_TTL = timedelta(hours=24)

# A reschedule beyond this is far likelier to be a mis-parsed date than intent.
MAX_RESCHEDULE_DAYS = 365

_PLATFORM_DEFAULT_CONTENT_TYPE = {
    "youtube": "youtube_script",
    "linkedin": "linkedin",
    "blog": "blog",
}

_HUMAN_PLATFORM = {
    "youtube": "YouTube",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "blog": "Blog",
    "x": "X",
    "tiktok": "TikTok",
}


@dataclass
class ValidatedAction:
    """A proposal that survived validation, ready to persist."""

    verb: str
    item_id: str
    label: str
    params: dict
    content_id: Optional[str] = None


def target_published_status(platform: str) -> str:
    """The 'published' value for this platform's status vocabulary.

    YouTube runs the video pipeline and ends at ``video_published``; everything
    else ends at ``published``. Computed here in Python and never taken from the
    model — ``production_status`` has no CHECK constraint in the database, so a
    bad string would be written silently.
    """
    return "video_published" if platform in VIDEO_PLATFORMS else "published"


def _human_platform(platform: str) -> str:
    return _HUMAN_PLATFORM.get(platform, (platform or "").title())


# ── Proposal-time validation ─────────────────────────────────────────────────


async def validate_proposal(
    session: AsyncSession,
    user_id: str,
    action: ProposedAction,
    pack: ContextPack,
) -> ValidatedAction | None:
    """Return a persistable action, or None to drop it silently.

    Dropping rather than erroring is deliberate: the prose answer is still
    useful, and a user who asked a question should not get a 500 because the
    model attached a bad suggestion to a correct answer. Every drop is logged.
    """
    verb = action.verb

    if verb in ("approve_draft", "reject_draft"):
        return await _validate_review(session, user_id, action, pack)

    item_id = _resolve_id(action.item_id, pack.item_ids)
    if item_id is None:
        logger.warning(
            "assistant: dropped %s — item_id %r not in this turn's context pack",
            verb, action.item_id,
        )
        return None

    item = await queries.get_plan_item_by_id(session, item_id, user_id)
    if not item:
        logger.warning("assistant: dropped %s — item %s not owned by %s", verb, item_id, user_id)
        return None

    platform = item.get("platform") or "youtube"
    topic = sanitize(item.get("topic"), 80)

    if verb == "mark_published":
        target = target_published_status(platform)
        if item.get("production_status") == target:
            logger.info("assistant: dropped mark_published — item %s already %s", item_id, target)
            return None
        return ValidatedAction(
            verb=verb,
            item_id=item_id,
            label=f'Mark "{topic}" ({_human_platform(platform)}) as published',
            params={"production_status": target},
        )

    if verb == "reschedule":
        when = parse_iso_date(action.scheduled_date)
        if when is None:
            logger.warning("assistant: dropped reschedule — unparseable date %r", action.scheduled_date)
            return None
        today = user_today()
        if abs((when - today).days) > MAX_RESCHEDULE_DAYS:
            logger.warning("assistant: dropped reschedule — %s is out of range", when)
            return None
        params: dict[str, Any] = {"scheduled_date": when.isoformat()}
        # A malformed time must not sink an otherwise valid reschedule.
        if action.event_time and _TIME_RE.match(action.event_time.strip()):
            params["event_time"] = action.event_time.strip()
        label = f'Reschedule "{topic}" to {when.isoformat()}'
        if "event_time" in params:
            label += f' at {params["event_time"]}'
        return ValidatedAction(verb=verb, item_id=item_id, label=label, params=params)

    if verb == "generate_content":
        if platform not in GENERATION_PLATFORMS:
            logger.warning(
                "assistant: dropped generate_content — %s is not a generation platform", platform
            )
            return None
        content_type = action.content_type or _PLATFORM_DEFAULT_CONTENT_TYPE.get(platform)
        if not content_type:
            return None
        return ValidatedAction(
            verb=verb,
            item_id=item_id,
            label=f'Generate the {content_type.replace("_", " ")} for "{topic}" (uses 1 run)',
            params={"content_type": content_type},
        )

    return None


async def _validate_review(
    session: AsyncSession,
    user_id: str,
    action: ProposedAction,
    pack: ContextPack,
) -> ValidatedAction | None:
    from app.services import plan_service

    content_id = _resolve_id(action.content_id, pack.content_ids)
    if content_id is None:
        logger.warning(
            "assistant: dropped %s — content_id %r not in this turn's context pack",
            action.verb, action.content_id,
        )
        return None

    content = await queries.get_plan_item_content_by_id(session, content_id, user_id)
    if not content:
        logger.warning("assistant: dropped %s — content %s not owned", action.verb, content_id)
        return None

    # Judge state only after reconciling: a row still reading 'generating' may
    # have finished, and telling the user there is nothing to review when a
    # draft is sitting ready is the worst answer this path can give.
    content = await plan_service.reconcile_plan_item_content(session, content)
    if content["review_status"] not in ("ready", "approved", "rejected"):
        logger.info(
            "assistant: dropped %s — content %s is %s",
            action.verb, content_id, content["review_status"],
        )
        return None

    approving = action.verb == "approve_draft"
    already = "approved" if approving else "rejected"
    if content["review_status"] == already:
        logger.info("assistant: dropped %s — content %s already %s", action.verb, content_id, already)
        return None

    item = await queries.get_plan_item_by_id(session, content["item_id"], user_id)
    if not item:
        return None
    platform = item.get("platform") or "youtube"
    topic = sanitize(item.get("topic"), 80)
    kind = (content.get("content_type") or "draft").replace("_", " ")

    params: dict[str, Any] = {}
    label = f'{"Approve" if approving else "Reject"} the {kind} draft for "{topic}"'
    if not approving and action.regenerate:
        # A regenerate re-runs the same pipeline, so it needs the same guard the
        # generate action does — but a platform mismatch downgrades the flag
        # rather than dropping a perfectly valid rejection.
        if platform in GENERATION_PLATFORMS:
            params["regenerate"] = True
            label += " and generate a replacement (uses 1 run)"
        else:
            logger.info(
                "assistant: dropped regenerate flag — %s is not a generation platform", platform
            )

    return ValidatedAction(
        verb=action.verb,
        item_id=content["item_id"],
        content_id=content_id,
        label=label,
        params=params,
    )


def _resolve_id(candidate: str | None, allowed: set[str]) -> str | None:
    """Match a model-supplied id against the ids it was shown.

    The context block renders ids as their first 8 characters so weak models
    reproduce them verbatim, so a proposal may name either form. Only exact
    matches against the pack are accepted, and an ambiguous short id — two rows
    sharing a prefix — is refused rather than guessed.
    """
    if not candidate:
        return None
    value = str(candidate).strip().strip("[]")
    if value in allowed:
        return value
    matches = [full for full in allowed if full.startswith(value)]
    return matches[0] if len(matches) == 1 else None


async def persist_actions(
    session: AsyncSession,
    user_id: str,
    message_id: str,
    validated: list[ValidatedAction],
) -> list[dict]:
    from app.db.queries import _now  # single source of "now" for this layer

    expires_at = _now() + ACTION_TTL
    rows = []
    for action in validated[:MAX_ACTIONS]:
        rows.append(
            await queries.create_assistant_action(
                session,
                message_id=message_id,
                user_id=user_id,
                item_id=action.item_id,
                content_id=action.content_id,
                verb=action.verb,
                label=action.label,
                params=action.params,
                expires_at=expires_at,
            )
        )
    return rows


# ── Confirm-time execution ───────────────────────────────────────────────────


async def execute_action(
    session: AsyncSession,
    user_id: str,
    row: dict,
    background_tasks: BackgroundTasks,
) -> dict:
    """Run one confirmed action. Assumes the caller already locked the row.

    Raises HTTPException on anything the user needs to be told about: 404 when
    the target vanished, 409 when the world moved on since the proposal, 429
    straight through from the quota gate.
    """
    from app.services import plan_service

    verb = row["verb"]
    params = row.get("params") or {}

    if verb in ("approve_draft", "reject_draft"):
        content = await queries.get_plan_item_content_by_id(session, row["content_id"], user_id)
        if not content:
            raise HTTPException(status_code=404, detail="That draft no longer exists.")
        content = await plan_service.reconcile_plan_item_content(session, content)

        approving = verb == "approve_draft"
        already = "approved" if approving else "rejected"
        if content["review_status"] == already:
            raise HTTPException(status_code=409, detail=f"That draft was already {already}.")

        result = await plan_service.apply_review(
            session,
            content,
            action="approve" if approving else "reject",
            regenerate=bool(params.get("regenerate")),
            provider=None,  # resolve from the original run inside apply_review
            background_tasks=background_tasks,
        )
        item = await queries.get_plan_item_by_id(session, row["item_id"], user_id)
        return {
            "item": item,
            "content": result.get("content"),
            "dispatched": result.get("dispatched", []),
        }

    item = await queries.get_plan_item_by_id(session, row["item_id"], user_id)
    if not item:
        raise HTTPException(status_code=404, detail="That item no longer exists.")
    platform = item.get("platform") or "youtube"

    if verb == "mark_published":
        target = target_published_status(platform)
        if item.get("production_status") == target:
            raise HTTPException(status_code=409, detail="That item is already published.")
        await queries.update_plan_item(session, item["id"], user_id, production_status=target)
        item = await _refresh_and_sync(session, item["id"], user_id)
        return {"item": item, "dispatched": []}

    if verb == "reschedule":
        kwargs: dict[str, Any] = {"scheduled_date": params.get("scheduled_date")}
        if params.get("event_time"):
            kwargs["event_time"] = params["event_time"]
        await queries.update_plan_item(session, item["id"], user_id, **kwargs)
        # Mandatory here, not best-effort-optional: a reschedule that moves the
        # row but not the calendar event is the most damaging silent failure in
        # this feature.
        item = await _refresh_and_sync(session, item["id"], user_id)
        return {"item": item, "dispatched": []}

    if verb == "generate_content":
        if platform not in GENERATION_PLATFORMS:
            raise HTTPException(
                status_code=409,
                detail=f"Content generation is not available for {platform} items.",
            )
        plan = await queries.get_content_plan_by_id(session, item["plan_id"], user_id)
        dispatched = await plan_service.dispatch_generation(
            session,
            item,
            params.get("content_type") or _PLATFORM_DEFAULT_CONTENT_TYPE.get(platform, "blog"),
            "nvidia",
            (plan or {}).get("niche") or "ai",
            background_tasks,
        )
        return {"item": item, "dispatched": dispatched}

    raise HTTPException(status_code=409, detail=f"Unsupported action: {verb}")


async def _refresh_and_sync(session: AsyncSession, item_id: str, user_id: str) -> dict:
    from app.services import plan_service

    item = await queries.get_plan_item_by_id(session, item_id, user_id)
    if item and item.get("gcal_event_id"):
        await plan_service.sync_calendar_event(session, item["plan_id"], item, user_id)
        item = await queries.get_plan_item_by_id(session, item_id, user_id)
    return item
