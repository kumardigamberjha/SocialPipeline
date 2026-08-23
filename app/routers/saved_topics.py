"""
Saved ("uncovered") topic endpoints.

Auto-research parks its unused candidate topics here; the dashboard lists them,
generates content for one on demand, and they move to 'generated' once a
pipeline produces a content row.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.models.saved_topics import (
    GenerateSavedTopicRequest,
    SavedTopicCreate,
)
from app.services import plan_service, saved_topic_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/saved-topics", tags=["saved-topics"])


async def _get_owned_topic(session: AsyncSession, topic_id: str, user_id: str) -> dict:
    topic = await queries.get_saved_topic_by_id(session, topic_id, user_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Saved topic not found")
    return topic


# NOTE: /summary is declared before /{topic_id} so FastAPI does not match
# "summary" as a topic id.
@router.get("/summary", summary="Backlog size for the uncovered-topics banner")
async def get_summary(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["id"]
    return {
        "uncovered_count": await queries.count_uncovered_topics(session, user_id),
        "latest_created_at": await queries.get_latest_saved_topic_at(session, user_id),
    }


@router.get("", summary="List saved topics")
async def list_saved_topics(
    status: str = None,
    include_dismissed: bool = False,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await saved_topic_service.list_topics_reconciled(
        session, current_user["id"], status=status, include_dismissed=include_dismissed,
    )


@router.post("", status_code=201, summary="Save a topic by hand")
async def create_saved_topic(
    request: SavedTopicCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    topic = await queries.create_saved_topic(
        session,
        user_id=current_user["id"],
        topic=request.topic,
        rationale=request.rationale,
        niche=request.niche,
        source="manual",
    )
    if topic is None:
        raise HTTPException(status_code=409, detail="That topic is already saved")
    topic["runs"] = []
    return topic


@router.post("/{topic_id}/generate", summary="Generate content for a saved topic")
async def generate_saved_topic(
    topic_id: str,
    request: GenerateSavedTopicRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["id"]
    topic = await _get_owned_topic(session, topic_id, user_id)
    dispatched = await saved_topic_service.dispatch_saved_topic_generation(
        session, topic, request.content_type, request.provider, background_tasks,
    )
    refreshed = await queries.get_saved_topic_by_id(session, topic_id, user_id)
    return {
        "dispatched": dispatched,
        "topic": await saved_topic_service.reconcile_saved_topic(
            session, refreshed, user_id
        ),
    }


@router.get("/{topic_id}/content", summary="Hydrated content generated for a saved topic")
async def get_saved_topic_content(
    topic_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["id"]
    await _get_owned_topic(session, topic_id, user_id)
    run_rows = await queries.get_saved_topic_runs(session, topic_id, user_id)
    rows = [
        await saved_topic_service.reconcile_saved_topic_run(session, r)
        for r in run_rows
    ]
    # hydrate_content only reads content_type / content_ref_id / user_id, all of
    # which saved_topic_runs rows carry — reused from plan_service unchanged.
    return [await plan_service.hydrate_content(session, r) for r in rows]


@router.post("/{topic_id}/dismiss", summary="Hide a saved topic without generating")
async def dismiss_saved_topic(
    topic_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["id"]
    await _get_owned_topic(session, topic_id, user_id)
    await queries.update_saved_topic(
        session, topic_id, user_id, dismissed_at=datetime.now(timezone.utc),
    )
    return await queries.get_saved_topic_by_id(session, topic_id, user_id)


@router.delete("/{topic_id}", summary="Delete a saved topic")
async def delete_saved_topic(
    topic_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.delete_saved_topic(session, topic_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Saved topic not found")
    return {"message": "Saved topic deleted"}
