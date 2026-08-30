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
from datetime import date, datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.sync_session import sync_session_scope
from app.db.tables import GoogleOAuthToken, YoutubePublishedVideo, YoutubeTrafficSource, YoutubeVideoLive
from app.services.google_calendar import (
    YOUTUBE_SCOPE,
    YOUTUBE_WRITE_SCOPE,
    YT_ANALYTICS_SCOPE,
    NotConnectedError,
    connection_status,
    load_credentials,
)
from app.services.youtube_cache import flush_youtube_cache_sync

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
    scopes = status.get("scopes", [])
    if YOUTUBE_SCOPE not in scopes and YOUTUBE_WRITE_SCOPE not in scopes:
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
    #
    # watch_time_hours is deliberately NOT written here. It used to be filled with
    # round(views * duration_seconds / 3600), which assumes every viewer watched
    # every video to the very end — an impossible figure that was then read back
    # and displayed as measured watch time. This column belongs to the two sources
    # that actually measure it: a YouTube Studio CSV import, and sync_video_analytics
    # (estimatedMinutesWatched). Left alone, it stays 0 until one of those runs.
    published = pg_insert(YoutubePublishedVideo).values(
        user_id=user_id,
        video_id=vid_id,
        title=title,
        publish_time=published_at,
        duration_seconds=duration_seconds,
        views=views,
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
                # watch_time_hours intentionally absent: a sync must never touch a
                # measured figure, and it no longer has an estimate to offer.
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

    # Step 4 – Auto-sync live YouTube Analytics & schedule YouTube Reporting jobs
    analytics_synced = False
    try:
        sync_video_analytics(user_id)
        sync_traffic_sources(user_id)
        try:
            from app.services.youtube_reporting_service import ensure_default_jobs, download_and_ingest_reports
            ensure_default_jobs(user_id)
            download_and_ingest_reports(user_id)
        except Exception as rep_exc:
            logger.debug("YouTube Reporting API hook: %s", rep_exc)
        analytics_synced = True
    except Exception as exc:
        logger.info("Optional YouTube Analytics auto-sync skipped/deferred for user %s: %s", user_id, exc)

    logger.info(
        "Full sync complete for user %s: %d total (%d new, %d updated, analytics=%s)",
        user_id, total, new_count, updated, analytics_synced,
    )
    flush_youtube_cache_sync(user_id)
    return {
        "synced": total,
        "new": new_count,
        "updated": updated,
        "channel_title": channel_title,
        "last_synced": last_synced,
        "analytics_synced": analytics_synced,
    }


TRAFFIC_SOURCE_LABELS: dict[str, str] = {
    "SHORTS": "YouTube Shorts Feed",
    "YT_SEARCH": "YouTube Search",
    "PLAYLIST": "Playlists",
    "SUBSCRIBER": "Subscriptions Feed",
    "YT_CHANNEL": "Channel Pages",
    "YT_OTHER_PAGE": "Other YouTube Features",
    "NO_LINK_OTHER": "Direct or Unknown",
    "RELATED_VIDEO": "Suggested Videos",
    "EXT_URL": "External",
    "NOTIFICATION": "Notifications",
    "SHORTS_CONTENT_LINKS": "Shorts Remix / Links",
    "END_SCREEN": "End Screens",
    "ANNOTATION": "Cards and Annotations",
}


def sync_traffic_sources(user_id: str, days: int = 90) -> list[dict]:
    """Fetch live traffic sources breakdown from YouTube Analytics API and persist."""
    try:
        yta = _get_analytics_service(user_id)
    except Exception:
        return []

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    try:
        response = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="insightTrafficSourceType",
            sort="-views",
        ).execute()
    except Exception as exc:
        logger.warning("YouTube Analytics traffic sources query failed for user %s: %s", user_id, exc)
        return []

    rows = response.get("rows", [])
    now = datetime.now(timezone.utc)
    synced_sources: list[dict] = []

    with sync_session_scope() as session:
        for r in rows:
            if not r or len(r) < 3:
                continue
            code, views, mins = r[0], int(r[1] or 0), float(r[2] or 0)
            label = TRAFFIC_SOURCE_LABELS.get(code, code)
            watch_time = round(mins / 60.0, 2)
            avg_secs = int((mins * 60) / views) if views > 0 else 0
            avg_dur = f"{avg_secs // 60}:{avg_secs % 60:02d}" if avg_secs else "0:00"

            stmt = pg_insert(YoutubeTrafficSource).values(
                user_id=user_id,
                traffic_source=label,
                views=views,
                watch_time_hours=watch_time,
                avg_view_duration=avg_dur,
                impressions=None,
                impressions_ctr=None,
                imported_at=now,
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[YoutubeTrafficSource.user_id, YoutubeTrafficSource.traffic_source],
                    set_={
                        "views": stmt.excluded.views,
                        "watch_time_hours": stmt.excluded.watch_time_hours,
                        "avg_view_duration": stmt.excluded.avg_view_duration,
                        "imported_at": stmt.excluded.imported_at,
                    },
                )
            )
            synced_sources.append({
                "traffic_source": label,
                "views": views,
                "watch_time_hours": watch_time,
                "avg_view_duration": avg_dur,
                "impressions": None,
                "impressions_ctr": None,
            })
    return synced_sources


