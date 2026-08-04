import asyncio
import json
import logging
import redis
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.db.database import get_db, dict_from_row
from app.db.models import YoutubePublishedVideo, YoutubeTrafficSource
from app.services.youtube_import import import_youtube_data
from app.core.auth_deps import get_current_user
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube-analytics", tags=["YouTube Analytics"])

# All YouTube analytics data (stats, videos, playlists, AI analysis, web search)
# is cached in Redis for 5 minutes.
CACHE_TTL_SECONDS = 300

try:
    redis_client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
except Exception:
    redis_client = None


@router.post("/import")
def trigger_youtube_import():
    """Trigger the YouTube CSV data import process"""
    result = import_youtube_data()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    if redis_client:
        keys = redis_client.keys("yt:*")
        if keys:
            redis_client.delete(*keys)
            
    return result


def get_filter_clause(time_range: str) -> tuple[str, list]:
    conditions = ["LOWER(title) NOT LIKE '%private%'", "LOWER(title) NOT LIKE '%draft%'"]
    params = []
    
    if time_range == "7_days":
        conditions.append("publish_time >= date('now', '-7 days')")
    elif time_range == "30_days":
        conditions.append("publish_time >= date('now', '-30 days')")
    elif time_range == "90_days":
        conditions.append("publish_time >= date('now', '-90 days')")
    elif time_range == "1_year":
        conditions.append("publish_time >= date('now', '-365 days')")
        
    return " WHERE " + " AND ".join(conditions), params

@router.get("/videos", response_model=List[YoutubePublishedVideo])
def get_youtube_videos(limit: int = 50, offset: int = 0, sort_by: str = "views", time_range: str = "all_time"):
    """Get published YouTube videos, sorted by views or publish_time"""
    cache_key = f"yt:videos:{time_range}:{sort_by}:{limit}:{offset}"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()
    
    # Validate sort parameter to prevent SQL injection
    valid_sort_columns = {"views", "publish_time", "duration_seconds", "watch_time_hours"}
    if sort_by not in valid_sort_columns:
        sort_by = "views"
        
    order = "DESC"
    
    where_clause, params = get_filter_clause(time_range)
    
    query = f"""
        SELECT * FROM youtube_published_videos 
        {where_clause}
        ORDER BY {sort_by} {order}
        LIMIT ? OFFSET ?
    """
    
    cursor.execute(query, params + [limit, offset])
    rows = cursor.fetchall()
    
    result = [dict_from_row(r) for r in rows]
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
            
    return [YoutubePublishedVideo(**r) for r in result]

