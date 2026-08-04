"""
Local YouTube playlist production tracker.

A "pending → published" board keyed to a real YouTube playlist id. The Google
connection is read-only and a bare topic idea has no uploaded video, so nothing is
written to the real playlist — these are locally-tracked video ideas (added from the
per-playlist trending topics, or manually) that the user advances through the same
production stages as content-planner items.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth_deps import get_current_user
from app.db import queries
from app.models.planner import ProductionStatus, VideoFormat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube-playlists", tags=["youtube-playlists"])


# ── Requests ─────────────────────────────────────────────────────────────────


class PlaylistItemIn(BaseModel):
    playlist_id: str
    playlist_title: Optional[str] = None
    title: str
    description: Optional[str] = None
    video_format: VideoFormat = "full"
    scheduled_date: Optional[str] = None
    publish_date: Optional[str] = None
    source: str = "manual"


class PlaylistItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    video_format: Optional[VideoFormat] = None
    scheduled_date: Optional[str] = None
    publish_date: Optional[str] = None
    production_status: Optional[ProductionStatus] = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/items")
def create_item(request: PlaylistItemIn, current_user: dict = Depends(get_current_user)):
    return queries.create_youtube_playlist_item(
        current_user["id"], request.playlist_id, request.title,
        playlist_title=request.playlist_title, description=request.description,
        video_format=request.video_format, scheduled_date=request.scheduled_date,
        publish_date=request.publish_date, source=request.source,
    )


@router.get("/items")
def list_items(playlist_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return queries.get_youtube_playlist_items(current_user["id"], playlist_id)


@router.patch("/items/{item_id}")
def update_item(item_id: str, request: PlaylistItemUpdate,
                current_user: dict = Depends(get_current_user)):
    if not queries.get_youtube_playlist_item_by_id(item_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Playlist item not found")
    # Only touch optional-clearable fields the client actually sent, so a PATCH
    # that omits them doesn't wipe existing values; when sent, None clears them.
    fields = request.model_fields_set
    update_kwargs = dict(
        title=request.title,
        video_format=request.video_format,
        production_status=request.production_status,
    )
    if "description" in fields:
        update_kwargs["description"] = request.description
    if "scheduled_date" in fields:
        update_kwargs["scheduled_date"] = request.scheduled_date
    if "publish_date" in fields:
        update_kwargs["publish_date"] = request.publish_date
    queries.update_youtube_playlist_item(item_id, current_user["id"], **update_kwargs)
    return queries.get_youtube_playlist_item_by_id(item_id, current_user["id"])


@router.delete("/items/{item_id}")
def delete_item(item_id: str, current_user: dict = Depends(get_current_user)):
    if not queries.delete_youtube_playlist_item(item_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Playlist item not found")
    return {"message": "Item deleted"}
