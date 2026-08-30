"""
YouTube analytics: imported CSV metrics, live-synced video data, and
Gemini-powered strategy/roadmap/playlist-trend analysis.

Every endpoint here is now authenticated and every query is scoped to the
caller's ``user_id``. Four endpoints (``/import``, ``/videos``,
``/traffic-sources``, ``/stats``) previously had **no** ``Depends`` at all —
anyone could trigger a filesystem import or read the aggregate channel data.
The Redis cache keys are user-scoped for the same reason: the old keys
(``yt:videos:*``, ``yt:stats:*``, ...) were global, so whichever tenant synced
last served analytics to everyone.
"""

import asyncio
import collections as _collections
import logging
from datetime import date as _date
from datetime import datetime, timezone
from datetime import timedelta as _timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.auth_deps import get_current_user
from app.core.redis_client import acache, bump_epoch, get_epoch, uk
from app.db import queries
from app.db.models import YoutubePublishedVideo, YoutubeTrafficSource
from app.db.session import get_session
from app.services.personal_intelligence import get_directives
from app.services import roadmap_to_plan
from app.services.youtube_import import import_youtube_data
from app.services.youtube_metrics import (
    duration_bucket as _duration_bucket,
    extract_keywords as _extract_keywords,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube-analytics", tags=["YouTube Analytics"])

# All YouTube analytics data (stats, videos, playlists, AI analysis, web search)
# is cached for 5 minutes.
CACHE_TTL_SECONDS = 300


# ── Cache helpers ─────────────────────────────────────────────────────────────
#
# Keys fold in a per-user "epoch" (see app.core.redis_client.bump_epoch)
# instead of the old free-form yt:* names. Bumping the epoch after an import or
# sync makes every previous key for that user unreachable in O(1); the old
# `_flush_live_cache()` ran `KEYS yt:*` + `DELETE`, an O(keyspace) scan that
# blocks Redis for every other client — and it flushed every tenant's cache.


async def _domain_key(user_id: str, domain: str, *parts: str) -> str:
    epoch = await get_epoch(user_id, domain)
    return uk(user_id, domain, str(epoch), *parts)


async def _get_cached(cache_key: str) -> Any | None:
    try:
        raw = await acache().get(cache_key)
    except Exception as exc:
        logger.error("[CACHE GET ERROR] key=%s: %s", cache_key, exc)
        return None
    if raw is None:
        return None
    import json

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


async def _set_cached(cache_key: str, data: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    import json

    try:
        await acache().setex(cache_key, ttl, json.dumps(data, default=str))
    except Exception as exc:
        logger.error("[CACHE SET ERROR] key=%s: %s", cache_key, exc)


async def _flush_live_cache(user_id: str) -> None:
    """Invalidate this user's cached YouTube data across all domains."""
    from app.services.youtube_cache import flush_youtube_cache
    await flush_youtube_cache(user_id)


# ── Saved analyses ────────────────────────────────────────────────────────────
#
# The cache above is only a 5-minute shortcut around a 30-60s LLM call;
# youtube_analyses is the durable record so a page reload doesn't lose the run.
# A cache hit is the same run that was already saved, so it reuses that row's
# id instead of writing a duplicate.


async def _save_analysis(
    session: AsyncSession, user_id: str, kind: str, time_range: str,
    result: Dict[str, Any], weeks: int | None = None,
) -> Dict[str, Any]:
    """Persist a freshly generated analysis, stamping its id onto the response."""
    try:
        row = await queries.create_youtube_analysis(
            session, user_id, kind, time_range, result, weeks=weeks, model=result.get("model"),
        )
    except Exception:  # never fail a good analysis because the save broke
        logger.exception("Could not save %s analysis", kind)
        return result
    result["analysis_id"] = row["id"]
    result["created_at"] = row["created_at"]
    return result


async def _stamp_cached(
    session: AsyncSession, user_id: str, kind: str, time_range: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Point a cached payload at the saved row it came from."""
    if payload.get("analysis_id"):
        return payload
    try:
        row = await queries.get_latest_youtube_analysis(session, user_id, kind, time_range)
    except Exception:
        return payload
    if row:
        payload["analysis_id"] = row["id"]
        payload["created_at"] = row["created_at"]
    return payload


@router.get("/analyses")
async def list_analyses(
    kind: str = None, limit: int = 20,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Past analysis runs, newest first — metadata only (no payload)."""
    return await queries.get_youtube_analyses(session, user["id"], kind=kind, limit=max(1, min(limit, 100)))


# Declared BEFORE "/analyses/{analysis_id}" so "latest" is not read as an id.
@router.get("/analyses/latest")
async def get_latest_analysis(
    kind: str, time_range: str = None,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """The newest saved run of `kind`, or {} when there is none yet."""
    return await queries.get_latest_youtube_analysis(session, user["id"], kind, time_range) or {}


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: str, user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    row = await queries.get_youtube_analysis_by_id(session, analysis_id, user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return row


@router.delete("/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: str, user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, str]:
    if not await queries.delete_youtube_analysis(session, analysis_id, user["id"]):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"message": "Analysis deleted"}


@router.post("/import")
async def trigger_youtube_import(
    user: dict = Depends(get_current_user),
) -> dict:
    """Import the YouTube Studio CSV exports for the current user.

    Was unauthenticated and imported into a single global table; both are now
    fixed. It also touches the filesystem (``data/Youtube``), so this remains
    an operator/self-service action rather than something exposed in the UI
    beyond the account owner.
    """
    # CSV parsing + a batch of DB upserts — off the event loop.
    result = await asyncio.to_thread(import_youtube_data, user["id"])
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))

    await _flush_live_cache(user["id"])
    return result


_TIME_RANGE_SQL = {
    "7_days": "date(publish_time) >= current_date - interval '7 days'",
    "30_days": "date(publish_time) >= current_date - interval '30 days'",
    "90_days": "date(publish_time) >= current_date - interval '90 days'",
    "1_year": "date(publish_time) >= current_date - interval '365 days'",
}

# Plain interval strings used for per-branch filtering in stats query
# (where the date column name differs between the live and legacy table).
_TIME_RANGE_INTERVAL: dict[str, str | None] = {
    "all_time": None,
    "7_days": "7 days",
    "30_days": "30 days",
    "90_days": "90 days",
    "1_year": "365 days",
}


def _range_clause(time_range: str) -> str:
    """A SQL boolean expression for the requested time range, or '' for all_time.

    ``time_range`` is validated against the fixed dict above before ever being
    interpolated, so this is not building a query from request-controlled text.
    """
    return _TIME_RANGE_SQL.get(time_range, "")


@router.get("/videos", response_model=List[YoutubePublishedVideo])
async def get_youtube_videos(
    limit: int = 50, offset: int = 0, sort_by: str = "views", time_range: str = "all_time",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Published YouTube videos for the current user, sorted by views or publish_time.

    UNIONs the live-synced table (richer, from the YouTube Data API) with the
    legacy CSV-imported table, preferring live data for any video_id present in
    both. Both source tables carry the composite ``(user_id, video_id)`` key
    introduced to stop two tenants' syncs from overwriting each other.
    """
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-videos", time_range, sort_by, str(limit), str(offset))
    cached = await _get_cached(cache_key)
    if cached:
        return [YoutubePublishedVideo(**r) for r in cached]

    valid_sort_columns = {"views", "publish_time", "published_at", "duration_seconds", "watch_time_hours", "likes", "comments"}
    if sort_by not in valid_sort_columns:
        sort_by = "views"
    sort_col = "publish_time" if sort_by in ("publish_time", "published_at") else sort_by
    range_sql = _range_clause(time_range)
    range_clause = f"AND {range_sql}" if range_sql else ""

    # Every metric here is measured or NULL. This query used to invent three of
    # them: watch_time_hours as views * duration (i.e. assuming every viewer
    # watched to the end), subscribers as a literal 0, and impressions as
    # views * 10. They rendered identically to real figures.
    #
    # watch_time_hours prefers the CSV column deliberately: youtube_videos_live's
    # is filled by sync_video_analytics from a 90-day Analytics query, so mixing
    # it in would show a quarter's watch time for recent videos beside lifetime
    # figures for the rest. impressions/CTR are NOT NULL DEFAULT 0 in the live
    # table, where 0 means "sync-analytics has not run" — NULLIF says that.
    query = text(f"""
        SELECT video_id, title, publish_time, duration_seconds, views,
               likes, comments, thumbnail_url,
               watch_time_hours, subscribers, impressions, impressions_ctr,
               average_view_percentage, average_view_duration_seconds
        FROM (
            SELECT
                l.video_id, l.title,
                l.published_at AS publish_time,
                l.duration_seconds,
                l.views,
                l.likes,
                l.comments,
                COALESCE(l.thumbnail_url, 'https://i.ytimg.com/vi/' || l.video_id || '/hqdefault.jpg') AS thumbnail_url,
                COALESCE(p.watch_time_hours, l.watch_time_hours) AS watch_time_hours,
                l.subscribers_gained AS subscribers,
                NULLIF(l.impressions, 0) AS impressions,
                NULLIF(l.impressions_ctr, 0) AS impressions_ctr,
                NULLIF(l.average_view_percentage, 0.0) AS average_view_percentage,
                NULLIF(l.average_view_duration_seconds, 0) AS average_view_duration_seconds
            FROM youtube_videos_live l
            LEFT JOIN youtube_published_videos p
                   ON p.user_id = l.user_id AND p.video_id = l.video_id
            WHERE l.user_id = :user_id

            UNION ALL

            SELECT
                p.video_id, p.title,
                p.publish_time,
                p.duration_seconds,
                p.views,
                0 AS likes,
                0 AS comments,
                'https://i.ytimg.com/vi/' || p.video_id || '/hqdefault.jpg' AS thumbnail_url,
                p.watch_time_hours,
                NULLIF(p.subscribers, 0) AS subscribers,
                p.impressions,
                p.impressions_ctr,
                NULL AS average_view_percentage,
                NULL AS average_view_duration_seconds
            FROM youtube_published_videos p
            WHERE p.user_id = :user_id
              AND NOT EXISTS (
                  SELECT 1 FROM youtube_videos_live l
                  WHERE l.user_id = p.user_id AND l.video_id = p.video_id
              )
        ) AS combined
        WHERE LOWER(title) NOT LIKE '%private%'
          AND LOWER(title) NOT LIKE '%draft%'
          {range_clause}
        ORDER BY {sort_col} {"DESC"} NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    rows = (
        await session.execute(query, {"user_id": user_id, "limit": limit, "offset": offset})
    ).mappings().all()

    # publish_time comes back as a Postgres datetime for rows sourced from
    # youtube_videos_live (TIMESTAMPTZ column) — YoutubePublishedVideo declares
    # publish_time: Optional[str], so constructing it directly from the raw row
    # raises a pydantic ValidationError on every cache-miss (a cache-hit masked
    # this before, since _set_cached's json.dumps(..., default=str) stringifies
    # it on the way into the cache).
    result = [
        {**dict(r), "publish_time": r["publish_time"].isoformat() if hasattr(r["publish_time"], "isoformat") else r["publish_time"]}
        for r in rows
    ]
    await _set_cached(cache_key, result)
    return [YoutubePublishedVideo(**r) for r in result]


@router.get("/traffic-sources", response_model=List[YoutubeTrafficSource])
async def get_traffic_sources(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """YouTube traffic sources for the current user, sorted by views."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-traffic")
    cached = await _get_cached(cache_key)
    if cached:
        return [YoutubeTrafficSource(**r) for r in cached]

    rows = (
        await session.execute(
            text(
                "SELECT * FROM youtube_traffic_sources WHERE user_id = :user_id ORDER BY views DESC"
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    if not rows:
        from app.services.youtube_sync_service import sync_traffic_sources

        await asyncio.to_thread(sync_traffic_sources, user_id)
        rows = (
            await session.execute(
                text(
                    "SELECT * FROM youtube_traffic_sources WHERE user_id = :user_id ORDER BY views DESC"
                ),
                {"user_id": user_id},
            )
        ).mappings().all()

    result = [dict(r) for r in rows]
    await _set_cached(cache_key, result)
    return [YoutubeTrafficSource(**r) for r in result]


@router.get("/stats")
async def get_youtube_overall_stats(
    time_range: str = "all_time",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Aggregate statistics for the current user (live + legacy combined)."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-stats", time_range)
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    from app.services.youtube_sync_service import get_channel_overview_stats

    # Gather accurate channel statistics directly from YouTube Analytics API / Data API
    result_data = await asyncio.to_thread(get_channel_overview_stats, user_id, time_range)
    if not result_data or result_data.get("total_views") == 0:
        # DB query fallback
        interval = _TIME_RANGE_INTERVAL.get(time_range)
        date_filter = f"AND date(published_at) >= current_date - interval '{interval}'" if interval else ""
        raw_q = text(f"""
            SELECT
                COUNT(*) AS total_videos,
                COALESCE(SUM(views), 0) AS total_views,
                COALESCE(SUM(watch_time_hours), 0) AS explicit_watch_time,
                COALESCE(SUM(ROUND((views * duration_seconds * 0.40) / 3600.0, 2)), 0) AS estimated_watch_time,
                COALESCE(SUM(subscribers_gained), 0) AS total_subscribers,
                COALESCE(SUM(views * 10), 0) AS total_impressions
            FROM youtube_videos_live
            WHERE user_id = :user_id
              AND LOWER(title) NOT LIKE '%private%'
              AND LOWER(title) NOT LIKE '%draft%'
              {date_filter}
        """)
        row = (await session.execute(raw_q, {"user_id": user_id})).mappings().first()
        if row:
            db_row = dict(row)
            explicit_wt = float(db_row.get("explicit_watch_time") or 0.0)
            estimated_wt = float(db_row.get("estimated_watch_time") or 0.0)
            result_data = {
                "total_videos": int(db_row.get("total_videos") or 0),
                "total_views": int(db_row.get("total_views") or 0),
                "total_watch_time": round(explicit_wt if explicit_wt > 0 else estimated_wt, 1),
                "total_subscribers": int(db_row.get("total_subscribers") or 0),
                "total_impressions": int(db_row.get("total_impressions") or 0),
            }

    await _set_cached(cache_key, result_data)
    return result_data


async def _gather_channel_context(
    session: AsyncSession, user_id: str, time_range: str
) -> tuple[str, int]:
    """Build a compact, human-readable summary of the channel's data for the LLM.

    Returns (context_text, video_count). video_count is used to short-circuit
    the AI call when there is nothing to analyze.
    """
    range_sql = _range_clause(time_range)
    range_clause = f"AND {range_sql}" if range_sql else ""
    base_where = f"WHERE LOWER(title) NOT LIKE '%private%' AND LOWER(title) NOT LIKE '%draft%' {range_clause}"

    combined_cte = f"""
        WITH combined AS (
            SELECT video_id, title, published_at AS publish_time, duration_seconds, views,
                   COALESCE(watch_time_hours, ROUND((views * duration_seconds * 0.40) / 3600.0, 2)) AS watch_time_hours,
                   average_view_percentage, subscribers_gained,
                   COALESCE(impressions, views * 10) AS impressions, impressions_ctr
            FROM youtube_videos_live
            WHERE user_id = :user_id

            UNION ALL

            SELECT video_id, title, publish_time, duration_seconds, views, watch_time_hours,
                   0.0 AS average_view_percentage, subscribers AS subscribers_gained,
                   impressions, impressions_ctr
            FROM youtube_published_videos
            WHERE user_id = :user_id
              AND video_id NOT IN (
                  SELECT video_id FROM youtube_videos_live WHERE user_id = :user_id
              )
        )
    """

    overall = (
        await session.execute(
            text(
                f"{combined_cte} "
                f"SELECT COUNT(video_id) AS videos, COALESCE(SUM(views),0) AS views, "
                f"COALESCE(SUM(watch_time_hours),0) AS watch_time, "
                f"COALESCE(SUM(impressions),0) AS impressions, "
                f"COALESCE(AVG(average_view_percentage),0) AS avg_retention "
                f"FROM combined {base_where}"
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    overall = dict(overall) if overall else {}

    video_count = overall.get("videos", 0) or 0
    if not video_count:
        return "", 0

    top = [
        dict(r)
        for r in (
            await session.execute(
                text(
                    f"{combined_cte} "
                    f"SELECT title, views, watch_time_hours, average_view_percentage, subscribers_gained "
                    f"FROM combined {base_where} ORDER BY views DESC LIMIT 8"
                ),
                {"user_id": user_id},
            )
        ).mappings().all()
    ]
    low = [
        dict(r)
        for r in (
            await session.execute(
                text(
                    f"{combined_cte} "
                    f"SELECT title, views, watch_time_hours, average_view_percentage "
                    f"FROM combined {base_where} ORDER BY views ASC LIMIT 5"
                ),
                {"user_id": user_id},
            )
        ).mappings().all()
    ]
    traffic = [
        dict(r)
        for r in (
            await session.execute(
                text(
                    "SELECT traffic_source, views, watch_time_hours "
                    "FROM youtube_traffic_sources WHERE user_id = :user_id "
                    "ORDER BY views DESC LIMIT 12"
                ),
                {"user_id": user_id},
            )
        ).mappings().all()
    ]

    lines = [
        f"OVERVIEW: {overall['videos']} videos, {int(overall['views']):,} total views, "
        f"{overall['watch_time']:.1f} watch-hours, {int(overall['impressions']):,} impressions, "
        f"{overall.get('avg_retention', 0):.1f}% average retention.",
        "",
        "TOP VIDEOS (by views):",
    ]
    for v in top:
        retention_str = f", {v['average_view_percentage']:.1f}% retention" if v.get("average_view_percentage") else ""
        subs_str = f", +{v['subscribers_gained']} subs" if v.get("subscribers_gained") else ""
        lines.append(
            f"- {v['title']} — {int(v['views']):,} views, {v['watch_time_hours']:.1f} watch-hrs{retention_str}{subs_str}"
        )
    lines += ["", "LOWEST-VIEW VIDEOS:"]
    for v in low:
        retention_str = f", {v['average_view_percentage']:.1f}% retention" if v.get("average_view_percentage") else ""
        lines.append(
            f"- {v['title']} — {int(v['views']):,} views{retention_str}"
        )
    if traffic:
        lines += ["", "TRAFFIC SOURCES (by views):"]
        for t in traffic:
            lines.append(
                f"- {t['traffic_source']}: {int(t['views']):,} views, {t.get('watch_time_hours', 0):.1f}h watch time"
            )

    from app.services.youtube_competitor_context import build_competitor_block

    competitor_block = await build_competitor_block(session, user_id)
    if competitor_block:
        lines += ["", competitor_block]

    return "\n".join(lines), video_count


@router.post("/ai-analysis")
async def generate_ai_analysis(
    time_range: str = "all_time", refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Generate an AI (Gemini 3.6 Flash) strategic analysis of the channel's performance."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-ai-analysis", time_range)
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return await _stamp_cached(session, user_id, "ai_analysis", time_range, cached)

    context, video_count = await _gather_channel_context(session, user_id, time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    # Imported lazily so crewai/LLM deps don't load unless AI analysis is requested.
    from app.services import youtube_ai_analysis

    directives = await get_directives(session, user_id, scope="youtube")
    try:
        result = await youtube_ai_analysis.analyze_channel(
            context, time_range=time_range, directives=directives
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")

    result["time_range"] = time_range
    await _set_cached(cache_key, result)
    return await _save_analysis(session, user_id, "ai_analysis", time_range, result)


# ── Playlist-wise latest videos & trending topics (YouTube Data API + Gemini 3.6 Flash) ────


def _map_youtube_error(exc: Exception) -> HTTPException:
    """Translate youtube_data / google_calendar errors into clean HTTP responses."""
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_data import (
        YoutubeApiDisabledError,
        YoutubeDataError,
        YoutubeScopeError,
    )

    if isinstance(exc, YoutubeScopeError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotConnectedError):
        return HTTPException(status_code=400, detail=str(exc) or "Google account not connected.")
    if isinstance(exc, YoutubeApiDisabledError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, YoutubeDataError):
        return HTTPException(status_code=502, detail=str(exc))
    logger.exception("Unexpected YouTube data error")
    return HTTPException(status_code=502, detail=f"YouTube data error: {exc}")


@router.get("/playlists")
async def get_playlists(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """List the connected channel's playlists plus its uploads playlist id."""
    from app.services import youtube_data

    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-playlists")
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    try:
        # googleapiclient is a synchronous HTTP client — off the event loop.
        overview = await asyncio.to_thread(youtube_data.get_channel_overview, user_id)
        playlists = await asyncio.to_thread(youtube_data.list_playlists, user_id)
    except Exception as exc:
        raise _map_youtube_error(exc)

    result = {**overview, "playlists": playlists}
    await _set_cached(cache_key, result)
    return result


@router.get("/playlist-videos")
async def get_playlist_videos(
    playlist_id: str, limit: int = 10, user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Latest videos in a playlist (or the uploads playlist), enriched with metrics."""
    from app.services import youtube_data

    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-playlist-videos", playlist_id, str(limit))
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    try:
        videos = await asyncio.to_thread(
            youtube_data.list_playlist_videos, user_id, playlist_id, max_results=limit
        )
    except Exception as exc:
        raise _map_youtube_error(exc)

    await _set_cached(cache_key, videos)
    return videos


async def _cached_web_search(query: str, max_results: int = 6, bypass: bool = False) -> str:
    """Run the multi-source web search, caching raw results for 5 min.

    Deliberately global (``gk``), not user-scoped: the result is a pure
    function of the search query — public web content, nothing tenant-specific
    — so scoping it per user would just multiply outbound search calls.
    """
    from app.core.redis_client import gk
    from app.tools.custom import run_web_search

    cache_key = gk("yt-websearch", query)
    if not bypass:
        cached = await _get_cached(cache_key)
        if cached is not None:
            return str(cached)

    result = await asyncio.to_thread(run_web_search, query, max_results)
    if result:
        await _set_cached(cache_key, result)
    return result


def _format_videos_block(videos: List[Dict[str, Any]]) -> str:
    lines = []
    for v in videos:
        metric = ""
        if v.get("views") is not None:
            metric = f" — {int(v['views']):,} views, {v.get('impressions_ctr', 0)}% CTR"
        date = (v.get("published_at") or "")[:10]
        lines.append(f"- {v.get('title', '')} ({date}){metric}")
    return "\n".join(lines)


@router.post("/playlist-trends")
async def generate_playlist_trends(
    playlist_id: str,
    playlist_title: str = "",
    refresh: bool = False,
    only_cached: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Trending next-video topics for one playlist: its latest videos + live web
    research, synthesized by Gemini 3.6 Flash."""
    from app.services import youtube_ai_analysis, youtube_data

    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-playlist-trends", playlist_id)
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return cached
        if only_cached:
            return {"trending_topics": [], "playlist_id": playlist_id, "cached": False}

    try:
        videos = await asyncio.to_thread(
            youtube_data.list_playlist_videos, user_id, playlist_id, max_results=8
        )
    except Exception as exc:
        raise _map_youtube_error(exc)

    title = playlist_title or "this playlist"
    videos_block = _format_videos_block(videos)

    # Live web trends for the playlist's theme (best-effort — never fatal).
    try:
        web_context = await _cached_web_search(
            f"latest trending YouTube video topics {title} 2026", 6, refresh
        )
    except Exception as exc:
        logger.warning("Web research failed for playlist trends: %s", exc)
        web_context = ""

    directives = await get_directives(session, user_id, scope="youtube")
    try:
        result = await youtube_ai_analysis.analyze_playlist_trends(
            title, videos_block, web_context, directives=directives
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI trend analysis failed: {exc}")

    result["playlist_id"] = playlist_id
    result["playlist_title"] = title
    result["videos"] = videos
    await _set_cached(cache_key, result)
    return result


# ── Channel strategy report & content roadmap (channel-wide, Gemini 3.6 Flash + web) ───────

async def _gather_strategy_context(
    session: AsyncSession, user_id: str, time_range: str
) -> tuple[str, int, List[str]]:
    """Rich channel summary for strategy/roadmap: cadence, length buckets,
    momentum, top/bottom videos and title keywords. Returns (text, count, keywords)."""
    range_sql = _range_clause(time_range)
    range_clause = f"AND {range_sql}" if range_sql else ""
    base_where = f"WHERE LOWER(title) NOT LIKE '%private%' AND LOWER(title) NOT LIKE '%draft%' {range_clause}"

    combined_query = text(f"""
        WITH combined AS (
            SELECT video_id, title, published_at AS publish_time, duration_seconds, views,
                   ROUND((views * duration_seconds) / 3600.0, 2) AS watch_time_hours,
                   0.0 AS impressions_ctr
            FROM youtube_videos_live
            WHERE user_id = :user_id

            UNION ALL

            SELECT video_id, title, publish_time, duration_seconds, views, watch_time_hours,
                   impressions_ctr
            FROM youtube_published_videos
            WHERE user_id = :user_id
              AND video_id NOT IN (
                  SELECT video_id FROM youtube_videos_live WHERE user_id = :user_id
              )
        )
        SELECT title, publish_time, duration_seconds, views, watch_time_hours, impressions_ctr
        FROM combined
        {base_where}
    """)

    rows = [
        dict(r)
        for r in (
            await session.execute(combined_query, {"user_id": user_id})
        ).mappings().all()
    ]
    video_count = len(rows)
    if not video_count:
        return "", 0, []

    total_views = sum(r["views"] or 0 for r in rows)
    avg_views = total_views / video_count
    median_views = sorted(r["views"] or 0 for r in rows)[video_count // 2]
    avg_ctr = sum(r["impressions_ctr"] or 0 for r in rows) / video_count

    # Length buckets → avg views.
    buckets: dict[str, list[int]] = _collections.defaultdict(list)
    for r in rows:
        buckets[_duration_bucket(r["duration_seconds"])].append(r["views"] or 0)
    bucket_lines = []
    for b in ["Shorts (<=1m)", "1-5 min", "5-15 min", "15-30 min", "30+ min", "unknown"]:
        if b in buckets:
            vals = buckets[b]
            bucket_lines.append(f"  {b}: {len(vals)} videos, {int(sum(vals)/len(vals)):,} avg views")

    # Cadence. publish_time may come back as a date/datetime object (Postgres)
    # rather than a string, so normalise to ISO text before slicing.
    def _iso(v) -> str:
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    dated = sorted(
        [{**r, "publish_time": _iso(r["publish_time"])} for r in rows if r["publish_time"]],
        key=lambda r: r["publish_time"],
    )
    last_upload = dated[-1]["publish_time"][:10] if dated else "unknown"
    today = _date.today()

    def _recent(days):
        cutoff = (today - _timedelta(days=days)).isoformat()
        return sum(1 for r in dated if r["publish_time"][:10] >= cutoff)

    last_30, last_90 = _recent(30), _recent(90)

    top = sorted(rows, key=lambda r: r["views"] or 0, reverse=True)[:8]
    recent = sorted(dated, key=lambda r: r["publish_time"], reverse=True)[:8]
    keywords = _extract_keywords([r["title"] for r in rows], 8)

    from app.services.youtube_metrics import analyze_breakout_keyword_patterns, analyze_upload_timing
    timing_rows = [
        {
            "views": r.get("views") or 0,
            "published_at": _iso(r["publish_time"]),
            "video_id": r.get("video_id") or "",
            "title": r.get("title") or "",
        }
        for r in rows if r.get("publish_time")
    ]
    timing = analyze_upload_timing(timing_rows, median_views)
    best_win = timing.get("best_window")
    timing_lines = []
    if best_win and timing.get("has_timing_data"):
        timing_lines = [
            "",
            "OPTIMAL UPLOAD TIMING & SCHEDULE:",
            f"  Optimal Release Slot: {best_win.get('combined_label', '')} ({best_win.get('multiplier', 1.0)}× baseline)",
            f"  Recommendation: {best_win.get('recommendation', '')}",
            f"  Proof: {best_win.get('top_video_proof', '')}",
        ]

    lines = [
        f"OVERVIEW: {video_count} videos, {int(total_views):,} total views, "
        f"{int(avg_views):,} avg views/video, {avg_ctr:.2f}% avg CTR.",
        f"CADENCE: last upload {last_upload}; {last_30} uploads in last 30 days, "
        f"{last_90} in last 90 days.",
        *timing_lines,
        "",
        "PERFORMANCE BY VIDEO LENGTH:",
        *bucket_lines,
        "",
        "TOP VIDEOS (by views):",
        *[f"- {r['title']} — {int(r['views'] or 0):,} views, {r['impressions_ctr'] or 0:.1f}% CTR" for r in top],
        "",
        "MOST RECENT VIDEOS (momentum check):",
        *[f"- {r['publish_time'][:10]}: {r['title']} — {int(r['views'] or 0):,} views" for r in recent],
        "",
        f"RECURRING TITLE KEYWORDS: {', '.join(keywords)}",
    ]

    from app.services.youtube_competitor_context import build_competitor_block

    competitor_block = await build_competitor_block(session, user_id)
    if competitor_block:
        lines += ["", competitor_block]

    return "\n".join(lines), video_count, keywords


@router.post("/strategy")
async def generate_strategy(
    time_range: str = "all_time", refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Channel-wide strategy brief (what's working, gaps, ranked priorities)."""
    from app.services import youtube_ai_analysis

    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-strategy", time_range)
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return await _stamp_cached(session, user_id, "strategy", time_range, cached)

    context, video_count, keywords = await _gather_strategy_context(session, user_id, time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    niche = " ".join(keywords[:4]) or "youtube content"
    web_context = await _cached_web_search(f"trending YouTube video topics {niche} 2026", 6, refresh)

    directives = await get_directives(session, user_id, scope="youtube")
    try:
        result = await youtube_ai_analysis.analyze_strategy(
            context, web_context, time_range, directives=directives
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Strategy analysis failed: {exc}")

    result["time_range"] = time_range
    await _set_cached(cache_key, result)
_DAY_INT_TO_NAME = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
    4: "Friday", 5: "Saturday", 6: "Sunday",
}

_DAY_NAME_TO_INT = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def _extract_preferred_days(
    preferred_days: list[str] | list[int] | None = None,
    upload_timing: dict | None = None,
    strategy: dict | None = None,
    directives: str = "",
) -> list[int]:
    """Extract preferred upload weekdays as integers (0=Monday ... 6=Sunday)."""
    import re
    if preferred_days:
        res = []
        for d in preferred_days:
            if isinstance(d, int) and 0 <= d <= 6:
                if d not in res:
                    res.append(d)
            elif isinstance(d, str):
                val = _DAY_NAME_TO_INT.get(d.lower().strip())
                if val is not None and val not in res:
                    res.append(val)
        if res:
            return res

    # 1. From upload_timing
    if upload_timing and isinstance(upload_timing, dict):
        best_win = upload_timing.get("best_window") or {}
        b_days = best_win.get("best_days") or []
        res = []
        for d in b_days:
            val = _DAY_NAME_TO_INT.get(str(d).lower().strip())
            if val is not None and val not in res:
                res.append(val)
        if res:
            return res

        timing_days = upload_timing.get("days") or []
        sorted_days = sorted(
            [d for d in timing_days if d.get("video_count", 0) > 0],
            key=lambda x: x.get("multiplier", 1.0),
            reverse=True,
        )
        if sorted_days and sorted_days[0].get("multiplier", 1.0) >= 1.1:
            best_d = sorted_days[0].get("day")
            val = _DAY_NAME_TO_INT.get(str(best_d).lower().strip())
            if val is not None:
                return [val]

    # 2. From strategy priorities / format_insights
    if strategy and isinstance(strategy, dict):
        texts = (strategy.get("priorities") or []) + (strategy.get("format_insights") or [])
        combined = " ".join(str(t) for t in texts).lower()
        if "weekend" in combined or "saturday or sunday" in combined or "saturday / sunday" in combined:
            return [5, 6]

        found = []
        for word in ["saturday", "sunday", "friday", "thursday", "wednesday", "tuesday", "monday"]:
            if re.search(rf"\b{word}\b", combined):
                val = _DAY_NAME_TO_INT[word]
                if val not in found:
                    found.append(val)
        if found:
            return found

    # 3. Directives scan
    if directives:
        lowered = directives.lower()
        if "weekend" in lowered:
            return [5, 6]
        found = []
        for word in ["saturday", "sunday", "friday", "thursday", "wednesday", "tuesday", "monday"]:
            if re.search(rf"\b{word}\b", lowered):
                val = _DAY_NAME_TO_INT[word]
                if val not in found:
                    found.append(val)
        if found:
            return found

    return []


def _assign_roadmap_dates(
    weeks: list,
    start: _date,
    preferred_days: list[str] | list[int] | None = None,
    upload_timing: dict | None = None,
    strategy: dict | None = None,
    directives: str = "",
) -> list:
    """Spread each week's items across that week starting from `start`, aligned with optimal upload days."""
    resolved_days = _extract_preferred_days(preferred_days, upload_timing, strategy, directives)

    # No fallback to ``start.weekday()``. That is the weekday the report happened
    # to be generated on — it is how a plan whose header said "published
    # Saturdays" ended up carrying four Tuesday dates. With no measured signal the
    # items simply carry no date, and the renderer omits the publishing-day claim
    # rather than inventing one.
    if not resolved_days:
        for wi, week in enumerate(weeks):
            week["week_number"] = wi + 1
            week.pop("start_date", None)
            for item in week.get("items", []) or []:
                item.pop("date", None)
        return weeks

    primary_day = resolved_days[0]

    # Find the first target release date on or after `start`
    days_to_first = (primary_day - start.weekday()) % 7
    first_release_date = start + _timedelta(days=days_to_first)

    for wi, week in enumerate(weeks):
        week_anchor = first_release_date + _timedelta(days=wi * 7)
        items = week.get("items", []) or []
        item_count = len(items)

        if item_count == 0:
            week["week_number"] = wi + 1
            week["start_date"] = week_anchor.isoformat()
            continue

        item_dates = []
        if len(resolved_days) >= item_count:
            for ii in range(item_count):
                day_offset = (resolved_days[ii] - primary_day) % 7
                item_dates.append(week_anchor + _timedelta(days=day_offset))
        else:
            step = max(1, 7 // item_count)
            for ii in range(item_count):
                if ii < len(resolved_days):
                    day_offset = (resolved_days[ii] - primary_day) % 7
                    item_dates.append(week_anchor + _timedelta(days=day_offset))
                else:
                    item_dates.append(week_anchor + _timedelta(days=min(6, ii * step)))

        for ii, item in enumerate(items):
            item["date"] = item_dates[ii].isoformat()

        week["week_number"] = wi + 1
        week["start_date"] = item_dates[0].isoformat()

    # Assert what was just built. Every date must land on a day the plan actually
    # recommends; anything else is a date the header contradicts.
    allowed = set(resolved_days)
    for week in weeks:
        for item in week.get("items", []) or []:
            iso = item.get("date")
            if not iso:
                continue
            if _date.fromisoformat(iso).weekday() not in allowed:
                logger.warning(
                    "roadmap date %s is a %s but the plan publishes on %s; dropping it",
                    iso,
                    _DAY_INT_TO_NAME.get(_date.fromisoformat(iso).weekday(), "?"),
                    ", ".join(_DAY_INT_TO_NAME.get(d, "?") for d in resolved_days),
                )
                item.pop("date", None)

    return weeks


@router.post("/roadmap")
async def generate_content_roadmap(
    time_range: str = "all_time", weeks: int = 4, refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """A multi-week posting roadmap across the channel's themes, with dates."""
    from app.services import youtube_ai_analysis

    user_id = user["id"]
    weeks = max(1, min(weeks, 8))
    cache_key = await _domain_key(user_id, "yt-roadmap", time_range, str(weeks))
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return await _stamp_cached(session, user_id, "roadmap", time_range, cached)

    context, video_count, keywords = await _gather_strategy_context(session, user_id, time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    niche = " ".join(keywords[:4]) or "youtube content"
    web_context = await _cached_web_search(f"trending YouTube video ideas {niche} 2026", 6, refresh)

    # Check if a strategy analysis was cached to pass into roadmap for topic/framing coherence
    strategy_cache_key = await _domain_key(user_id, "yt-strategy", time_range)
    saved_strategy = await _get_cached(strategy_cache_key)

    directives = await get_directives(session, user_id, scope="youtube")
    try:
        result = await youtube_ai_analysis.generate_roadmap(
            context, web_context, weeks, directives=directives, audit_strategy=saved_strategy
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Roadmap generation failed: {exc}")

    result["weeks"] = _assign_roadmap_dates(
        result.get("weeks", []), _date.today(), strategy=saved_strategy, directives=directives
    )
    result["time_range"] = time_range
    await _set_cached(cache_key, result)
    return await _save_analysis(session, user_id, "roadmap", time_range, result, weeks=weeks)


# ── Roadmap → planner ─────────────────────────────────────────────────────────
#
# A roadmap item already carries a title, format, theme and a rough date; what
# it lacks is a real schedule. app.services.roadmap_to_plan supplies that from
# the channel's own publish history. This is the YouTube counterpart of
# POST /api/instagram-analytics/roadmap/add-to-plan, and shares its scheduler.


class RoadmapItemIn(BaseModel):
    title: str
    format: str = ""
    theme: str = ""
    rationale: str = ""
    date: str | None = None
    week_number: int | None = None


class RoadmapAddToPlanBody(BaseModel):
    items: List[RoadmapItemIn]
    # Append into an existing plan, or create a new one when omitted.
    plan_id: str | None = None
    plan_name: str | None = None
    # False keeps the roadmap's own dates instead of the channel's best weekdays.
    strategic: bool = True


@router.post("/roadmap/add-to-plan")
async def add_roadmap_to_plan(
    body: RoadmapAddToPlanBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Schedule roadmap items into the content planner.

    Items already in the plan or already published are skipped rather than
    duplicated; the caller gets the reasons back so the UI can explain itself.
    """
    if not body.items:
        raise HTTPException(status_code=400, detail="No items to add.")

    user_id = user["id"]

    if body.plan_id:
        plan = await queries.get_content_plan_by_id(session, body.plan_id, user_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        existing = await queries.get_plan_items(session, plan["id"], user_id)
    else:
        plan, existing = None, []

    raw_items = [item.model_dump() for item in body.items]

    # schedule_items() reads the publish history through a *sync* session and
    # the sqlite content tracker, so it must not run on the event loop.
    scheduled, skipped, profile = await asyncio.to_thread(
        roadmap_to_plan.schedule_items, user_id, raw_items, existing, body.strategic
    )

    if not scheduled:
        return {
            "plan_id": plan["id"] if plan else None,
            "created": [],
            "skipped": skipped,
            "profile": profile,
        }

    if plan is None:
        dates = sorted(item["publish_date"] for item in scheduled)
        plan = await queries.create_content_plan(
            session,
            user_id,
            body.plan_name or f"Roadmap — {_date.today().isoformat()}",
            "monthly",
            "ai",
            min(item["scheduled_date"] for item in scheduled),
            dates[-1],
            platform="youtube",
        )

    created = [
        await queries.create_plan_item(session, plan["id"], user_id, **item)
        for item in scheduled
    ]

    return {
        "plan_id": plan["id"],
        "created": created,
        "skipped": skipped,
        "profile": profile,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Live YouTube Sync Endpoints (YouTube Data API v3 → youtube_videos_live)
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/sync-live")
async def sync_live_videos(user: dict = Depends(get_current_user)) -> dict:
    """
    Trigger a full sync from YouTube Data API v3 for the current user.
    Fetches ALL channel videos, upserts metadata + metrics into
    youtube_videos_live, and invalidates this user's cached analytics.
    """
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_sync_service import (
        YoutubeApiDisabled,
        YoutubeScopeMissing,
        YoutubeSyncError,
        sync_all_videos,
    )

    user_id = user["id"]
    try:
        # Paginated googleapiclient calls + a batch of upserts — off the loop.
        # This can run for minutes on a full-channel sync; Phase 4 moves it to
        # a Celery job so it survives Cloudflare's ~100s proxy timeout.
        result = await asyncio.to_thread(sync_all_videos, user_id)
    except NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeScopeMissing as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except YoutubeApiDisabled as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await _flush_live_cache(user_id)
    return result


@router.post("/sync-analytics")
async def sync_video_analytics_route(user: dict = Depends(get_current_user)) -> dict:
    """
    Pull real impressions/CTR/retention from the YouTube Analytics API
    (separate scope from /sync-live's Data API sync) and write them onto the
    matching youtube_videos_live rows. Run /sync-live first so there are local
    rows to match against.
    """
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_sync_service import (
        YoutubeAnalyticsScopeMissing,
        YoutubeApiDisabled,
        YoutubeSyncError,
        sync_video_analytics,
    )

    user_id = user["id"]
    try:
        result = await asyncio.to_thread(sync_video_analytics, user_id)
    except NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeAnalyticsScopeMissing as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except YoutubeApiDisabled as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await _flush_live_cache(user_id)
    return result


@router.get("/achievements")
async def get_achievements(
    refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Milestone achievements for the connected channel.

    Every figure is measured or null — see youtube_achievements_service. The
    response carries a ``basis`` telling the client whether the history behind
    the dates is a real monthly series or publish-date attribution, so an
    approximation is never rendered as an exact claim.
    """
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-achievements")
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return cached

    from app.services.youtube_achievements_service import build_achievements

    result = await build_achievements(session, user_id)
    await _set_cached(cache_key, result)
    return result


@router.get("/sync-status")
async def get_sync_status(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the last sync timestamp and total live video count for this user."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-live-sync-status")
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    row = (
        await session.execute(
            text(
                "SELECT MAX(fetched_at) AS last_synced, COUNT(*) AS total "
                "FROM youtube_videos_live WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    result = dict(row) if row else {"last_synced": None, "total": 0}

    await _set_cached(cache_key, result)
    return result


@router.get("/live-videos")
async def get_live_videos(
    limit: int = 24,
    offset: int = 0,
    sort_by: str = "published_at",
    order: str = "desc",
    search: str = "",
    status: str = "",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Paginated list of the current user's videos from youtube_videos_live.
    Cached for 5 minutes per unique query.

    sort_by: published_at | views | likes | comments | seo_title_score
    order: asc | desc
    search: optional title/tag text filter
    status: optional status filter (public | unlisted | private | scheduled)
    """
    user_id = user["id"]
    valid_sort = {"published_at", "views", "likes", "comments", "seo_title_score", "duration_seconds"}
    if sort_by not in valid_sort:
        sort_by = "published_at"
    order_sql = "ASC" if order.upper() == "ASC" else "DESC"

    cache_key = await _domain_key(
        user_id, "yt-live", sort_by, order_sql, str(limit), str(offset), search, status
    )
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    where_clauses = ["user_id = :user_id"]
    params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}

    if search:
        where_clauses.append("(title ILIKE :search OR tags::text ILIKE :search)")
        params["search"] = f"%{search}%"

    if status:
        st_lower = status.lower()
        if st_lower == "scheduled":
            where_clauses.append("is_scheduled = TRUE")
        elif st_lower in ("public", "unlisted", "private"):
            where_clauses.append("privacy_status = :status")
            params["status"] = st_lower

    where_sql = "WHERE " + " AND ".join(where_clauses)

    total_row = (
        await session.execute(
            text(f"SELECT COUNT(*) AS cnt FROM youtube_videos_live {where_sql}"), params
        )
    ).mappings().first()
    total = total_row["cnt"] if total_row else 0

    rows = (
        await session.execute(
            text(f"""
                SELECT video_id, title, description, tags, category_id,
                       duration_seconds, published_at, thumbnail_url,
                       views, likes, comments,
                       channel_id, channel_title,
                       seo_title_score, seo_tag_count, seo_desc_words,
                       privacy_status, is_scheduled, publish_at,
                       fetched_at,
                       impressions, impressions_ctr,
                       average_view_duration_seconds, average_view_percentage,
                       analytics_synced_at
                FROM youtube_videos_live
                {where_sql}
                ORDER BY {sort_by} {order_sql}
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
    ).mappings().all()

    # tags is JSONB — already a Python list, no json.loads needed.
    videos = [dict(r) for r in rows]

    result = {"total": total, "limit": limit, "offset": offset, "videos": videos}
    await _set_cached(cache_key, result)
    return result


@router.get("/live-video/{video_id}")
async def get_live_video(
    video_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Single video detail with full metadata + SEO breakdown, for the current user.
    Cached for 5 minutes.
    """
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-live-video", video_id)
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    row = (
        await session.execute(
            text(
                "SELECT * FROM youtube_videos_live WHERE user_id = :user_id AND video_id = :video_id"
            ),
            {"user_id": user_id, "video_id": video_id},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Video not found in live sync data.")

    v = dict(row)

    # SEO suggestions
    suggestions = []
    if v["seo_title_score"] < 60:
        title_len = len(v.get("title", ""))
        if title_len < 40:
            suggestions.append(f"Title is short ({title_len} chars). Aim for 40-70 characters.")
        elif title_len > 70:
            suggestions.append(f"Title is long ({title_len} chars). Consider trimming to under 70 characters.")
        if not any(c.isdigit() for c in v.get("title", "")):
            suggestions.append("Add a number to your title for better CTR (e.g. '5 Ways', 'in 10 Minutes').")
    if v["seo_tag_count"] < 5:
        suggestions.append(f"Only {v['seo_tag_count']} tags. Add at least 5-15 tags to improve discoverability.")
    elif v["seo_tag_count"] > 15:
        suggestions.append("You have many tags. YouTube recommends keeping it focused (5-15 relevant tags).")
    if v["seo_desc_words"] < 150:
        suggestions.append(f"Description is short ({v['seo_desc_words']} words). A 150-300 word description with keywords helps SEO.")

    v["seo_suggestions"] = suggestions
    v["youtube_url"] = f"https://www.youtube.com/watch?v={video_id}"

    await _set_cached(cache_key, v)
    return v


def _format_video_growth_context(v: dict) -> str:
    """Compact, honest context for the growth-recommendations prompt.

    Never fabricates a CTR number — reports real Analytics-API data only when
    analytics_synced_at is set, otherwise says so explicitly.
    """
    published_at = v.get("published_at")
    days_live = "unknown"
    if published_at:
        try:
            published_dt = published_at if isinstance(published_at, datetime) else datetime.fromisoformat(str(published_at))
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)
            days_live = (datetime.now(timezone.utc) - published_dt).days
        except Exception:
            days_live = "unknown"

    if v.get("analytics_synced_at"):
        ctr_block = (
            f"Impressions: {v.get('impressions', 0)}\n"
            f"CTR: {round((v.get('impressions_ctr') or 0) * 100, 2)}%\n"
            f"Average % of video viewed: {round(v.get('average_view_percentage') or 0, 1)}%\n"
            f"Average view duration: {v.get('average_view_duration_seconds', 0)}s"
        )
    else:
        ctr_block = "CTR not synced — reason from title/tags/description/format instead of a CTR number."

    tags = v.get("tags") or []
    return (
        f"Title: {v.get('title', '')}\n"
        f"Published: {days_live} days ago\n"
        f"Duration: {v.get('duration_seconds', 0)}s\n"
        f"Views: {v.get('views', 0)} | Likes: {v.get('likes', 0)} | Comments: {v.get('comments', 0)}\n"
        f"{ctr_block}\n"
        f"SEO title score: {v.get('seo_title_score', 0)}/100 | Tag count: {v.get('seo_tag_count', 0)} | "
        f"Description words: {v.get('seo_desc_words', 0)}\n"
        f"Tags: {', '.join(tags) if tags else '(none)'}\n"
        f"Description: {(v.get('description') or '')[:500]}"
    )


@router.post("/live-video/{video_id}/growth-recommendations")
async def get_video_growth_recommendations(
    video_id: str,
    refresh: bool = False,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """AI recommendations to grow views/CTR for ONE video — title/thumbnail/hook/
    tag fixes, grounded in this video's real stats (real CTR when synced, else
    honestly flagged as not synced) plus live web trends. Cached for 5 minutes."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-video-growth", video_id)
    if not refresh:
        cached = await _get_cached(cache_key)
        if cached:
            return cached

    row = (
        await session.execute(
            text(
                "SELECT * FROM youtube_videos_live WHERE user_id = :user_id AND video_id = :video_id"
            ),
            {"user_id": user_id, "video_id": video_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found in live sync data.")

    v = dict(row)
    video_context = _format_video_growth_context(v)

    from app.services.youtube_competitor_context import build_topic_overlap_block

    overlap_block = await build_topic_overlap_block(session, user_id, v.get("title", ""))
    if overlap_block:
        video_context = f"{video_context}\n\n{overlap_block}"

    try:
        web_context = await _cached_web_search(
            f"trending YouTube video titles thumbnails ideas {v.get('title', '')[:60]} 2026", 6, refresh
        )
    except Exception as exc:
        logger.warning("Web research failed for video growth recommendations: %s", exc)
        web_context = ""

    from app.services import youtube_ai_analysis

    directives = await get_directives(session, user_id, scope="youtube")
    try:
        result = await youtube_ai_analysis.analyze_video_growth(
            video_context, web_context, directives=directives
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI growth analysis failed: {exc}")

    result["video_id"] = video_id
    await _set_cached(cache_key, result)
    return result


class VideoMetadataUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    category_id: str | None = None


@router.post("/live-video/{video_id}/update-metadata")
async def update_video_metadata_route(
    video_id: str,
    payload: VideoMetadataUpdateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """1-Click update of YouTube video title, description, and tags directly to YouTube."""
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_sync_service import (
        YoutubeApiDisabled,
        YoutubeScopeMissing,
        YoutubeSyncError,
        update_video_metadata,
    )

    user_id = user["id"]
    try:
        result = await asyncio.to_thread(
            update_video_metadata,
            user_id=user_id,
            video_id=video_id,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            category_id=payload.category_id,
        )
    except NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeScopeMissing as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except YoutubeApiDisabled as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    await _flush_live_cache(user_id)
    return result


# ── YouTube Reporting API & Audience Insights ────────────────────────────────


@router.get("/audience-insights")
async def get_audience_insights_route(
    days: int = 90,
    user: dict = Depends(get_current_user),
) -> dict:
    """Breakdown of device types, operating systems, viewer demographics, and geography."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-audience-insights", str(days))
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    from app.services.youtube_sync_service import get_audience_insights

    insights = await asyncio.to_thread(get_audience_insights, user_id, days)
    await _set_cached(cache_key, insights, ttl=600)
    return insights


@router.get("/reporting/jobs")
async def get_reporting_jobs(
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """List all scheduled bulk reporting jobs from YouTube Reporting API."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-reporting", "jobs")
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached

    from app.services.youtube_reporting_service import list_reporting_jobs

    jobs = await asyncio.to_thread(list_reporting_jobs, user_id)
    await _set_cached(cache_key, jobs, ttl=600)
    return jobs


@router.post("/reporting/setup")
async def setup_reporting_jobs(
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """Ensure standard reporting jobs are scheduled on YouTube Reporting API."""
    user_id = user["id"]
    from app.services.youtube_reporting_service import ensure_default_jobs

    res = await asyncio.to_thread(ensure_default_jobs, user_id)
    await _flush_live_cache(user_id)
    return res


@router.get("/reporting/reports")
async def get_available_reports(
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """List all available generated bulk reports from YouTube Reporting API."""
    user_id = user["id"]
    cache_key = await _domain_key(user_id, "yt-reporting", "reports")
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached

    from app.services.youtube_reporting_service import list_available_reports

    reports = await asyncio.to_thread(list_available_reports, user_id)
    await _set_cached(cache_key, reports, ttl=600)
    return reports


@router.post("/reporting/sync")
async def sync_reporting_data(
    user: dict = Depends(get_current_user),
) -> dict:
    """Download and ingest available bulk CSV reports from YouTube Reporting API."""
    user_id = user["id"]
    from app.services.youtube_reporting_service import download_and_ingest_reports

    res = await asyncio.to_thread(download_and_ingest_reports, user_id)
    await _flush_live_cache(user_id)
    return res
