"""
Resolve an *arbitrary* YouTube channel from whatever a human pasted, and pull
its public upload history.

Everything else in this codebase that touches YouTube either works on the
signed-in user's own channel (``app.services.youtube_sync_service``, via OAuth +
the Analytics API) or on a channel that is already a tracked competitor row
(``app.services.youtube_competitor``). This module is the missing front door:
a free-text query -> a normalized channel row -> that channel's videos.

It deliberately reuses the resolution primitives in
``app.services.youtube_competitor`` rather than re-implementing them, but does
*not* go through ``verify_candidates()``: that function drops any channel
reporting ``subscriberCount == 0 AND videoCount == 0``, which is correct for
competitor discovery (a dead channel is not a competitor) but wrong here —
plenty of real, active creators simply hide their subscriber count.

Quota, for a full lookup + 200-video pull: roughly 10 units against the
10,000/day default. The 100-unit ``search.list`` path is a last resort only.
"""

from __future__ import annotations

import logging
import re

from app.services.youtube_competitor import (
    LOOKUP_COST,
    QuotaLedger,
    _resolve_by_handle,
    _resolve_by_ids,
    _resolve_by_search,
    _sync_videos_via_rss,
    _to_row,
    search_youtube_channels_direct,
)
from app.services.youtube_data import _service

logger = logging.getLogger(__name__)

# playlistItems.list and videos.list both cap at 50 per page.
_PAGE_SIZE = 50
DEFAULT_UPLOAD_LIMIT = 200

_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/(?P<path>.*)$", re.I
)
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def normalize_channel_query(raw: str) -> dict:
    """Classify a pasted channel reference.

    Returns a dict carrying ``raw`` plus exactly one of ``channel_id``,
    ``handle``, ``video_id`` or ``name``. A ``/c/`` or ``/user/`` custom URL
    yields *both* ``handle`` and ``name`` — the custom slug usually matches the
    modern @handle, but not always, so the resolver tries the cheap handle
    lookup first and falls back to a search on the same string.
    """
    text = (raw or "").strip()
    if not text:
        return {"raw": text}

    out: dict = {"raw": text}
    match = _URL_RE.match(text)
    if match:
        path = match.group("path")
        # Drop query string and fragment, then trailing slashes.
        path = path.split("?")[0].split("#")[0].strip("/")
        # youtu.be/<id> carries the video id as the whole path.
        if "youtu.be" in text.lower() and _VIDEO_ID_RE.match(path):
            out["video_id"] = path
            return out
        if not path:
            return out

        segments = [s for s in path.split("/") if s]
        head = segments[0]

        if head == "watch":
            # /watch?v=... — the id lives in the query string we just dropped.
            vid = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", text)
            if vid:
                out["video_id"] = vid.group(1)
            return out
        if head in ("shorts", "live", "embed") and len(segments) > 1:
            if _VIDEO_ID_RE.match(segments[1]):
                out["video_id"] = segments[1]
                return out
        if head == "channel" and len(segments) > 1:
            out["channel_id"] = segments[1]
            return out
        if head.startswith("@"):
            out["handle"] = head
            return out
        if head in ("c", "user") and len(segments) > 1:
            out["handle"] = f"@{segments[1]}"
            out["name"] = segments[1]
            return out
        # Bare youtube.com/<something> — treat as a custom URL.
        out["handle"] = f"@{head}"
        out["name"] = head
        return out

    if text.startswith("@"):
        out["handle"] = text.rstrip("/")
        return out
    if _CHANNEL_ID_RE.match(text):
        out["channel_id"] = text
        return out

    out["name"] = text
    return out


def _channel_id_from_video(yt, video_id: str, ledger: QuotaLedger) -> str | None:
    """1 quota unit. Lets a viewer paste any video link and get its channel."""
    try:
        resp = yt.videos().list(part="snippet", id=video_id).execute()
    except Exception as exc:
        logger.info("videos.list lookup failed for %s: %s", video_id, exc)
        return None
    ledger.spend(LOOKUP_COST)
    items = resp.get("items", [])
    if not items:
        return None
    return (items[0].get("snippet") or {}).get("channelId")


def _scraped_match(query: str) -> dict | None:
    """Zero-quota scrapetube search, best match first."""
    results = search_youtube_channels_direct(query, limit=5)
    return results[0] if results else None


