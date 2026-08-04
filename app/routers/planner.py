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

import calendar as _calendar
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.auth_deps import get_current_user
from app.db import queries
from app.models.planner import (
    CalendarAddRequest,
    GenerateContentRequest,
    PlanCreateRequest,
    PlanItemIn,
    PlanItemUpdate,
    PlanUpdateRequest,
    ReviewActionRequest,
    SuggestTopicsRequest,
)
from app.services import plan_service
from app.services.topic_suggester import suggest_topics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plans", tags=["planner"])


# ── Topic suggestion ─────────────────────────────────────────────────────────


@router.post("/suggest-topics")
async def suggest_plan_topics(request: SuggestTopicsRequest, current_user: dict = Depends(get_current_user)):
    try:
        topics = await suggest_topics(
            user_id=current_user["id"],
            plan_type=request.plan_type,
            niche=request.niche,
            start_date=request.start_date,
            count=request.count,
            provider=request.provider,
        )
    except Exception as exc:
        logger.exception("Topic suggestion failed")
        raise HTTPException(status_code=502, detail=f"Topic suggestion failed: {exc}")
    return {"topics": topics}


# ── Plans ────────────────────────────────────────────────────────────────────


@router.post("")
def create_plan(request: PlanCreateRequest, current_user: dict = Depends(get_current_user)):
    start = request.start_date
    if request.plan_type == "weekly":
        end = start + timedelta(days=6)
    else:
        end = start + timedelta(days=_calendar.monthrange(start.year, start.month)[1] - 1)

    plan = queries.create_content_plan(
        current_user["id"], request.name, request.plan_type, request.niche,
        start.isoformat(), end.isoformat(),
    )
    for item in request.items:
        queries.create_plan_item(
            plan["id"], current_user["id"], item.topic, item.scheduled_date.isoformat(),
            item.notes, item.topic_source,
            publish_date=item.publish_date.isoformat() if item.publish_date else None,
            video_format=item.video_format,
            event_time=item.event_time,
            event_duration_minutes=item.event_duration_minutes,
        )
    return plan_service.get_plan_detail(plan["id"], current_user["id"])


@router.get("")
def list_plans(current_user: dict = Depends(get_current_user)):
    return queries.get_content_plans(current_user["id"])


# Declared BEFORE "/{plan_id}" so the static "/stats" path is not captured as a plan id.
@router.get("/stats")
def get_planner_stats(current_user: dict = Depends(get_current_user)):
    """Aggregate planner metrics for the analytics dashboard."""
    return queries.get_planner_analytics(current_user["id"])


