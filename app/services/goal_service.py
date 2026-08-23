"""
Goal progress — reads a tracked metric from the user's synced YouTube data and
turns a ``user_goals`` row into a progress-annotated dict the dashboard and the
LLM prompts both consume.

Progress is computed lazily on read (the same pattern
``plan_service.reconcile_plan_item_content`` uses for plan items): no
background job, just a cheap query — or, for ``subscribers``, one cached
YouTube API call — each time a goal is fetched.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from googleapiclient.errors import HttpError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import acache, uk
from app.services.youtube_data import _service, _wrap_http_error

logger = logging.getLogger(__name__)

_OWN_STATS_TTL = 300  # seconds — matches the app-wide analysis cache TTL


def get_own_channel_stats(user_id: str) -> dict:
    """Live channel-level stats for the connected account. 1 quota unit."""
    yt = _service(user_id)
    try:
        resp = yt.channels().list(part="statistics", mine=True).execute()
    except HttpError as exc:
        raise _wrap_http_error(exc)
    items = resp.get("items", [])
    if not items:
        return {}
    stats = items[0].get("statistics", {})
    return {
        "subscriber_count": int(stats.get("subscriberCount", 0) or 0),
        "view_count": int(stats.get("viewCount", 0) or 0),
        "video_count": int(stats.get("videoCount", 0) or 0),
    }


async def _cached_own_channel_stats(user_id: str) -> dict:
    cache_key = uk(user_id, "yt-own-stats")
    try:
        raw = await acache().get(cache_key)
        if raw:
            import json

            return json.loads(raw)
    except Exception:
        pass

    try:
        stats = await asyncio.to_thread(get_own_channel_stats, user_id)
    except Exception as exc:
        logger.info("goal_service: could not fetch own channel stats for %s: %s", user_id, exc)
        return {}

    try:
        import json

        await acache().setex(cache_key, _OWN_STATS_TTL, json.dumps(stats))
    except Exception:
        pass
    return stats


async def read_metric(
    session: AsyncSession, user_id: str, metric: str, start_date=None
) -> tuple[float | None, str]:
    """Current value for ``metric``. Returns (value, note); value is None when
    the data isn't available (never a fabricated 0 — same honesty rule the
    video-growth prompt uses for un-synced CTR)."""
    if metric == "subscribers":
        stats = await _cached_own_channel_stats(user_id)
        if "subscriber_count" not in stats:
            return None, "YouTube not connected or stats unavailable"
        return float(stats["subscriber_count"]), "live"

    if metric == "views":
        stats = await _cached_own_channel_stats(user_id)
        if "view_count" in stats:
            return float(stats["view_count"]), "live"
        return None, "YouTube not connected"

    where_since = "AND published_at >= :start_date" if start_date else ""
    if metric == "videos_published":
        row = (
            await session.execute(
                text(
                    f"SELECT COUNT(*) AS n FROM youtube_videos_live "
                    f"WHERE user_id = :user_id AND privacy_status = 'public' {where_since}"
                ),
                {"user_id": user_id, "start_date": start_date},
            )
        ).mappings().first()
        return float((row or {}).get("n", 0) or 0), "synced"

    if metric == "watch_hours":
        where = "AND publish_time >= :start_date" if start_date else ""
        row = (
            await session.execute(
                text(
                    f"SELECT COALESCE(SUM(watch_time_hours), 0) AS n "
                    f"FROM youtube_published_videos WHERE user_id = :user_id {where}"
                ),
                {"user_id": user_id, "start_date": start_date},
            )
        ).mappings().first()
        return float((row or {}).get("n", 0) or 0), "synced"

    # custom — no automatic source; the user (or a future manual-update
    # endpoint) supplies the value directly.
    return None, "manual metric"


def compute_progress(goal: dict, current_value: float | None = None) -> dict:
    """Attach a ``progress`` block to ``goal``. Pure — no I/O.

    When ``current_value`` is omitted, falls back to the last value stored in
    ``goal["progress"]`` (e.g. for list views that don't want to refetch).
    """
    target = float(goal.get("target_value") or 0)
    baseline = float(goal.get("baseline_value") or 0)

    if current_value is None:
        stored = goal.get("progress") or {}
        current_value = stored.get("current_value")

    result = dict(goal)

    if current_value is None:
        result["progress"] = {
            "current_value": None,
            "pct": None,
            "on_track": None,
            "computed_at": None,
        }
        return result

    achieved = current_value - baseline
    pct = 0.0
    if target > 0:
        pct = max(0.0, min(100.0, 100.0 * achieved / target))

    deadline = goal.get("deadline")
    on_track = None
    if deadline:
        if isinstance(deadline, str):
            deadline_dt = datetime.fromisoformat(deadline).replace(tzinfo=timezone.utc)
        else:
            deadline_dt = datetime(deadline.year, deadline.month, deadline.day, tzinfo=timezone.utc)
        baseline_at = goal.get("baseline_at")
        if isinstance(baseline_at, str):
            start_dt = datetime.fromisoformat(baseline_at)
        elif baseline_at:
            start_dt = baseline_at
        else:
            start_dt = datetime.now(timezone.utc)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        total_seconds = max((deadline_dt - start_dt).total_seconds(), 1)
        elapsed_pct = max(0.0, min(100.0, 100.0 * (now - start_dt).total_seconds() / total_seconds))
        on_track = pct >= elapsed_pct - 5  # 5-point grace band

    result["progress"] = {
        "current_value": current_value,
        "pct": round(pct, 1),
        "on_track": on_track,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


async def refresh_goal(session: AsyncSession, user_id: str, goal: dict) -> dict:
    current, _ = await read_metric(session, user_id, goal["metric"], goal.get("baseline_at"))
    return compute_progress(goal, current_value=current)