def resolve_channel(user_id: str, query: str, ledger: QuotaLedger | None = None) -> dict | None:
    """Resolve free text / a URL / a handle / a channel id to one channel row.

    Returns the ``_to_row()`` shape (channel_id, title, handle, description,
    thumbnail_url, uploads_playlist_id, country, subscriber_count, view_count,
    video_count, ...) or ``None`` when nothing matched.

    Works without Google OAuth by falling back to the scrapetube path, which
    returns approximate subscriber counts and no view/video totals.
    """
    ledger = ledger or QuotaLedger()
    parsed = normalize_channel_query(query)
    if len(parsed) <= 1:
        return None

    try:
        yt = _service(user_id)
    except Exception:
        yt = None

    channel_id = parsed.get("channel_id")
    handle = parsed.get("handle")
    name = parsed.get("name")

    if yt is not None:
        if parsed.get("video_id"):
            channel_id = _channel_id_from_video(yt, parsed["video_id"], ledger)

        if channel_id:
            item = _resolve_by_ids(yt, [channel_id], ledger).get(channel_id)
            if item:
                return _to_row(parsed, item)

        if handle:
            item = _resolve_by_handle(yt, handle, ledger)
            if item:
                return _to_row(parsed, item)

        # Scrapetube costs nothing, so try it before the 100-unit search.list.
        probe = name or (handle or "").lstrip("@") or parsed["raw"]
        scraped = _scraped_match(probe)
        if scraped:
            item = _resolve_by_ids(yt, [scraped["channel_id"]], ledger).get(scraped["channel_id"])
            if item:
                return _to_row(scraped, item)
            return scraped

        item = _resolve_by_search(yt, probe, ledger)
        if item:
            return _to_row(parsed, item)
        return None

    # ── No OAuth: scrapetube only. ───────────────────────────────────────────
    if parsed.get("video_id"):
        # A video id is not searchable without the API.
        return None
    probe = name or (handle or "").lstrip("@") or channel_id or parsed["raw"]
    scraped = _scraped_match(probe)
    if not scraped:
        return None
    if channel_id and scraped.get("channel_id") != channel_id:
        # Searching for a raw UC id rarely returns that exact channel; don't
        # hand back a confidently-wrong match.
        return None
    return scraped


def fetch_channel_uploads(
    user_id: str,
    channel_id: str,
    uploads_playlist_id: str = "",
    ledger: QuotaLedger | None = None,
    limit: int = DEFAULT_UPLOAD_LIMIT,
) -> tuple[list[dict], bool]:
    """Public upload history for any channel.

    Returns ``(videos, duration_available)``.

    ``app.services.youtube_competitor.sync_competitor_videos`` already does this
    but caps at 50 and does not paginate — an audit needs a few hundred videos
    to say anything credible about cadence or length. Roughly 8 quota units for
    200 videos (one playlistItems page + one videos.list batch per 50).

    ``duration_available`` is False on the RSS fallback path, which carries no
    duration, no comment counts and only the ~15 most recent uploads. Callers
    MUST suppress any length-based analysis in that case rather than treating
    the zeros as real: a "0 second" bucket is a different claim from "unknown".
    """
    ledger = ledger or QuotaLedger()
    uploads_playlist_id = uploads_playlist_id or (
        f"UU{channel_id[2:]}" if channel_id.startswith("UC") else ""
    )

    yt = None
    try:
        yt = _service(user_id)
    except Exception:
        yt = None

    if yt is not None and uploads_playlist_id:
        try:
            videos = _fetch_uploads_via_api(yt, channel_id, uploads_playlist_id, ledger, limit)
            if videos:
                return videos, True
        except Exception as exc:
            logger.warning(
                "Data API upload fetch failed for %s (%s); falling back to RSS", channel_id, exc
            )

    return _sync_videos_via_rss(channel_id, limit=min(limit, 15)), False


def _fetch_uploads_via_api(
    yt, channel_id: str, uploads_playlist_id: str, ledger: QuotaLedger, limit: int
) -> list[dict]:
    from app.services.youtube_sync_service import _parse_duration

    video_ids: list[str] = []
    page_token: str | None = None
    while len(video_ids) < limit:
        resp = (
            yt.playlistItems()
            .list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(_PAGE_SIZE, limit - len(video_ids)),
                pageToken=page_token,
            )
            .execute()
        )
        ledger.spend(LOOKUP_COST)
        for item in resp.get("items", []):
            vid = (item.get("contentDetails") or {}).get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    videos: list[dict] = []
    for i in range(0, len(video_ids), _PAGE_SIZE):
        chunk = video_ids[i : i + _PAGE_SIZE]
        resp = (
            yt.videos()
            .list(part="snippet,contentDetails,statistics", id=",".join(chunk))
            .execute()
        )
        ledger.spend(LOOKUP_COST)
        for item in resp.get("items", []):
            snippet = item.get("snippet") or {}
            stats = item.get("statistics") or {}
            thumbs = snippet.get("thumbnails") or {}
            duration = _parse_duration((item.get("contentDetails") or {}).get("duration", ""))
            videos.append({
                "video_id": item["id"],
                "channel_id": channel_id,
                "title": snippet.get("title", ""),
                "description": (snippet.get("description") or "")[:1500],
                "published_at": snippet.get("publishedAt"),
                "duration_seconds": duration,
                "is_short": 0 < duration <= 60,
                "views": int(stats.get("viewCount", 0) or 0),
                "likes": int(stats.get("likeCount", 0) or 0),
                "comments": int(stats.get("commentCount", 0) or 0),
                "tags": snippet.get("tags") or [],
                "thumbnail_url": (thumbs.get("high") or thumbs.get("default") or {}).get("url"),
            })
    return videos