def sync_video_analytics(user_id: str, days: int | None = None) -> dict:
    """Pull real watch time, lifetime net subscriber gains, retention and views from the
    YouTube Analytics API and write them onto the matching youtube_videos_live rows.

    One report call returns metrics for up to 200 videos in a single request.
    Rows are matched by video_id against existing youtube_videos_live rows.

    Raises YoutubeAnalyticsScopeMissing / NotConnectedError / YoutubeSyncError.
    """
    yta = _get_analytics_service(user_id)

    end_date = datetime.now(timezone.utc).date()
    if days is not None:
        start_date = end_date - timedelta(days=days)
    else:
        start_date = datetime(2005, 1, 1).date()

    try:
        response = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments,shares",
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
            minutes_watched = float(data.get("estimatedMinutesWatched", 0) or 0)
            watch_time_hours = round(minutes_watched / 60.0, 4) if minutes_watched else None
            gained = int(data.get("subscribersGained", 0) or 0)
            lost = int(data.get("subscribersLost", 0) or 0)
            net_subs = gained - lost
            result = session.execute(
                update(YoutubeVideoLive)
                .where(
                    YoutubeVideoLive.user_id == user_id,
                    YoutubeVideoLive.video_id == video_id,
                )
                .values(
                    average_view_duration_seconds=int(data.get("averageViewDuration", 0) or 0),
                    average_view_percentage=float(data.get("averageViewPercentage", 0) or 0),
                    watch_time_hours=watch_time_hours,
                    subscribers_gained=net_subs,
                    analytics_synced_at=now,
                )
            )
            if result.rowcount:
                updated += 1
            else:
                skipped += 1

    # Also sync live traffic sources
    sync_traffic_sources(user_id, days=days or 90)

    logger.info(
        "Analytics sync complete for user %s: %d updated, %d skipped (no local video)",
        user_id, updated, skipped,
    )
    flush_youtube_cache_sync(user_id)
    return {
        "updated": updated,
        "skipped": skipped,
        "last_synced": now.isoformat(),
    }


