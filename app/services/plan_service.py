"""
Content-plan domain logic: generation dispatch and lazy status reconciliation.

Reconciliation design
---------------------
plan_item_content rows are created with review_status='generating' and a run_id.
The pipelines themselves (Celery tasks / BackgroundTasks fallbacks) know nothing
about plans — they just write their content row and flip the agent_run status.
Whenever plan data is read, reconcile_plan_item_content() checks each
'generating' row against its run: on 'completed' it links the produced content
row (content_ref_id) and marks 'ready'; on 'failed' it marks 'failed'. A
completed youtube_script also auto-advances the owning item's production_status
from 'pending' to 'script_generated'.
"""

import logging

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries
from app.db.tables import BlogPost, LinkedinPost, YoutubeScript
from app.models.planner import VIDEO_PLATFORMS
from app.services.dispatch import (
    CONTENT_LOOKUP,
    CONTENT_TYPES,
    dispatch_pipeline,
)

logger = logging.getLogger(__name__)

# Re-exported under the names this module has always used, so existing callers
# and the reconcile path below are unaffected by the move into dispatch.py.
_CONTENT_LOOKUP = CONTENT_LOOKUP


# ── Reconciliation ───────────────────────────────────────────────────────────


async def reconcile_plan_item_content(session: AsyncSession, content: dict) -> dict:
    """Advance a 'generating' content row from its run's terminal state.
    Returns the (possibly updated) row."""
    if content["review_status"] != "generating" or not content.get("run_id"):
        return content

    user_id = content["user_id"]
    run = await queries.get_run_by_id(session, content["run_id"], user_id)
    if not run or run["status"] in ("pending", "running"):
        return content

    if run["status"] == "failed":
        await queries.update_plan_item_content(session, content["id"], user_id, review_status="failed")
        content["review_status"] = "failed"
        return content

    # run completed — link the produced content row
    rows = await _CONTENT_LOOKUP[content["content_type"]](session, content["run_id"], user_id)
    if not rows:
        # Completed run but no saved row (should not happen) — surface as failed.
        await queries.update_plan_item_content(session, content["id"], user_id, review_status="failed")
        content["review_status"] = "failed"
        return content

    ref_id = rows[-1]["id"]
    await queries.update_plan_item_content(session, content["id"], user_id,
                                           content_ref_id=ref_id, review_status="ready")
    content["content_ref_id"] = ref_id
    content["review_status"] = "ready"

    if content["content_type"] == "youtube_script":
        item = await queries.get_plan_item_by_id(session, content["item_id"], user_id)
        # Only advance items that actually run the video pipeline: on any other
        # platform 'script_generated' is not a column the board can render, so a
        # stray generation would make the card disappear from its Kanban.
        if (
            item
            and item["production_status"] == "pending"
            and (item.get("platform") or "youtube") in VIDEO_PLATFORMS
        ):
            await queries.update_plan_item(session, item["id"], user_id,
                                           production_status="script_generated")

    return content


async def get_item_contents_reconciled(session: AsyncSession, item_id: str, user_id: str) -> list[dict]:
    contents = await queries.get_plan_item_contents(session, item_id, user_id)
    return [await reconcile_plan_item_content(session, c) for c in contents]


async def get_plan_detail(session: AsyncSession, plan_id: str, user_id: str) -> dict | None:
    """Plan + items + reconciled content summaries — the planner UI's main read."""
    plan = await queries.get_content_plan_by_id(session, plan_id, user_id)
    if not plan:
        return None
    items = await queries.get_plan_items(session, plan_id, user_id)
    for item in items:
        item["contents"] = await get_item_contents_reconciled(session, item["id"], user_id)
        # Reconciliation may have advanced production_status — re-read cheaply.
        if any(c["content_type"] == "youtube_script" and c["review_status"] == "ready" for c in item["contents"]):
            fresh = await queries.get_plan_item_by_id(session, item["id"], user_id)
            if fresh:
                item["production_status"] = fresh["production_status"]
    plan["items"] = items
    return plan


