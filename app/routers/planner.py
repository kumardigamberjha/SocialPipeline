"""
Content planner REST router.

Weekly/monthly content plans with dated topic items, per-item production status
(pending → script_generated → … → video_published), per-item content generation
(LinkedIn / Blog / YouTube script via the existing pipelines), a persisted
human review/approve flow, and Google Calendar scheduling.

Generation runs asynchronously (Celery or BackgroundTasks fallback); the UI
polls GET /api/plans/{plan_id}, whose read path lazily reconciles 'generating'
content rows against their runs (see app.services.plan_service).
"""

import asyncio
import calendar as _calendar
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.core.clock import user_today_iso
from app.db import queries
from app.db.session import get_session
from app.models.planner import (
    GENERATION_PLATFORMS,
    IMAGE_PLATFORMS,
    CalendarAddRequest,
    GenerateContentRequest,
    GenerateImageRequest,
    PlanCreateRequest,
    PlanItemIn,
    PlanItemUpdate,
    PlanUpdateRequest,
    ReviewActionRequest,
    SuggestTopicsRequest,
    status_order,
)
from app.services import plan_service
from app.services.gemini_image_client import OUTPUT_DIR as IMAGE_DIR, GeminiImageClient
from app.services.topic_suggester import NotSyncedError, suggest_topics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["planner"])

_image_client = GeminiImageClient()


# ── Topic suggestion ─────────────────────────────────────────────────────────


@router.post("/suggest-topics")
async def suggest_plan_topics(request: SuggestTopicsRequest,
                              current_user: dict = Depends(get_current_user),
                              session: AsyncSession = Depends(get_session)):
    try:
        topics = await suggest_topics(
            session=session,
            user_id=current_user["id"],
            plan_type=request.plan_type,
            niche=request.niche,
            start_date=request.start_date,
            count=request.count,
            provider=request.provider,
            platform=request.platform,
        )
    except NotSyncedError as exc:
        # The platform has nothing to ground on — a user problem, not a 502.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Topic suggestion failed")
        raise HTTPException(status_code=502, detail=f"Topic suggestion failed: {exc}")
    return {"topics": topics}


# ── Plans ────────────────────────────────────────────────────────────────────