def get_channel_overview_stats(user_id: str, time_range: str = "all_time") -> dict:
    """
    Fetch exact channel-level overview metrics directly from YouTube Analytics API.
    Falls back to YouTube Data API v3 channel statistics + local database when
    Analytics API is not enabled in Google Cloud Console or has not run.
    """
    end_date = datetime.now(timezone.utc).date()
    if time_range == "7_days":
        start_date = end_date - timedelta(days=7)
    elif time_range == "30_days":
        start_date = end_date - timedelta(days=30)
    elif time_range == "90_days":
        start_date = end_date - timedelta(days=90)
    elif time_range == "1_year":
        start_date = end_date - timedelta(days=365)
    else:  # all_time / lifetime
        start_date = datetime(2005, 1, 1).date()

    # 1. Try YouTube Analytics API directly for exact watch minutes & subscriber delta
    try:
        yta = _get_analytics_service(user_id)
        response = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments",
        ).execute()

        headers = [h["name"] for h in response.get("columnHeaders", [])]
        rows = response.get("rows", [])
        if rows:
            data = dict(zip(headers, rows[0]))
            views = int(data.get("views", 0) or 0)
            mins_watched = float(data.get("estimatedMinutesWatched", 0) or 0)
            subs_gained = int(data.get("subscribersGained", 0) or 0)
            subs_lost = int(data.get("subscribersLost", 0) or 0)
            net_subs = subs_gained - subs_lost

            # For all_time / lifetime, try to supplement with exact channel subscriber count
            if time_range in ("all_time", "lifetime"):
                try:
                    yt = _get_service(user_id)
                    ch_resp = yt.channels().list(mine=True, part="statistics").execute()
                    if ch_resp.get("items"):
                        st = ch_resp["items"][0].get("statistics", {})
                        net_subs = int(st.get("subscriberCount", net_subs) or net_subs)
                except Exception:
                    pass

            with sync_session_scope() as session:
                total_vids = session.execute(
                    select(func.count(YoutubeVideoLive.video_id)).where(
                        YoutubeVideoLive.user_id == user_id
                    )
                ).scalar() or 0

            return {
                "source": "youtube_analytics_api",
                "total_videos": total_vids,
                "total_views": views,
                "total_watch_time": round(mins_watched / 60.0, 2),
                "total_subscribers": net_subs,
                # The Analytics API call above does not request impressions
                # (it needs the yt-analytics scope + a separate metric); report
                # nothing rather than a multiple of views.
                "total_impressions": None,
            }
    except Exception as exc:
        logger.warning(
            "YouTube Analytics API unavailable for user %s (%s). Using Data API + DB fallback.",
            user_id, exc
        )

    # 2. Fallback: YouTube Data API v3 channel statistics + DB aggregation
    try:
        yt = _get_service(user_id)
        ch_resp = yt.channels().list(mine=True, part="snippet,statistics").execute()
        item = ch_resp.get("items", [{}])[0]
        stats = item.get("statistics", {})
        ch_subscribers = int(stats.get("subscriberCount", 0) or 0)
        ch_views = int(stats.get("viewCount", 0) or 0)
        ch_videos = int(stats.get("videoCount", 0) or 0)

        interval = {
            "7_days": "7 days",
            "30_days": "30 days",
            "90_days": "90 days",
            "1_year": "365 days",
        }.get(time_range)
        date_filter = f"AND date(published_at) >= current_date - interval '{interval}'" if interval else ""

        with sync_session_scope() as session:
            from sqlalchemy import text
            raw_q = text(f"""
                SELECT
                    COUNT(*) AS total_videos,
                    COALESCE(SUM(views), 0) AS total_views,
                    COALESCE(SUM(watch_time_hours), 0) AS explicit_watch_time,
                    COALESCE(SUM(ROUND((views * duration_seconds * 0.40) / 3600.0, 2)), 0) AS estimated_watch_time,
                    COALESCE(SUM(subscribers_gained), 0) AS time_range_subs
                FROM youtube_videos_live
                WHERE user_id = :user_id
                  AND LOWER(title) NOT LIKE '%private%'
                  AND LOWER(title) NOT LIKE '%draft%'
                  {date_filter}
            """)
            db_row = session.execute(raw_q, {"user_id": user_id}).mappings().first()

            db_views = int(db_row["total_views"]) if db_row else 0
            db_vids = int(db_row["total_videos"]) if db_row else 0
            explicit_wt = float(db_row["explicit_watch_time"]) if db_row and db_row["explicit_watch_time"] else 0.0
            estimated_wt = float(db_row["estimated_watch_time"]) if db_row and db_row["estimated_watch_time"] else 0.0
            final_wt = explicit_wt if explicit_wt > 0 else estimated_wt

            is_lifetime = time_range in ("all_time", "lifetime")
            return {
                "source": "youtube_data_api_and_db",
                "total_videos": ch_videos if is_lifetime else db_vids,
                "total_views": ch_views if is_lifetime else db_views,
                "total_watch_time": round(final_wt, 1),
                "total_subscribers": ch_subscribers if is_lifetime else int(db_row["time_range_subs"] or 0) if db_row else 0,
                # No impressions source on this path — the Data API does not expose
                # them. None, not views * 10, which was a fabricated number the
                # dashboard rendered as though measured.
                "total_impressions": None,
            }
    except Exception as exc:
        logger.error("Failed to gather channel stats: %s", exc)
        return {
            "source": "fallback",
            "total_videos": 0,
            "total_views": 0,
            "total_watch_time": 0,
            "total_subscribers": 0,
            "total_impressions": 0,
        }


