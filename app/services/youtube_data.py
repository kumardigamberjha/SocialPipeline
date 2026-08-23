"""
YouTube Data API v3 access for the connected Google account.

Uses the same per-user OAuth credentials as the calendar integration (see
google_calendar.load_credentials), but requires the youtube.readonly scope —
so users connected before that scope was added must reconnect. Playlist/upload
videos are matched back to the imported analytics rows (youtube_published_videos)
by video_id so each video carries its real views / watch-time / CTR when known.
"""

import logging

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from sqlalchemy import select

from app.db.sync_session import sync_session_scope
from app.db.tables import YoutubePublishedVideo
from app.services.google_calendar import (
    YOUTUBE_SCOPE,
    NotConnectedError,
    connection_status,
    load_credentials,
)

logger = logging.getLogger(__name__)


class YoutubeDataError(Exception):
    """Generic YouTube Data API failure surfaced to the router as 502."""


class YoutubeScopeError(YoutubeDataError):
    """Connected, but the youtube.readonly scope was never granted — reconnect."""


class YoutubeApiDisabledError(YoutubeDataError):
    """The GCP project has not enabled the YouTube Data API v3."""


def _service(user_id: str):
    """Build a YouTube Data API client, enforcing the youtube.readonly grant."""
    status = connection_status(user_id)
    if not status.get("connected"):
        raise NotConnectedError("Google account is not connected.")
    if YOUTUBE_SCOPE not in status.get("scopes", []):
        raise YoutubeScopeError(
            "YouTube access has not been granted. Reconnect your Google account to enable it."
        )
    creds = load_credentials(user_id)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _wrap_http_error(exc: HttpError) -> YoutubeDataError:
    detail = str(exc)
    if "accessNotConfigured" in detail or "has not been used" in detail or "it is disabled" in detail:
        return YoutubeApiDisabledError(
            "YouTube Data API v3 is not enabled for this project. Enable it in Google Cloud Console."
        )
    if exc.resp is not None and exc.resp.status == 403 and "insufficient" in detail.lower():
        return YoutubeScopeError("Insufficient YouTube permissions. Reconnect your Google account.")
    return YoutubeDataError(f"YouTube Data API error: {detail}")


def _enrich_with_metrics(user_id: str, videos: list[dict]) -> list[dict]:
    """Attach imported views/watch-time/CTR to videos, matched by video_id.

    Scoped to ``user_id``: ``youtube_published_videos`` is keyed on
    ``(user_id, video_id)``, so an unscoped lookup would surface another
    tenant's imported analytics for any video id they happen to share.
    """
    ids = [v["video_id"] for v in videos if v.get("video_id")]
    if not ids:
        return videos
    with sync_session_scope() as session:
        rows = {
            r.video_id: r
            for r in session.execute(
                select(
                    YoutubePublishedVideo.video_id,
                    YoutubePublishedVideo.views,
                    YoutubePublishedVideo.watch_time_hours,
                    YoutubePublishedVideo.impressions_ctr,
                ).where(
                    YoutubePublishedVideo.user_id == user_id,
                    YoutubePublishedVideo.video_id.in_(ids),
                )
            )
        }
    for v in videos:
        m = rows.get(v["video_id"])
        v["views"] = m.views if m else None
        v["watch_time_hours"] = m.watch_time_hours if m else None
        v["impressions_ctr"] = m.impressions_ctr if m else None
    return videos


def get_channel_overview(user_id: str) -> dict:
    """Return {channel_title, uploads_playlist_id} for the connected channel."""
    yt = _service(user_id)
    try:
        resp = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
    except HttpError as exc:
        raise _wrap_http_error(exc)
    items = resp.get("items", [])
    if not items:
        raise YoutubeDataError("No YouTube channel found for the connected Google account.")
    ch = items[0]
    return {
        "channel_title": ch["snippet"]["title"],
        "uploads_playlist_id": ch["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def list_playlists(user_id: str, max_results: int = 50) -> list[dict]:
    """List the connected channel's playlists (newest-created first as returned)."""
    yt = _service(user_id)
    playlists: list[dict] = []
    try:
        req = yt.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50)
        while req is not None and len(playlists) < max_results:
            resp = req.execute()
            for it in resp.get("items", []):
                sn = it.get("snippet", {})
                thumbs = sn.get("thumbnails", {})
                playlists.append(
                    {
                        "id": it["id"],
                        "title": sn.get("title", ""),
                        "description": sn.get("description", ""),
                        "item_count": it.get("contentDetails", {}).get("itemCount", 0),
                        "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url"),
                    }
                )
            req = yt.playlists().list_next(req, resp)
    except HttpError as exc:
        raise _wrap_http_error(exc)
    return playlists[:max_results]


def list_playlist_videos(user_id: str, playlist_id: str, max_results: int = 10) -> list[dict]:
    """Latest videos in a playlist (or uploads playlist), enriched with metrics."""
    yt = _service(user_id)
    try:
        resp = (
            yt.playlistItems()
            .list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=min(max_results, 50))
            .execute()
        )
    except HttpError as exc:
        raise _wrap_http_error(exc)

    videos: list[dict] = []
    for it in resp.get("items", []):
        cd = it.get("contentDetails", {})
        sn = it.get("snippet", {})
        video_id = cd.get("videoId")
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": sn.get("title", ""),
                "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt"),
            }
        )
    # Newest first regardless of playlist ordering.
    videos.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    return _enrich_with_metrics(user_id, videos[:max_results])