@router.post("")
async def create_plan(request: PlanCreateRequest,
                      current_user: dict = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    start = request.start_date
    if request.plan_type == "weekly":
        end = start + timedelta(days=6)
    elif request.plan_type == "board":
        # An open-ended Kanban plan has no period to compute.
        end = start
    else:
        end = start + timedelta(days=_calendar.monthrange(start.year, start.month)[1] - 1)

    plan = await queries.create_content_plan(
        session, current_user["id"], request.name, request.plan_type, request.niche,
        start.isoformat(), end.isoformat(), platform=request.platform,
    )
    for item in request.items:
        await queries.create_plan_item(
            session, plan["id"], current_user["id"], item.topic,
            item.scheduled_date.isoformat() if item.scheduled_date else None,
            item.notes, item.topic_source,
            publish_date=item.publish_date.isoformat() if item.publish_date else None,
            video_format=item.video_format,
            event_time=item.event_time,
            event_duration_minutes=item.event_duration_minutes,
            platform=request.platform,
            meta=item.meta,
            production_status=item.production_status,
        )
    return await plan_service.get_plan_detail(session, plan["id"], current_user["id"])


@router.get("")
async def list_plans(platform: str | None = None,
                     current_user: dict = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    """Plans for one platform, or every platform when `platform` is omitted."""
    return await queries.get_content_plans(session, current_user["id"], platform)


# Declared BEFORE "/{plan_id}" so the static "/stats" path is not captured as a plan id.
@router.get("/stats")
async def get_planner_stats(platform: str | None = None,
                            current_user: dict = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session)):
    """Aggregate planner metrics for the analytics dashboard.

    Without `platform` the figures are cross-platform totals; the funnel then
    lists one vocabulary's stages and will not sum to `total_items`.

    `today` is passed explicitly so the overdue/upcoming split is anchored to the
    user's timezone rather than the database session's — in a UTC container those
    disagree by a full day between 00:00 and 05:30 IST, which would show this page
    a different overdue count from the assistant's.
    """
    return await queries.get_planner_analytics(
        session, current_user["id"], platform, today=user_today_iso()
    )


# ── Board / calendar reads (declared before "/{plan_id}") ────────────────────


@router.get("/board")
async def get_board(platform: str = "youtube",
                    plan_id: str | None = None,
                    current_user: dict = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    """Every item on a platform plus its Kanban column order.

    Returns the column order alongside the items so one endpoint serves every
    platform — the client does not need a per-platform status table.
    """
    items = await queries.get_plan_items_by_platform(
        session, current_user["id"], platform, plan_id=plan_id, order="created_desc"
    )
    return {
        "platform": platform,
        "plan_id": plan_id,
        "statuses": list(status_order(platform)),
        "items": items,
    }


@router.post("/board/items")
async def add_board_item(request: PlanItemIn, platform: str = "youtube",
                         current_user: dict = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    """Quick-add onto a platform's board without knowing a plan id."""
    plan = await queries.get_or_create_board_plan(session, current_user["id"], platform)
    return await queries.create_plan_item(
        session, plan["id"], current_user["id"], request.topic,
        request.scheduled_date.isoformat() if request.scheduled_date else None,
        request.notes, request.topic_source,
        publish_date=request.publish_date.isoformat() if request.publish_date else None,
        video_format=request.video_format,
        event_time=request.event_time,
        event_duration_minutes=request.event_duration_minutes,
        platform=platform,
        meta=request.meta,
        production_status=request.production_status,
    )


@router.get("/items")
async def list_items_across_plans(platform: str = "youtube",
                                  date_from: str | None = None,
                                  date_to: str | None = None,
                                  current_user: dict = Depends(get_current_user),
                                  session: AsyncSession = Depends(get_session)):
    """Cross-plan calendar feed for one platform."""
    return await queries.get_plan_items_by_platform(
        session, current_user["id"], platform,
        date_from=date_from, date_to=date_to, order="scheduled",
    )


@router.get("/{plan_id}")
async def get_plan(plan_id: str, current_user: dict = Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)):
    plan = await plan_service.get_plan_detail(session, plan_id, current_user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/{plan_id}")
async def update_plan(plan_id: str, request: PlanUpdateRequest,
                      current_user: dict = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    if not await queries.update_content_plan(session, plan_id, current_user["id"],
                                             name=request.name, status=request.status):
        raise HTTPException(status_code=404, detail="Plan not found or nothing to update")
    return await queries.get_content_plan_by_id(session, plan_id, current_user["id"])


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, current_user: dict = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    if not await queries.delete_content_plan(session, plan_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted"}


# ── Plan items ───────────────────────────────────────────────────────────────


async def _get_owned_item(session: AsyncSession, plan_id: str, item_id: str, user_id: str) -> dict:
    item = await queries.get_plan_item_by_id(session, item_id, user_id)
    if not item or item["plan_id"] != plan_id:
        raise HTTPException(status_code=404, detail="Plan item not found")
    return item


@router.post("/{plan_id}/items")
async def add_plan_item(plan_id: str, request: PlanItemIn,
                        current_user: dict = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    plan = await queries.get_content_plan_by_id(session, plan_id, current_user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return await queries.create_plan_item(
        session, plan_id, current_user["id"], request.topic,
        request.scheduled_date.isoformat() if request.scheduled_date else None,
        request.notes, request.topic_source,
        publish_date=request.publish_date.isoformat() if request.publish_date else None,
        video_format=request.video_format,
        event_time=request.event_time,
        event_duration_minutes=request.event_duration_minutes,
        platform=plan.get("platform"),
        meta=request.meta,
        production_status=request.production_status,
    )


@router.patch("/{plan_id}/items/{item_id}")
async def update_plan_item(plan_id: str, item_id: str, request: PlanItemUpdate,
                           current_user: dict = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    await _get_owned_item(session, plan_id, item_id, current_user["id"])
    # Only touch publish_date when the client actually sent it, so PATCHes that
    # omit it don't clear an existing value. When sent, None clears it.
    update_kwargs = dict(
        topic=request.topic,
        scheduled_date=request.scheduled_date.isoformat() if request.scheduled_date else None,
        notes=request.notes,
        production_status=request.production_status,
        video_format=request.video_format,
        event_duration_minutes=request.event_duration_minutes,
    )
    if "publish_date" in request.model_fields_set:
        update_kwargs["publish_date"] = request.publish_date.isoformat() if request.publish_date else None
    if "event_time" in request.model_fields_set:
        update_kwargs["event_time"] = request.event_time or None
    # Sent explicitly as null, clear the date (a backlog card has none).
    if "scheduled_date" in request.model_fields_set and request.scheduled_date is None:
        update_kwargs["scheduled_date_unset"] = None
    if request.meta is not None:
        update_kwargs["meta_patch"] = request.meta
    await queries.update_plan_item(session, item_id, current_user["id"], **update_kwargs)
    item = await queries.get_plan_item_by_id(session, item_id, current_user["id"])

    # Keep the linked Google Calendar event in sync with any edit.
    if item.get("gcal_event_id"):
        await _sync_calendar_event(session, plan_id, item, current_user["id"])
        item = await queries.get_plan_item_by_id(session, item_id, current_user["id"])

    item["contents"] = await plan_service.get_item_contents_reconciled(
        session, item_id, current_user["id"]
    )
    return item


# Lives in plan_service so the assistant's action executor runs the same code
# (app/services/assistant/actions.py). Imported under the original private name
# so the call sites below are unchanged.
_sync_calendar_event = plan_service.sync_calendar_event


@router.delete("/{plan_id}/items/{item_id}")
async def delete_plan_item(plan_id: str, item_id: str,
                           current_user: dict = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    await _get_owned_item(session, plan_id, item_id, current_user["id"])
    await queries.delete_plan_item(session, item_id, current_user["id"])
    return {"message": "Item deleted"}


# ── Content generation + review ──────────────────────────────────────────────


@router.post("/{plan_id}/items/{item_id}/generate")
async def generate_item_content(plan_id: str, item_id: str, request: GenerateContentRequest,
                                background_tasks: BackgroundTasks,
                                current_user: dict = Depends(get_current_user),
                                session: AsyncSession = Depends(get_session)):
    item = await _get_owned_item(session, plan_id, item_id, current_user["id"])
    # The pipelines produce linkedin / blog / youtube_script only. Without this
    # guard, generating for an Instagram card silently burns a run-quota unit
    # writing a YouTube script for a carousel.
    platform = item.get("platform") or "youtube"
    if platform not in GENERATION_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Content generation is not available for {platform} items.",
        )
    plan = await queries.get_content_plan_by_id(session, plan_id, current_user["id"])
    dispatched = await plan_service.dispatch_generation(
        session, item, request.content_type, request.provider,
        plan.get("niche") or "ai", background_tasks,
    )
    return {"dispatched": dispatched}


@router.get("/{plan_id}/items/{item_id}/content")
async def get_item_content(plan_id: str, item_id: str,
                           current_user: dict = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    await _get_owned_item(session, plan_id, item_id, current_user["id"])
    contents = await plan_service.get_item_contents_reconciled(
        session, item_id, current_user["id"]
    )
    return [await plan_service.hydrate_content(session, c) for c in contents]


# ── Image generation (Instagram) ─────────────────────────────────────────────
#
# Deliberately not part of /generate: an image is a Gemini render, not a
# ContentType. It has no agent run, spends no generation quota, and has nothing
# to review — so it gets its own endpoint rather than a special case inside the
# pipeline dispatch.


def _image_path(filename: str):
    """Resolve a stored image name inside IMAGE_DIR, refusing anything outside.

    The name comes back to us from the DB, but it reaches the DB from a request
    handler, so it is treated as untrusted: without this a crafted meta.image_file
    would turn the GET below into an arbitrary-file read.
    """
    candidate = (IMAGE_DIR / filename).resolve()
    if candidate.parent != IMAGE_DIR.resolve() or not candidate.is_file():
        return None
    return candidate


@router.post("/{plan_id}/items/{item_id}/image")
async def generate_item_image(plan_id: str, item_id: str, request: GenerateImageRequest,
                              current_user: dict = Depends(get_current_user),
                              session: AsyncSession = Depends(get_session)):
    item = await _get_owned_item(session, plan_id, item_id, current_user["id"])
    platform = item.get("platform") or "youtube"
    if platform not in IMAGE_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Image generation is not available for {platform} items.",
        )

    if not await _image_client.health_check():
        raise HTTPException(
            status_code=503,
            detail="Gemini image generation is unavailable. Check GEMINI_API_KEY and GEMINI_IMAGE_MODEL.",
        )

    meta = item.get("meta") or {}
    # Explicit override, then the item's stored prompt, then its topic.
    prompt = (request.prompt or meta.get("image_prompt") or item["topic"]).strip()

    try:
        result = await _image_client.generate_instagram_post(
            topic=prompt,
            palette=request.palette,
            layout=request.layout,
            model=request.model,
        )
    except Exception as exc:
        logger.error("Image generation failed for item %s: %s", item_id, exc)
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}")

    filenames = result.get("filenames") or []
    images = result.get("images") or []
    if not filenames or not images:
        raise HTTPException(status_code=502, detail="Gemini returned no image.")

    await queries.update_plan_item(
        session,
        item_id,
        current_user["id"],
        meta_patch={
            "image_file": filenames[0],
            "image_model": result.get("model"),
            "image_prompt_used": result.get("positive_prompt"),
        },
    )
    return {
        "image_file": filenames[0],
        "image_b64": images[0],
        "model": result.get("model"),
        "duration_s": result.get("duration_s"),
    }


@router.get("/{plan_id}/items/{item_id}/image")
async def get_item_image(plan_id: str, item_id: str,
                         current_user: dict = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    """Serve the item's rendered image.

    Owner-scoped rather than served as a static file: under docker-compose the
    dashboard cannot see the API's output directory at all, and even in dev a
    static mount would make every user's generated graphics public.
    """
    item = await _get_owned_item(session, plan_id, item_id, current_user["id"])
    filename = (item.get("meta") or {}).get("image_file")
    path = _image_path(filename) if isinstance(filename, str) else None
    if path is None:
        raise HTTPException(status_code=404, detail="No image for this item")
    return FileResponse(path, media_type="image/png")


@router.post("/content/{content_id}/review")
async def review_content(content_id: str, request: ReviewActionRequest,
                         background_tasks: BackgroundTasks,
                         current_user: dict = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    content = await queries.get_plan_item_content_by_id(session, content_id, current_user["id"])
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    content = await plan_service.reconcile_plan_item_content(session, content)
    # Shared with the assistant's approve_draft / reject_draft actions; the
    # response shape and the 409 detail are unchanged by the move.
    return await plan_service.apply_review(
        session, content, request.action,
        regenerate=request.regenerate,
        provider=request.provider,
        background_tasks=background_tasks,
    )


# ── Google Calendar ──────────────────────────────────────────────────────────


@router.post("/{plan_id}/items/{item_id}/calendar")
async def add_item_to_calendar(plan_id: str, item_id: str, request: CalendarAddRequest,
                               current_user: dict = Depends(get_current_user),
                               session: AsyncSession = Depends(get_session)):
    from app.services import google_calendar

    item = await _get_owned_item(session, plan_id, item_id, current_user["id"])
    if item.get("gcal_event_id"):
        raise HTTPException(status_code=409, detail="Item is already on the calendar")
    # scheduled_date is nullable now (backlog cards), and the event body falls
    # back to it when there is no publish_date — so an undated item would build
    # an event with no date at all.
    if not (item.get("publish_date") or item.get("scheduled_date")):
        raise HTTPException(
            status_code=400, detail="Item has no date to put on the calendar."
        )

    plan = await queries.get_content_plan_by_id(session, plan_id, current_user["id"])
    # Precedence: request value → item's stored value → service default.
    event_time = request.event_time or item.get("event_time")
    duration = request.event_duration_minutes or item.get("event_duration_minutes")
    try:
        event = await asyncio.to_thread(
            google_calendar.create_event_for_item,
            current_user["id"], item, plan["name"] if plan else "Content plan",
            reminders_minutes=request.reminders_minutes,
            event_time=event_time,
            duration_minutes=duration,
        )
    except google_calendar.NotConnectedError:
        raise HTTPException(status_code=403, detail="Google Calendar is not connected. Connect it from the planner page.")
    except google_calendar.CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await queries.set_plan_item_calendar_event(
        session, item_id, current_user["id"], event["event_id"], event["event_link"],
        event_time=event_time, event_duration_minutes=duration,
    )
    return event