def get_monthly_channel_series(user_id: str, since: date | None = None) -> list[dict]:
    """Real per-month channel history from the YouTube Analytics API.

    ``dimensions="month"`` over the channel's whole life is the only source that
    can say *when* a milestone was crossed — the video tables hold lifetime
    totals with no time axis, so everything derived from them can only be
    attributed to a video's publish date.

    Raises on any failure (not connected, scope missing, Analytics API disabled
    in Google Cloud Console) so the caller can fall back deliberately rather
    than mistake an empty list for a channel with no history.

    Returns rows sorted oldest-first::

        [{"month": "2021-03", "views": 9493, "watch_time_hours": 1244.0,
          "likes": 120, "comments": 14, "subscribers_gained": 37}, ...]
    """
    yta = _get_analytics_service(user_id)
    start_date = since or datetime(2005, 1, 1).date()
    end_date = datetime.now(timezone.utc).date()

    response = yta.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="views,estimatedMinutesWatched,likes,comments,subscribersGained,subscribersLost",
        dimensions="month",
        sort="month",
    ).execute()

    headers = [h["name"] for h in response.get("columnHeaders", [])]
    out: list[dict] = []
    for row in response.get("rows", []) or []:
        data = dict(zip(headers, row))
        gained = int(data.get("subscribersGained", 0) or 0)
        lost = int(data.get("subscribersLost", 0) or 0)
        out.append({
            # The API returns "2021-03"; keep that shape as the series key.
            "month": str(data.get("month", "")),
            "views": int(data.get("views", 0) or 0),
            "watch_time_hours": round(
                float(data.get("estimatedMinutesWatched", 0) or 0) / 60.0, 2
            ),
            "likes": int(data.get("likes", 0) or 0),
            "comments": int(data.get("comments", 0) or 0),
            # Net, so a month that shed subscribers reads as the loss it was.
            "subscribers_gained": gained - lost,
        })
    return sorted(out, key=lambda r: r["month"])


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