# ── Content hydration (review modal) ─────────────────────────────────────────


async def hydrate_content(session: AsyncSession, content: dict) -> dict:
    """Attach title/body from the source table to a plan_item_content row."""
    hydrated = dict(content)
    hydrated["title"] = None
    hydrated["body"] = None
    hydrated["meta"] = {}
    ref_id, user_id = content.get("content_ref_id"), content["user_id"]
    if not ref_id:
        return hydrated

    if content["content_type"] == "linkedin":
        row = await queries.get_linkedin_post_by_id(session, ref_id, user_id)
        if row:
            hydrated["title"] = row["hook"]
            hydrated["body"] = row["post_text"]
            hydrated["meta"] = {"word_count": row["word_count"], "hashtag_count": row["hashtag_count"],
                                "angle_type": row["angle_type"], "pipeline_approved": bool(row["approved"])}
    elif content["content_type"] == "blog":
        row = await queries.get_blog_by_id(session, ref_id, user_id)
        if row:
            hydrated["title"] = row["title"]
            hydrated["body"] = row["content"]
            hydrated["meta"] = {"word_count": row["word_count"], "slug": row["slug"],
                                "reading_time_minutes": row["reading_time_minutes"],
                                "pipeline_approved": bool(row["approved"])}
    elif content["content_type"] == "youtube_script":
        row = await queries.get_youtube_script_by_id(session, ref_id, user_id)
        if row:
            hydrated["title"] = row["title"]
            hydrated["body"] = row["script"]
            hydrated["meta"] = {"word_count": row["word_count"], "seo_title": row["seo_title"],
                                "seo_description": row["seo_description"], "seo_tags": row["seo_tags"],
                                "pipeline_approved": bool(row["approved"])}
    return hydrated


# Content type -> the table holding the body. A mapped class, not an
# interpolated table name: the previous version built the UPDATE with an
# f-string, which only stayed safe because the key came from a literal dict.
_SOURCE_MODEL = {
    "linkedin": LinkedinPost,
    "blog": BlogPost,
    "youtube_script": YoutubeScript,
}


async def set_source_approved(session: AsyncSession, content: dict, approved: bool) -> None:
    """Persist the human decision on the underlying content table too."""
    ref_id = content.get("content_ref_id")
    if not ref_id:
        return
    model = _SOURCE_MODEL[content["content_type"]]
    await session.execute(
        update(model)
        .where(model.id == ref_id, model.user_id == content["user_id"])
        .values(approved=approved)
    )


# ── Dispatch ─────────────────────────────────────────────────────────────────


async def _remaining_quota(session: AsyncSession, user_id: str) -> int:
    await queries.reset_usage_if_expired(session, user_id)
    usage = await queries.get_usage(session, user_id)
    if not usage:
        await queries.init_usage(session, user_id)
        usage = await queries.get_usage(session, user_id)
    if not usage:
        return 0
    return max(0, usage["max_runs_per_month"] - usage["runs_this_month"])


async def dispatch_item_content(session: AsyncSession, item: dict, content_type: str,
                                provider: str, niche: str,
                                background_tasks: BackgroundTasks) -> dict:
    """Create a run + plan_item_content link and dispatch one pipeline.
    Returns {content_type, run_id, content_id}."""
    user_id = item["user_id"]
    topic = item["topic"]
    run = await queries.create_run(session, user_id, topic, provider)
    run_id = run["id"]
    content = await queries.create_plan_item_content(session, item["id"], user_id, content_type, run_id)

    dispatch_pipeline(
        content_type=content_type,
        run_id=run_id,
        topic=topic,
        niche=niche,
        user_id=user_id,
        provider=provider,
        video_format=item.get("video_format") or "full",
        background_tasks=background_tasks,
    )

    return {"content_type": content_type, "run_id": run_id, "content_id": content["id"]}


