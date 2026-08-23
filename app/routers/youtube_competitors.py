"""
YouTube competitor tracking: LLM-proposed, YouTube-API-verified discovery,
user approval, and cached channel/video data that feeds the analysis and
planner prompts (see app.services.youtube_competitor_context, wired into
app.routers.youtube_analytics).

Discovery excludes every channel already in the user's list, in ANY status
(approved, rejected, or archived) — see
app.db.queries.filter_known_competitor_ids. A rejected suggestion is never
proposed again.
"""

import asyncio
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.models.competitors import AddCompetitorRequest, ApproveDiscoveryRequest, UpdateCompetitorRequest
from app.services import youtube_competitor as yc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube-competitors", tags=["YouTube Competitors"])


def _map_error(exc: Exception) -> HTTPException:
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_data import YoutubeApiDisabledError, YoutubeDataError, YoutubeScopeError

    if isinstance(exc, YoutubeScopeError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotConnectedError):
        return HTTPException(status_code=400, detail=str(exc) or "Google account not connected.")
    if isinstance(exc, YoutubeApiDisabledError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, YoutubeDataError):
        return HTTPException(status_code=502, detail=str(exc))
    logger.exception("Unexpected competitor error")
    return HTTPException(status_code=502, detail=f"Competitor discovery error: {exc}")


def _encode_cursor(created_at: str, channel_id: str) -> str:
    raw = f"{created_at}|{channel_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at, channel_id = raw.split("|", 1)
    return created_at, channel_id


# ── Discovery ────────────────────────────────────────────────────────────────


@router.post("/discover")
async def discover_competitors(
    niche: str = "",
    count: int = 20,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Propose up to `count` NEW competitor channels, verified against the real
    YouTube API. Channels already tracked (any status) are excluded."""
    count = max(1, min(count, 30))
    try:
        run = await yc.run_discovery(session, current_user["id"], niche=niche, count=count)
    except Exception as exc:
        raise _map_error(exc)
    return run


@router.get("/discover/{run_id}")
async def get_discovery_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    run = await queries.get_competitor_discovery_run(session, run_id, current_user["id"])
    if not run:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return run


@router.post("/discover/{run_id}/approve")
async def approve_discovery_run(
    run_id: str,
    request: ApproveDiscoveryRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await yc.approve_candidates(
            session, current_user["id"], run_id, request.approved, request.rejected
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Fixed-path routes (must precede /{channel_id}) ────────────────────────────


@router.get("/videos")
async def list_competitor_videos(
    page: int = 1,
    per_page: int = 30,
    channel_id: str | None = None,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """All competitor videos sorted by views descending. Supports optional channel_id filter."""
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    offset = (page - 1) * per_page
    rows, total = await queries.get_all_competitor_videos(
        session, current_user["id"], limit=per_page, offset=offset, channel_id=channel_id
    )
    return {
        "items": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),  # ceiling division
    }


@router.get("/summary")

async def competitor_summary(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    uid = current_user["id"]
    approved = await queries.count_competitors(session, uid, status="approved")
    rejected = await queries.count_competitors(session, uid, status="rejected")
    return {"approved": approved, "rejected": rejected}


# ── List / detail / mutate ────────────────────────────────────────────────────


@router.get("")
async def list_competitors(
    cursor: str | None = None,
    limit: int = 50,
    status: str = "approved",
    q: str = "",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    limit = max(1, min(limit, 100))
    decoded = _decode_cursor(cursor) if cursor else None
    items = await queries.list_competitors(
        session, current_user["id"], limit=limit + 1, cursor=decoded, status=status, q=q
    )
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        last = items[-1]
        next_cursor = _encode_cursor(last["created_at"], last["channel_id"])
    return {"items": items, "next_cursor": next_cursor}


@router.post("")
async def add_competitor(
    request: AddCompetitorRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Manually track a channel by id or handle (no LLM involved)."""
    if not request.channel_id and not request.handle:
        raise HTTPException(status_code=400, detail="channel_id or handle is required")
    candidate = {"name": request.handle or request.channel_id, "handle": request.handle or "",
                 "channel_id": request.channel_id or ""}
    ledger = yc.QuotaLedger()
    try:
        verified = await asyncio.to_thread(
            yc.verify_candidates, current_user["id"], [candidate], ledger
        )
    except Exception as exc:
        raise _map_error(exc)
    if not verified:
        raise HTTPException(status_code=404, detail="Channel not found on YouTube")
    row = {**verified[0], "status": "approved", "discovered_by": "manual"}
    await queries.bulk_upsert_competitors(session, current_user["id"], [row])
    return await queries.get_competitor(session, current_user["id"], row["channel_id"])


@router.get("/{channel_id}")
async def get_competitor_detail(
    channel_id: str,
    video_limit: int = 20,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    competitor = await queries.get_competitor(session, current_user["id"], channel_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    videos = await queries.get_competitor_videos(
        session, current_user["id"], channel_id, limit=min(video_limit, 50)
    )
    return {**competitor, "videos": videos}


@router.patch("/{channel_id}")
async def update_competitor(
    channel_id: str,
    request: UpdateCompetitorRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await queries.get_competitor(session, current_user["id"], channel_id):
        raise HTTPException(status_code=404, detail="Competitor not found")
    await queries.update_competitor(
        session, current_user["id"], channel_id, status=request.status, priority=request.priority
    )
    return await queries.get_competitor(session, current_user["id"], channel_id)


@router.delete("/{channel_id}")
async def remove_competitor(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Archives rather than deletes — the row must survive so future discovery
    runs keep excluding this channel."""
    if not await queries.update_competitor(session, current_user["id"], channel_id, status="archived"):
        raise HTTPException(status_code=404, detail="Competitor not found")
    return {"message": "Competitor archived"}


@router.post("/{channel_id}/sync")
async def sync_one_competitor(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    competitor = await queries.get_competitor(session, current_user["id"], channel_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    ledger = yc.QuotaLedger()
    try:
        videos = await asyncio.to_thread(
            yc.sync_competitor_videos, current_user["id"], channel_id,
            competitor.get("uploads_playlist_id") or "", ledger,
        )
    except Exception as exc:
        raise _map_error(exc)
    if videos:
        await queries.bulk_upsert_competitor_videos(session, current_user["id"], videos)
    await queries.stamp_competitor_synced(session, current_user["id"], channel_id)
    return {"synced": len(videos), "quota_units": ledger.spent}