def get_audience_insights(user_id: str, days: int = 90) -> dict:
    """Fetch breakdown of devices, operating systems, demographics, and top countries."""
    try:
        yta = _get_analytics_service(user_id)
    except Exception:
        return {"devices": [], "operating_systems": [], "demographics": [], "geography": []}

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    res: dict[str, list[dict]] = {
        "devices": [],
        "operating_systems": [],
        "demographics": [],
        "geography": [],
    }

    # 1. Devices
    try:
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="deviceType",
            sort="-views",
        ).execute()
        for row in r.get("rows", []):
            res["devices"].append({
                "device": row[0].replace("_", " ").title(),
                "views": int(row[1] or 0),
                "watch_time_hours": round(float(row[2] or 0) / 60.0, 1),
            })
    except Exception as exc:
        logger.debug("Device breakdown query error: %s", exc)

    # 2. Operating Systems
    try:
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="operatingSystem",
            sort="-views",
        ).execute()
        for row in r.get("rows", []):
            res["operating_systems"].append({
                "os": row[0].replace("_", " ").title(),
                "views": int(row[1] or 0),
                "watch_time_hours": round(float(row[2] or 0) / 60.0, 1),
            })
    except Exception as exc:
        logger.debug("OS breakdown query error: %s", exc)

    # 3. Demographics
    try:
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="viewerPercentage",
            dimensions="ageGroup,gender",
            sort="-viewerPercentage",
        ).execute()
        for row in r.get("rows", []):
            res["demographics"].append({
                "age_group": str(row[0]).replace("age", ""),
                "gender": str(row[1]).capitalize(),
                "percentage": float(row[2] or 0),
            })
    except Exception as exc:
        logger.debug("Demographics query error: %s", exc)

    # 4. Top Countries
    try:
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="country",
            sort="-views",
            maxResults=8,
        ).execute()
        for row in r.get("rows", []):
            res["geography"].append({
                "country_code": str(row[0]),
                "views": int(row[1] or 0),
                "watch_time_hours": round(float(row[2] or 0) / 60.0, 1),
            })
    except Exception as exc:
        logger.debug("Geography query error: %s", exc)

    return res


def update_video_metadata(
    user_id: str,
    video_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    category_id: str | None = None,
) -> dict:
    """Update title, description, tags, or category on YouTube Data API v3,
    then reflect the update immediately in the local database (youtube_videos_live).
    """
    from googleapiclient.errors import HttpError

    youtube = _get_service(user_id)
    try:
        # Fetch current snippet to keep required fields (e.g. categoryId, title) intact
        list_resp = youtube.videos().list(part="snippet,status", id=video_id).execute()
        items = list_resp.get("items", [])
        if not items:
            raise ValueError(f"Video {video_id} not found on YouTube.")

        snippet = items[0]["snippet"]
        if title is not None and title.strip():
            snippet["title"] = title.strip()
        if description is not None:
            snippet["description"] = description.strip()
        if tags is not None:
            snippet["tags"] = [t.strip() for t in tags if t.strip()]
        if category_id is not None:
            snippet["categoryId"] = str(category_id)

        update_resp = youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": snippet,
            },
        ).execute()

        new_snippet = update_resp.get("snippet", snippet)
        new_title = new_snippet.get("title", title or "")
        new_desc = new_snippet.get("description", description or "")
        new_tags = new_snippet.get("tags") or tags or []
        new_cat = new_snippet.get("categoryId", category_id)

        # Recalculate SEO scores
        seo_title = _compute_seo_title_score(new_title)
        seo_tags = len(new_tags)
        seo_words = _compute_seo_desc_words(new_desc)

        # Update local database
        with sync_session_scope() as session:
            session.execute(
                update(YoutubeVideoLive)
                .where(
                    YoutubeVideoLive.user_id == user_id,
                    YoutubeVideoLive.video_id == video_id,
                )
                .values(
                    title=new_title,
                    description=new_desc,
                    tags=new_tags,
                    category_id=new_cat,
                    seo_title_score=seo_title,
                    seo_tag_count=seo_tags,
                    seo_desc_words=seo_words,
                    fetched_at=datetime.now(timezone.utc),
                )
            )

        flush_youtube_cache_sync(user_id)
        return {
            "success": True,
            "video_id": video_id,
            "title": new_title,
            "description": new_desc,
            "tags": new_tags,
            "category_id": new_cat,
            "seo_title_score": seo_title,
            "seo_tag_count": seo_tags,
            "seo_desc_words": seo_words,
            "message": "Video successfully updated on YouTube!",
        }
    except HttpError as exc:
        if exc.resp is not None and exc.resp.status in (401, 403):
            err_details = str(exc)
            if (
                "insufficient" in err_details.lower()
                or "permission" in err_details.lower()
                or "forbidden" in err_details.lower()
                or "scope" in err_details.lower()
            ):
                raise YoutubeScopeMissing(
                    "YouTube write permission missing. Please reconnect your Google account in Settings to grant video update permissions."
                )
        raise _handle_http_error(exc)