async def dispatch_generation(session: AsyncSession, item: dict, content_type: str,
                              provider: str, niche: str,
                              background_tasks: BackgroundTasks) -> list[dict]:
    """Dispatch one content type or all three, gating on remaining quota upfront."""
    types = list(CONTENT_TYPES) if content_type == "all" else [content_type]
    remaining = await _remaining_quota(session, item["user_id"])
    if remaining < len(types):
        raise HTTPException(
            status_code=429,
            detail=f"Not enough runs left this month: need {len(types)}, have {remaining}. Nothing was dispatched.",
        )
    return [
        await dispatch_item_content(session, item, t, provider, niche, background_tasks)
        for t in types
    ]


# ── Shared router logic ──────────────────────────────────────────────────────
#
# These two lived inside app/routers/planner.py as handler-local code. They moved
# here when the assistant gained the ability to perform the same operations: a
# FastAPI handler cannot be called in-process (its signature is Depends-shaped)
# and an internal HTTP call would have to forge auth cookies and CSRF, so the
# only honest way to share the behaviour is to share the function. The routers
# import them back under their original names, so their call sites are unchanged.


async def sync_calendar_event(
    session: AsyncSession, plan_id: str, item: dict, user_id: str
) -> None:
    """Best-effort push of item changes to its Google Calendar event.

    Never fails the edit: on a missing event the local link is cleared; other
    errors are logged. A reschedule that silently fails to move the calendar
    event is the most damaging failure mode this code has, which is exactly why
    there must be only one copy of the recovery logic.
    """
    import asyncio

    from app.services import google_calendar

    plan = await queries.get_content_plan_by_id(session, plan_id, user_id)
    try:
        # Blocking HTTPS call to Google — off the event loop, or it stalls every
        # other request in this worker for the round trip.
        await asyncio.to_thread(
            google_calendar.update_event_for_item,
            user_id, item, plan["name"] if plan else "Content plan",
        )
    except google_calendar.EventGoneError:
        logger.info("Calendar event for item %s was deleted in Google; clearing link.", item["id"])
        await queries.clear_plan_item_calendar_event(session, item["id"], user_id)
    except google_calendar.CalendarError as exc:
        # Includes NotConnectedError — the edit still saved locally.
        logger.warning("Calendar sync failed for item %s: %s", item["id"], exc)


async def apply_review(
    session: AsyncSession,
    content: dict,
    action: str,
    regenerate: bool = False,
    provider: str | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Persist a human review decision, optionally re-dispatching generation.

    ``content`` must already be reconciled by the caller — judging review state
    from a stale 'generating' row is the most likely wrong answer this path can
    give.

    ``provider=None`` resolves the provider from the run that produced the
    rejected draft, so a regenerate reuses whatever tier wrote the original.
    That fallback is the main reason this is shared rather than reimplemented:
    a second copy would quietly regress to always-'nvidia'.

    Returns ``{"content": ..., "dispatched": [...]}`` — 'dispatched' only on a
    reject-and-regenerate. Raises HTTPException(409) when the row is not
    reviewable, and lets dispatch_generation's HTTPException(429) propagate.
    """
    if content["review_status"] not in ("ready", "approved", "rejected"):
        raise HTTPException(
            status_code=409,
            detail=f"Content is not reviewable (status: {content['review_status']})",
        )

    user_id = content["user_id"]
    new_status = "approved" if action == "approve" else "rejected"
    await queries.update_plan_item_content(
        session, content["id"], user_id, review_status=new_status
    )
    await set_source_approved(session, content, action == "approve")
    content["review_status"] = new_status

    result: dict = {"content": content}
    if action == "reject" and regenerate and background_tasks is not None:
        item = await queries.get_plan_item_by_id(session, content["item_id"], user_id)
        plan = (
            await queries.get_content_plan_by_id(session, item["plan_id"], user_id)
        ) if item else None
        if item:
            run = (
                await queries.get_run_by_id(session, content["run_id"], user_id)
            ) if content.get("run_id") else None
            resolved_provider = provider or (run and run.get("provider_used")) or "nvidia"
            result["dispatched"] = await dispatch_generation(
                session, item, content["content_type"], resolved_provider,
                (plan or {}).get("niche") or "ai", background_tasks,
            )
    return result