@router.get("/{plan_id}")
def get_plan(plan_id: str, current_user: dict = Depends(get_current_user)):
    plan = plan_service.get_plan_detail(plan_id, current_user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/{plan_id}")
def update_plan(plan_id: str, request: PlanUpdateRequest, current_user: dict = Depends(get_current_user)):
    if not queries.update_content_plan(plan_id, current_user["id"], name=request.name, status=request.status):
        raise HTTPException(status_code=404, detail="Plan not found or nothing to update")
    return queries.get_content_plan_by_id(plan_id, current_user["id"])


@router.delete("/{plan_id}")
def delete_plan(plan_id: str, current_user: dict = Depends(get_current_user)):
    if not queries.delete_content_plan(plan_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted"}


# ── Plan items ───────────────────────────────────────────────────────────────


def _get_owned_item(plan_id: str, item_id: str, user_id: str) -> dict:
    item = queries.get_plan_item_by_id(item_id, user_id)
    if not item or item["plan_id"] != plan_id:
        raise HTTPException(status_code=404, detail="Plan item not found")
    return item


@router.post("/{plan_id}/items")
def add_plan_item(plan_id: str, request: PlanItemIn, current_user: dict = Depends(get_current_user)):
    plan = queries.get_content_plan_by_id(plan_id, current_user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return queries.create_plan_item(
        plan_id, current_user["id"], request.topic, request.scheduled_date.isoformat(),
        request.notes, request.topic_source,
        publish_date=request.publish_date.isoformat() if request.publish_date else None,
        video_format=request.video_format,
        event_time=request.event_time,
        event_duration_minutes=request.event_duration_minutes,
    )


@router.patch("/{plan_id}/items/{item_id}")
def update_plan_item(plan_id: str, item_id: str, request: PlanItemUpdate,
                     current_user: dict = Depends(get_current_user)):
    _get_owned_item(plan_id, item_id, current_user["id"])
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
    queries.update_plan_item(item_id, current_user["id"], **update_kwargs)
    item = queries.get_plan_item_by_id(item_id, current_user["id"])

    # Keep the linked Google Calendar event in sync with any edit.
    if item.get("gcal_event_id"):
        _sync_calendar_event(plan_id, item, current_user["id"])
        item = queries.get_plan_item_by_id(item_id, current_user["id"])

    item["contents"] = plan_service.get_item_contents_reconciled(item_id, current_user["id"])
    return item


def _sync_calendar_event(plan_id: str, item: dict, user_id: str) -> None:
    """Best-effort push of item changes to its Google Calendar event. Never fails
    the edit: on a missing event the local link is cleared; other errors are logged."""
    from app.services import google_calendar

    plan = queries.get_content_plan_by_id(plan_id, user_id)
    try:
        google_calendar.update_event_for_item(
            user_id, item, plan["name"] if plan else "Content plan",
        )
    except google_calendar.EventGoneError:
        logger.info("Calendar event for item %s was deleted in Google; clearing link.", item["id"])
        queries.clear_plan_item_calendar_event(item["id"])
    except google_calendar.CalendarError as exc:
        # Includes NotConnectedError — the edit still saved locally.
        logger.warning("Calendar sync failed for item %s: %s", item["id"], exc)


@router.delete("/{plan_id}/items/{item_id}")
def delete_plan_item(plan_id: str, item_id: str, current_user: dict = Depends(get_current_user)):
    _get_owned_item(plan_id, item_id, current_user["id"])
    queries.delete_plan_item(item_id, current_user["id"])
    return {"message": "Item deleted"}


# ── Content generation + review ──────────────────────────────────────────────


@router.post("/{plan_id}/items/{item_id}/generate")
def generate_item_content(plan_id: str, item_id: str, request: GenerateContentRequest,
                          background_tasks: BackgroundTasks,
                          current_user: dict = Depends(get_current_user)):
    item = _get_owned_item(plan_id, item_id, current_user["id"])
    plan = queries.get_content_plan_by_id(plan_id, current_user["id"])
    dispatched = plan_service.dispatch_generation(
        item, request.content_type, request.provider, plan.get("niche") or "ai", background_tasks,
    )
    return {"dispatched": dispatched}


@router.get("/{plan_id}/items/{item_id}/content")
def get_item_content(plan_id: str, item_id: str, current_user: dict = Depends(get_current_user)):
    _get_owned_item(plan_id, item_id, current_user["id"])
    contents = plan_service.get_item_contents_reconciled(item_id, current_user["id"])
    return [plan_service.hydrate_content(c) for c in contents]


@router.post("/content/{content_id}/review")
def review_content(content_id: str, request: ReviewActionRequest,
                   background_tasks: BackgroundTasks,
                   current_user: dict = Depends(get_current_user)):
    content = queries.get_plan_item_content_by_id(content_id, current_user["id"])
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    content = plan_service.reconcile_plan_item_content(content)
    if content["review_status"] not in ("ready", "approved", "rejected"):
        raise HTTPException(status_code=409, detail=f"Content is not reviewable (status: {content['review_status']})")

    new_status = "approved" if request.action == "approve" else "rejected"
    queries.update_plan_item_content(content_id, review_status=new_status)
    plan_service.set_source_approved(content, request.action == "approve")
    content["review_status"] = new_status

    result = {"content": content}
    if request.action == "reject" and request.regenerate:
        item = queries.get_plan_item_by_id(content["item_id"], current_user["id"])
        plan = queries.get_content_plan_by_id(item["plan_id"], current_user["id"]) if item else None
        if item:
            run = queries.get_run_by_id(content["run_id"]) if content.get("run_id") else None
            provider = request.provider or (run and run.get("provider_used")) or "nvidia"
            result["dispatched"] = plan_service.dispatch_generation(
                item, content["content_type"], provider,
                (plan or {}).get("niche") or "ai", background_tasks,
            )
    return result


# ── Google Calendar ──────────────────────────────────────────────────────────


@router.post("/{plan_id}/items/{item_id}/calendar")
def add_item_to_calendar(plan_id: str, item_id: str, request: CalendarAddRequest,
                         current_user: dict = Depends(get_current_user)):
    from app.services import google_calendar

    item = _get_owned_item(plan_id, item_id, current_user["id"])
    if item.get("gcal_event_id"):
        raise HTTPException(status_code=409, detail="Item is already on the calendar")

    plan = queries.get_content_plan_by_id(plan_id, current_user["id"])
    # Precedence: request value → item's stored value → service default.
    event_time = request.event_time or item.get("event_time")
    duration = request.event_duration_minutes or item.get("event_duration_minutes")
    try:
        event = google_calendar.create_event_for_item(
            current_user["id"], item, plan["name"] if plan else "Content plan",
            reminders_minutes=request.reminders_minutes,
            event_time=event_time,
            duration_minutes=duration,
        )
    except google_calendar.NotConnectedError:
        raise HTTPException(status_code=403, detail="Google Calendar is not connected. Connect it from the planner page.")
    except google_calendar.CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    queries.set_plan_item_calendar_event(
        item_id, event["event_id"], event["event_link"],
        event_time=event_time, event_duration_minutes=duration,
    )
    return event