@router.get("/traffic-sources", response_model=List[YoutubeTrafficSource])
def get_traffic_sources():
    """Get YouTube traffic sources, sorted by views"""
    cache_key = "yt:traffic_sources"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM youtube_traffic_sources 
        ORDER BY views DESC
    """)
    rows = cursor.fetchall()
    
    result = [dict_from_row(r) for r in rows]
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
            
    return [YoutubeTrafficSource(**r) for r in result]

@router.get("/stats")
def get_youtube_overall_stats(time_range: str = "all_time") -> Dict[str, Any]:
    """Get aggregate statistics for the channel"""
    cache_key = f"yt:stats:{time_range}"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()
    
    where_clause, params = get_filter_clause(time_range)
    
    query = f"""
        SELECT 
            COUNT(video_id) as total_videos,
            SUM(views) as total_views,
            SUM(watch_time_hours) as total_watch_time,
            SUM(subscribers) as total_subscribers,
            SUM(impressions) as total_impressions
        FROM youtube_published_videos
        {where_clause}
    """
    cursor.execute(query, params)
    row = cursor.fetchone()
    if not row:
        result_data = {}
    else:
        result_data = dict_from_row(row)
        
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result_data))
        except Exception:
            pass

    return result_data


def _gather_channel_context(time_range: str) -> tuple[str, int]:
    """Build a compact, human-readable summary of the channel's data for the LLM.

    Returns (context_text, video_count). video_count is used to short-circuit the
    AI call when there is nothing to analyze.
    """
    conn = get_db()
    where_clause, params = get_filter_clause(time_range)

    overall = dict_from_row(
        conn.execute(
            f"SELECT COUNT(video_id) AS videos, COALESCE(SUM(views),0) AS views, "
            f"COALESCE(SUM(watch_time_hours),0) AS watch_time, "
            f"COALESCE(SUM(impressions),0) AS impressions, "
            f"COALESCE(AVG(impressions_ctr),0) AS avg_ctr "
            f"FROM youtube_published_videos {where_clause}",
            params,
        ).fetchone()
    )

    video_count = overall.get("videos", 0) or 0
    if not video_count:
        return "", 0

    top = [
        dict_from_row(r)
        for r in conn.execute(
            f"SELECT title, views, watch_time_hours, impressions_ctr "
            f"FROM youtube_published_videos {where_clause} ORDER BY views DESC LIMIT 8",
            params,
        ).fetchall()
    ]
    low = [
        dict_from_row(r)
        for r in conn.execute(
            f"SELECT title, views, watch_time_hours, impressions_ctr "
            f"FROM youtube_published_videos {where_clause} ORDER BY views ASC LIMIT 5",
            params,
        ).fetchall()
    ]
    traffic = [
        dict_from_row(r)
        for r in conn.execute(
            "SELECT traffic_source, views, impressions_ctr "
            "FROM youtube_traffic_sources ORDER BY views DESC LIMIT 12"
        ).fetchall()
    ]

    lines = [
        f"OVERVIEW: {overall['videos']} videos, {int(overall['views']):,} total views, "
        f"{overall['watch_time']:.0f} watch-hours, {int(overall['impressions']):,} impressions, "
        f"{overall['avg_ctr']:.2f}% average CTR.",
        "",
        "TOP VIDEOS (by views):",
    ]
    for v in top:
        lines.append(
            f"- {v['title']} — {int(v['views']):,} views, {v['watch_time_hours']:.0f} watch-hrs, "
            f"{v['impressions_ctr']:.1f}% CTR"
        )
    lines += ["", "LOWEST-VIEW VIDEOS:"]
    for v in low:
        lines.append(
            f"- {v['title']} — {int(v['views']):,} views, {v['impressions_ctr']:.1f}% CTR"
        )
    lines += ["", "TRAFFIC SOURCES (by views):"]
    for t in traffic:
        lines.append(
            f"- {t['traffic_source']}: {int(t['views']):,} views, {t['impressions_ctr']:.1f}% CTR"
        )

    return "\n".join(lines), video_count


@router.post("/ai-analysis")
async def generate_ai_analysis(time_range: str = "all_time", refresh: bool = False) -> Dict[str, Any]:
    """Generate an AI (Ollama qwen) strategic analysis of the channel's performance."""
    cache_key = f"yt:ai_analysis:{time_range}"
    if redis_client and not refresh:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    context, video_count = _gather_channel_context(time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    # Imported lazily so crewai/LLM deps don't load unless AI analysis is requested.
    from app.services import youtube_ai_analysis

    try:
        result = await youtube_ai_analysis.analyze_channel(context, time_range=time_range)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")

    result["time_range"] = time_range
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
    return result


# ── Playlist-wise latest videos & trending topics (YouTube Data API + qwen) ────


def _map_youtube_error(exc: Exception) -> HTTPException:
    """Translate youtube_data / google_calendar errors into clean HTTP responses."""
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_data import (
        YoutubeScopeError,
        YoutubeApiDisabledError,
        YoutubeDataError,
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
def get_playlists(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """List the connected channel's playlists plus its uploads playlist id."""
    from app.services import youtube_data

    cache_key = f"yt:playlists:{user['id']}"
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        overview = youtube_data.get_channel_overview(user["id"])
        playlists = youtube_data.list_playlists(user["id"])
    except Exception as exc:
        raise _map_youtube_error(exc)

    result = {**overview, "playlists": playlists}
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
    return result


@router.get("/playlist-videos")
def get_playlist_videos(
    playlist_id: str, limit: int = 10, user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Latest videos in a playlist (or the uploads playlist), enriched with metrics."""
    from app.services import youtube_data

    cache_key = f"yt:playlist_videos:{user['id']}:{playlist_id}:{limit}"
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        videos = youtube_data.list_playlist_videos(user["id"], playlist_id, max_results=limit)
    except Exception as exc:
        raise _map_youtube_error(exc)

    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(videos))
        except Exception:
            pass
    return videos


def _cached_web_search(query: str, max_results: int = 6, bypass: bool = False) -> str:
    """Run the multi-source web search, caching raw results in Redis for 5 min."""
    from app.tools.custom import run_web_search

    cache_key = f"yt:websearch:{query}"
    if redis_client and not bypass:
        try:
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass

    result = run_web_search(query, max_results)
    if redis_client and result:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, result)
        except Exception:
            pass
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
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Trending next-video topics for one playlist: its latest videos + live web
    research, synthesized by the local qwen model."""
    from app.services import youtube_data, youtube_ai_analysis

    cache_key = f"yt:playlist_trends:{playlist_id}"
    if redis_client and not refresh:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    try:
        videos = youtube_data.list_playlist_videos(user["id"], playlist_id, max_results=8)
    except Exception as exc:
        raise _map_youtube_error(exc)

    title = playlist_title or "this playlist"
    videos_block = _format_videos_block(videos)

    # Live web trends for the playlist's theme (best-effort — never fatal).
    # Cached 5 min; a refresh bypasses the search cache too.
    try:
        web_context = await asyncio.to_thread(
            _cached_web_search, f"latest trending YouTube video topics {title} 2026", 6, refresh
        )
    except Exception as exc:
        logger.warning("Web research failed for playlist trends: %s", exc)
        web_context = ""

    try:
        result = await youtube_ai_analysis.analyze_playlist_trends(title, videos_block, web_context)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI trend analysis failed: {exc}")

    result["playlist_id"] = playlist_id
    result["playlist_title"] = title
    result["videos"] = videos
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
    return result


# ── Channel strategy report & content roadmap (channel-wide, qwen + web) ───────

import re as _re
import collections as _collections
from datetime import date as _date, timedelta as _timedelta

_STOPWORDS = set(
    "the a an and or of to for with your you how what why when who in on at is are be "
    "this that these those from into your my our it its as vs your best top new using use "
    "part full free real make made build built guide tutorial video || coding india".split()
)


def _extract_keywords(titles: List[str], n: int = 6) -> List[str]:
    """Most frequent meaningful words across video titles (for niche/search)."""
    counter: _collections.Counter = _collections.Counter()
    for t in titles:
        for w in _re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]{2,}", (t or "").lower()):
            if w in _STOPWORDS or len(w) < 3:
                continue
            counter[w] += 1
    return [w for w, _ in counter.most_common(n)]


def _duration_bucket(seconds) -> str:
    s = seconds or 0
    if s <= 0:
        return "unknown"
    if s <= 60:
        return "Shorts (<=1m)"
    if s <= 300:
        return "1-5 min"
    if s <= 900:
        return "5-15 min"
    if s <= 1800:
        return "15-30 min"
    return "30+ min"


def _gather_strategy_context(time_range: str) -> tuple[str, int, List[str]]:
    """Rich channel summary for strategy/roadmap: cadence, length buckets,
    momentum, top/bottom videos and title keywords. Returns (text, count, keywords)."""
    conn = get_db()
    where_clause, params = get_filter_clause(time_range)

    rows = [
        dict_from_row(r)
        for r in conn.execute(
            f"SELECT title, publish_time, duration_seconds, views, watch_time_hours, impressions_ctr "
            f"FROM youtube_published_videos {where_clause}",
            params,
        ).fetchall()
    ]
    video_count = len(rows)
    if not video_count:
        return "", 0, []

    total_views = sum(r["views"] or 0 for r in rows)
    avg_views = total_views / video_count
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

    # Cadence.
    dated = sorted([r for r in rows if r["publish_time"]], key=lambda r: r["publish_time"])
    last_upload = dated[-1]["publish_time"][:10] if dated else "unknown"
    today = _date.today()
    def _recent(days):
        cutoff = (today - _timedelta(days=days)).isoformat()
        return sum(1 for r in dated if r["publish_time"][:10] >= cutoff)
    last_30, last_90 = _recent(30), _recent(90)

    top = sorted(rows, key=lambda r: r["views"] or 0, reverse=True)[:8]
    recent = sorted(dated, key=lambda r: r["publish_time"], reverse=True)[:8]
    keywords = _extract_keywords([r["title"] for r in rows], 8)

    lines = [
        f"OVERVIEW: {video_count} videos, {int(total_views):,} total views, "
        f"{int(avg_views):,} avg views/video, {avg_ctr:.2f}% avg CTR.",
        f"CADENCE: last upload {last_upload}; {last_30} uploads in last 30 days, "
        f"{last_90} in last 90 days.",
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
    return "\n".join(lines), video_count, keywords


@router.post("/strategy")
async def generate_strategy(time_range: str = "all_time", refresh: bool = False) -> Dict[str, Any]:
    """Channel-wide strategy brief (what's working, gaps, ranked priorities)."""
    from app.services import youtube_ai_analysis

    cache_key = f"yt:strategy:{time_range}"
    if redis_client and not refresh:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    context, video_count, keywords = _gather_strategy_context(time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    niche = " ".join(keywords[:4]) or "youtube content"
    web_context = await asyncio.to_thread(
        _cached_web_search, f"trending YouTube video topics {niche} 2026", 6, refresh
    )

    try:
        result = await youtube_ai_analysis.analyze_strategy(context, web_context, time_range)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Strategy analysis failed: {exc}")

    result["time_range"] = time_range
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
    return result


def _assign_roadmap_dates(weeks: list, start: _date) -> list:
    """Spread each week's items across that week starting from `start`."""
    for wi, week in enumerate(weeks):
        week_start = start + _timedelta(days=wi * 7)
        items = week.get("items", []) or []
        step = max(1, 7 // max(1, len(items)))
        for ii, item in enumerate(items):
            item["date"] = (week_start + _timedelta(days=min(6, ii * step))).isoformat()
        week["week_number"] = wi + 1
        week["start_date"] = week_start.isoformat()
    return weeks


@router.post("/roadmap")
async def generate_content_roadmap(
    time_range: str = "all_time", weeks: int = 4, refresh: bool = False
) -> Dict[str, Any]:
    """A multi-week posting roadmap across the channel's themes, with dates."""
    from app.services import youtube_ai_analysis

    weeks = max(1, min(weeks, 8))
    cache_key = f"yt:roadmap:{time_range}:{weeks}"
    if redis_client and not refresh:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    context, video_count, keywords = _gather_strategy_context(time_range)
    if not video_count:
        raise HTTPException(status_code=404, detail="No YouTube data to analyze. Import data first.")

    niche = " ".join(keywords[:4]) or "youtube content"
    web_context = await asyncio.to_thread(
        _cached_web_search, f"trending YouTube video ideas {niche} 2026", 6, refresh
    )

    try:
        result = await youtube_ai_analysis.generate_roadmap(context, web_context, weeks)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Roadmap generation failed: {exc}")

    result["weeks"] = _assign_roadmap_dates(result.get("weeks", []), _date.today())
    result["time_range"] = time_range
    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass
    return result
