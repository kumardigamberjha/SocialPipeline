"""
YouTube Live Sync Service — fetches full video metadata directly from
YouTube Data API v3 and stores it in the youtube_videos_live table.

Provides a VidIQ-comparable dataset: title, description, tags, category,
duration, thumbnail, views, likes, comments, and computed SEO scores.

Usage:
    from app.services.youtube_sync_service import sync_latest_videos
    result = sync_latest_videos(user_id, max_results=50)
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.sync_session import sync_session_scope
from app.db.tables import GoogleOAuthToken, YoutubePublishedVideo, YoutubeVideoLive
from app.services.google_calendar import (
    YOUTUBE_SCOPE,
    YT_ANALYTICS_SCOPE,
    NotConnectedError,
    connection_status,
    load_credentials,
)

logger = logging.getLogger(__name__)


# ── Custom exceptions (mirror youtube_data.py pattern) ───────────────────────


class YoutubeSyncError(Exception):
    """Generic failure surfaced to the router as 502."""


class YoutubeScopeMissing(YoutubeSyncError):
    """Connected but youtube.readonly scope was never granted."""


class YoutubeApiDisabled(YoutubeSyncError):
    """GCP project has not enabled the YouTube Data API v3."""


class YoutubeAnalyticsScopeMissing(YoutubeSyncError):
    """Connected but yt-analytics.readonly was never granted (CTR sync needs it)."""


# ── ISO 8601 duration parser ──────────────────────────────────────────────────

_ISO_RE = re.compile(
    r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE
)


def _parse_duration(iso_str: str) -> int:
    """Convert ISO 8601 duration (PT1H3M27S) to total seconds."""
    if not iso_str:
        return 0
    m = _ISO_RE.match(iso_str)
    if not m:
        return 0
    h, mi, s = (int(v) if v else 0 for v in m.groups())
    return h * 3600 + mi * 60 + s


# ── SEO scoring ───────────────────────────────────────────────────────────────

def _compute_seo_title_score(title: str) -> int:
    """
    Score the title 0-100 based on VidIQ-style heuristics:
      - 40-70 chars  → full 40 pts
      - Has a number  → +10 pts
      - Has brackets/parens → +10 pts
      - No ALL-CAPS words (spammy) → +10 pts
      - Starts with a keyword (not stopword) → +10 pts
      - Remaining 20 pts: penalise very short (<20) or very long (>80)
    """
    if not title:
        return 0
    score = 0
    length = len(title)

    # Length sweet spot
    if 40 <= length <= 70:
        score += 40
    elif 20 <= length < 40 or 70 < length <= 80:
        score += 20
    elif length > 0:
        score += 10

    if re.search(r"\d", title):
        score += 10
    if re.search(r"[\[\](){}]", title):
        score += 10
    if not re.search(r"\b[A-Z]{4,}\b", title):
        score += 10

    # First word not a stopword
    stopwords = {"the", "a", "an", "how", "why", "what", "is", "are", "in", "of"}
    first = title.split()[0].lower().strip("[]()") if title.split() else ""
    if first and first not in stopwords:
        score += 10

    # Bonus 20 for the above being solid (cap at 100)
    score += 20
    return min(score, 100)


def _compute_seo_desc_words(description: str) -> int:
    """Word count of the description."""
    if not description:
        return 0
    return len(description.split())


# ── YouTube API client helper ─────────────────────────────────────────────────


def _get_service(user_id: str):
    """Build a YouTube Data API v3 client for the connected user."""
    from googleapiclient.discovery import build

    status = connection_status(user_id)
    if not status.get("connected"):
        raise NotConnectedError("Google account is not connected.")
    if YOUTUBE_SCOPE not in status.get("scopes", []):
        raise YoutubeScopeMissing(
            "YouTube access has not been granted. Reconnect your Google account."
        )
    creds = load_credentials(user_id)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _get_analytics_service(user_id: str):
    """Build a YouTube Analytics API v2 client for the connected user.

    Separate scope from the Data API client above — impressions/CTR require
    yt-analytics.readonly, which existing youtube.readonly-only connections
    were never granted.
    """
    from googleapiclient.discovery import build

    status = connection_status(user_id)
    if not status.get("connected"):
        raise NotConnectedError("Google account is not connected.")
    if YT_ANALYTICS_SCOPE not in status.get("scopes", []):
        raise YoutubeAnalyticsScopeMissing(
            "YouTube Analytics access has not been granted. Reconnect your Google account."
        )
    creds = load_credentials(user_id)
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _handle_http_error(exc: HttpError) -> YoutubeSyncError:
    detail = str(exc)
    if "accessNotConfigured" in detail or "has not been used" in detail or "it is disabled" in detail:
        return YoutubeApiDisabled(
            "YouTube Data API v3 is not enabled. Enable it in Google Cloud Console."
        )
    if exc.resp is not None and exc.resp.status == 403 and "insufficient" in detail.lower():
        return YoutubeScopeMissing("Insufficient YouTube permissions. Reconnect your Google account.")
    return YoutubeSyncError(f"YouTube Data API error: {detail}")


# ── Core sync logic ───────────────────────────────────────────────────────────


def _get_uploads_playlist_id(yt) -> tuple[str, str, str]:
    """Return (uploads_playlist_id, channel_id, channel_title)."""
    try:
        resp = yt.channels().list(
            part="snippet,contentDetails", mine=True
        ).execute()
    except HttpError as exc:
        raise _handle_http_error(exc)

    items = resp.get("items", [])
    if not items:
        raise YoutubeSyncError("No YouTube channel found for the connected Google account.")

    ch = items[0]
    return (
        ch["contentDetails"]["relatedPlaylists"]["uploads"],
        ch["id"],
        ch["snippet"]["title"],
    )


def _get_video_ids_from_playlist(yt, playlist_id: str, max_results: int = 50) -> list[str]:
    """Fetch the latest N video IDs from the uploads playlist."""
    video_ids = []
    page_token = None

    while len(video_ids) < max_results:
        batch = min(50, max_results - len(video_ids))
        try:
            kwargs = dict(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=batch,
            )
            if page_token:
                kwargs["pageToken"] = page_token
            resp = yt.playlistItems().list(**kwargs).execute()
        except HttpError as exc:
            raise _handle_http_error(exc)

        for item in resp.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids.append(vid)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return video_ids[:max_results]


def _fetch_video_details(yt, video_ids: list[str]) -> list[dict]:
    """Batch-fetch full video details (snippet + contentDetails + statistics + status)."""
    all_items = []
    # YouTube API allows max 50 per batch
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        try:
            resp = yt.videos().list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(chunk),
            ).execute()
        except HttpError as exc:
            raise _handle_http_error(exc)
        all_items.extend(resp.get("items", []))
    return all_items


def _upsert_video(session, user_id: str, video: dict, channel_id: str, channel_title: str) -> bool:
    """Parse a YouTube API video item and upsert it for ``user_id``.

    Writes both ``youtube_videos_live`` and ``youtube_published_videos``. Both
    are keyed on ``(user_id, video_id)``; the previous version keyed on
    ``video_id`` alone, so two users syncing the same public video overwrote
    each other's row.

    Returns True if this is a brand-new video (INSERT), False if an UPDATE.
    """
    vid_id = video.get("id", "")
    snippet = video.get("snippet", {})
    content = video.get("contentDetails", {})
    stats = video.get("statistics", {})
    status_info = video.get("status", {})

    title = snippet.get("title", "")
    description = snippet.get("description", "")
    tags = snippet.get("tags", [])
    category_id = snippet.get("categoryId", "")
    published_at = snippet.get("publishedAt") or None

    # Status / Privacy / Scheduled
    privacy_status = status_info.get("privacyStatus", "public")
    publish_at_scheduled = status_info.get("publishAt")
    is_scheduled = bool(
        publish_at_scheduled
        or (
            privacy_status == "private"
            and status_info.get("uploadStatus") == "uploaded"
            and (published_at or "") > datetime.now(timezone.utc).isoformat()
        )
    )

    # Thumbnail: prefer maxresdefault → high → medium → default
    thumbs = snippet.get("thumbnails", {})
    thumbnail_url = (
        (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {})
        .get("url")
    )

    duration_seconds = _parse_duration(content.get("duration", ""))
    views = int(stats.get("viewCount", 0) or 0)
    likes = int(stats.get("likeCount", 0) or 0)
    comments = int(stats.get("commentCount", 0) or 0)

    is_new = session.execute(
        select(YoutubeVideoLive.video_id).where(
            YoutubeVideoLive.user_id == user_id,
            YoutubeVideoLive.video_id == vid_id,
        )
    ).first() is None

    live = pg_insert(YoutubeVideoLive).values(
        user_id=user_id,
        video_id=vid_id,
        title=title,
        description=description,
        tags=tags,                      # JSONB — no json.dumps needed
        category_id=category_id,
        duration_seconds=duration_seconds,
        published_at=published_at,
        thumbnail_url=thumbnail_url,
        views=views,
        likes=likes,
        comments=comments,
        channel_id=channel_id or "",
        channel_title=channel_title or "",
        seo_title_score=_compute_seo_title_score(title),
        seo_tag_count=len(tags),
        seo_desc_words=_compute_seo_desc_words(description),
        privacy_status=privacy_status,
        is_scheduled=is_scheduled,
        publish_at=publish_at_scheduled,
    )
    session.execute(
        live.on_conflict_do_update(
            index_elements=[YoutubeVideoLive.user_id, YoutubeVideoLive.video_id],
            set_={
                "title": live.excluded.title,
                "description": live.excluded.description,
                "tags": live.excluded.tags,
                "category_id": live.excluded.category_id,
                "duration_seconds": func.coalesce(
                    live.excluded.duration_seconds, YoutubeVideoLive.duration_seconds
                ),
                "published_at": func.coalesce(
                    live.excluded.published_at, YoutubeVideoLive.published_at
                ),
                "thumbnail_url": func.coalesce(
                    live.excluded.thumbnail_url, YoutubeVideoLive.thumbnail_url
                ),
                "views": live.excluded.views,
                "likes": live.excluded.likes,
                "comments": live.excluded.comments,
                "channel_id": live.excluded.channel_id,
                "channel_title": live.excluded.channel_title,
                "seo_title_score": live.excluded.seo_title_score,
                "seo_tag_count": live.excluded.seo_tag_count,
                "seo_desc_words": live.excluded.seo_desc_words,
                "privacy_status": live.excluded.privacy_status,
                "is_scheduled": live.excluded.is_scheduled,
                "publish_at": live.excluded.publish_at,
                "fetched_at": func.now(),
            },
        )
    )

    # Dual-upsert into youtube_published_videos for legacy analytics compatibility.
    published = pg_insert(YoutubePublishedVideo).values(
        user_id=user_id,
        video_id=vid_id,
        title=title,
        publish_time=published_at,
        duration_seconds=duration_seconds,
        views=views,
        watch_time_hours=round((views * duration_seconds) / 3600.0, 2),
    )
    session.execute(
        published.on_conflict_do_update(
            index_elements=[
                YoutubePublishedVideo.user_id,
                YoutubePublishedVideo.video_id,
            ],
            set_={
                "title": published.excluded.title,
                "publish_time": func.coalesce(
                    published.excluded.publish_time,
                    YoutubePublishedVideo.publish_time,
                ),
                "duration_seconds": func.coalesce(
                    published.excluded.duration_seconds,
                    YoutubePublishedVideo.duration_seconds,
                ),
                "views": published.excluded.views,
                # An estimate derived from views must not overwrite a real
                # Studio CSV import that reported a higher figure.
                "watch_time_hours": func.greatest(
                    YoutubePublishedVideo.watch_time_hours,
                    published.excluded.watch_time_hours,
                ),
            },
        )
    )

    return is_new


# ── Public API ────────────────────────────────────────────────────────────────


def sync_all_videos(user_id: str, max_results: int = 10000) -> dict:
    """
    Fetch ALL videos from the channel's uploads playlist and upsert into
    youtube_videos_live (and legacy youtube_published_videos).

    - On first run: imports every video ever published (up to max_results).
    - On subsequent runs: updates views/likes/comments for every existing video
      AND adds any newly published videos.

    Returns:
        {
            "synced": total videos processed,
            "new": brand-new videos inserted,
            "updated": existing videos refreshed,
            "channel_title": str,
            "last_synced": ISO timestamp,
        }

    Raises YoutubeSyncError / YoutubeScopeMissing / YoutubeApiDisabled on failure.
    """
    yt = _get_service(user_id)

    uploads_id, channel_id, channel_title = _get_uploads_playlist_id(yt)
    logger.info(
        "Syncing ALL videos for channel '%s' (user %s), max=%d",
        channel_title, user_id, max_results,
    )

    # Step 1 – get every video ID from the uploads playlist
    video_ids = _get_video_ids_from_playlist(yt, uploads_id, max_results)
    if not video_ids:
        return {"synced": 0, "new": 0, "updated": 0, "channel_title": channel_title,
                "last_synced": datetime.now(timezone.utc).isoformat()}

    # Step 2 – Also refresh metrics for any videos already in the DB that
    #           weren't returned by the playlist (e.g. very old uploads that
    #           fall beyond the playlist page limit).
    with sync_session_scope() as session:
        db_ids = [
            r[0] for r in session.execute(
                select(YoutubeVideoLive.video_id).where(
                    YoutubeVideoLive.user_id == user_id
                )
            )
        ]
    # Merge: playlist_ids first (newest), then any DB-only IDs
    extra_ids = [vid for vid in db_ids if vid not in set(video_ids)]
    all_ids = video_ids + extra_ids

    # Step 3 – batch-fetch details (50 per API call)
    items = _fetch_video_details(yt, all_ids)
    new_count = 0
    with sync_session_scope() as session:
        for item in items:
            if _upsert_video(session, user_id, item, channel_id, channel_title):
                new_count += 1

    total = len(items)
    updated = total - new_count
    last_synced = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Full sync complete for user %s: %d total (%d new, %d updated)",
        user_id, total, new_count, updated,
    )
    return {
        "synced": total,
        "new": new_count,
        "updated": updated,
        "channel_title": channel_title,
        "last_synced": last_synced,
    }


def sync_video_analytics(user_id: str, days: int = 90) -> dict:
    """Pull real impressions/CTR/retention from the YouTube Analytics API and
    write them onto the matching youtube_videos_live rows.

    One report call returns one row per video for the whole channel — cheap,
    no per-video pagination needed. Rows are matched by video_id against
    existing youtube_videos_live rows (populated by sync_all_videos); a video
    with no local match is skipped rather than inserted, since we'd have no
    title/description/etc. to satisfy the rest of that table's columns.

    Raises YoutubeAnalyticsScopeMissing / NotConnectedError / YoutubeSyncError.
    """
    yta = _get_analytics_service(user_id)

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    try:
        response = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,impressions,impressionsClickThroughRate,averageViewDuration,averageViewPercentage",
            dimensions="video",
            maxResults=200,
            sort="-views",
        ).execute()
    except HttpError as exc:
        raise _handle_http_error(exc)

    headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])

    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    with sync_session_scope() as session:
        for row in rows:
            data = dict(zip(headers, row))
            video_id = data.get("video")
            if not video_id:
                continue
            result = session.execute(
                update(YoutubeVideoLive)
                .where(
                    YoutubeVideoLive.user_id == user_id,
                    YoutubeVideoLive.video_id == video_id,
                )
                .values(
                    impressions=int(data.get("impressions", 0) or 0),
                    impressions_ctr=float(data.get("impressionsClickThroughRate", 0) or 0),
                    average_view_duration_seconds=int(data.get("averageViewDuration", 0) or 0),
                    average_view_percentage=float(data.get("averageViewPercentage", 0) or 0),
                    analytics_synced_at=now,
                )
            )
            if result.rowcount:
                updated += 1
            else:
                skipped += 1

    logger.info(
        "Analytics sync complete for user %s: %d updated, %d skipped (no local video)",
        user_id, updated, skipped,
    )
    return {
        "updated": updated,
        "skipped": skipped,
        "last_synced": now.isoformat(),
    }


# Backward-compat alias — routes that call sync_latest_videos(user, max_results=50)
# now transparently perform a full sync.
sync_latest_videos = sync_all_videos


def get_all_connected_user_ids() -> list[str]:
    """Return all user_ids that have a Google OAuth token with youtube scope."""
    with sync_session_scope() as session:
        rows = session.execute(
            select(GoogleOAuthToken.user_id, GoogleOAuthToken.scopes)
        ).all()
    return [r.user_id for r in rows if YOUTUBE_SCOPE in (r.scopes or "")]
