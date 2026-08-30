"""Milestone achievements from the user's own channel data.

The page this backs used to render a hardcoded ``FALLBACK`` constant because the
endpoint it called had never been written; every number on it belonged to
nobody. The rule this module is built around is therefore the same one
``goal_service.read_metric`` states: **a metric with no source returns None, not
a plausible-looking number.** Every field here is either measured or null.

Two histories can back a milestone, and which one is in play is reported to the
client as ``basis`` so the UI can label the difference:

``analytics_api``
    A true monthly series from the YouTube Analytics API (``dimensions="month"``).
    Exact: the month a metric actually crossed a rung, and a real growth rate.

``upload_month``
    Each video's lifetime totals credited to the month it was published, then
    running-totalled. Always available — it needs only the synced video tables —
    but approximate by construction: views a 2021 video earned in 2026 are
    counted in 2021. Never presented as exact.

Lifetime totals never come from ``youtube_videos_live.watch_time_hours`` or
``subscribers_gained``: ``sync_video_analytics`` fills those from a 90-day,
top-200-video Analytics query, so summing them reports a quarter as a lifetime.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import goal_service
# The ladder, the display formatting and the two facts a monthly series can
# support are platform-agnostic and now live in one place; Instagram's
# achievements are built on exactly the same maths.
from app.services.milestones import (
    achieved_month,
    eta_for,
    format_label,
    format_month,
    monthly_rate,
    rungs_for,
    series_values as _series_values,
)

logger = logging.getLogger(__name__)

# ── Metric vocabulary ────────────────────────────────────────────────────────

# The six cards the UI renders, mapped to the series key each one aggregates and
# to the metric name goal_service.read_metric knows it by.
METRICS: dict[str, dict] = {
    "subscribers": {"series": "subscribers_gained", "goal_metric": "subscribers"},
    "views":       {"series": "views",              "goal_metric": "views"},
    "uploads":     {"series": "uploads",            "goal_metric": "videos_published"},
    "likes":       {"series": "likes",              "goal_metric": "likes"},
    "watch_time":  {"series": "watch_time_hours",   "goal_metric": "watch_hours"},
    "comments":    {"series": "comments",           "goal_metric": "comments"},
}

# Subscribers have no stored history anywhere: youtube_published_videos.subscribers
# is all zeros and subscribers_gained is only populated for a 90-day window. The
# live count is real, so the card shows current + next rung — but its achieved
# date and best month would be invention, so under upload_month it gets neither.
NO_HISTORY_UNDER_ATTRIBUTION = frozenset({"subscribers"})

# Attribution can time an upload exactly — a video's publish month is a fact, not
# an estimate — so uploads keeps its projection even without the Analytics API.
# Everything else would be projecting from lifetime views pinned to publish
# dates, which is not a growth rate.
ETA_UNDER_ATTRIBUTION = frozenset({"uploads"})

# ── History ──────────────────────────────────────────────────────────────────

# Lifetime per-video figures, bucketed by publish month. The two tables hold the
# same video_id set for a user, so this is a 1:1 join: youtube_videos_live has
# the publish date and the Data API counters, youtube_published_videos has the
# lifetime watch time from the Studio CSV export.
_ATTRIBUTION_SQL = text("""
    SELECT to_char(l.published_at, 'YYYY-MM')        AS month,
           COUNT(*)                                  AS uploads,
           COALESCE(SUM(l.views), 0)                 AS views,
           COALESCE(SUM(l.likes), 0)                 AS likes,
           COALESCE(SUM(l.comments), 0)              AS comments,
           COALESCE(SUM(p.watch_time_hours), 0)      AS watch_time_hours
    FROM youtube_videos_live l
    LEFT JOIN youtube_published_videos p
           ON p.user_id = l.user_id AND p.video_id = l.video_id
    WHERE l.user_id = :user_id
      AND l.published_at IS NOT NULL
      -- Matches goal_service.read_metric('videos_published'), which counts only
      -- public videos. Without it the uploads card would show a current value of
      -- 373 above a history summing to 402.
      AND l.privacy_status = 'public'
    GROUP BY 1
    ORDER BY 1
""")


# Until this was fixed, sync_all_videos wrote round(views * duration / 3600) into
# youtube_published_videos.watch_time_hours — the 100%-retention formula — so any
# channel synced before then has a column full of arithmetic rather than
# measurement. Nothing in the row distinguishes the two, so we test the values
# themselves: genuine watch time cannot match that formula on nearly every video,
# because that would mean every viewer watched every video to the end.
_SYNTHETIC_WATCH_TIME_SQL = text("""
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (
               WHERE p.watch_time_hours > 0
                 AND l.duration_seconds > 0
                 AND abs(p.watch_time_hours - (l.views * l.duration_seconds) / 3600.0) < 0.02
           ) AS formula_matches
    FROM youtube_published_videos p
    JOIN youtube_videos_live l ON l.user_id = p.user_id AND l.video_id = p.video_id
    WHERE p.user_id = :user_id
""")

# A real channel will not clear this by chance; 100% retention on 9 of every 10
# videos does not happen.
_SYNTHETIC_THRESHOLD = 0.9


async def watch_time_is_synthetic(session: AsyncSession, user_id: str) -> bool:
    """True when the stored watch time is the old formula rather than a measurement."""
    row = (await session.execute(_SYNTHETIC_WATCH_TIME_SQL, {"user_id": user_id})).mappings().first()
    total = int((row or {}).get("total") or 0)
    if not total:
        return False
    return int(row["formula_matches"]) / total >= _SYNTHETIC_THRESHOLD


async def _attribution_series(session: AsyncSession, user_id: str) -> list[dict]:
    rows = (await session.execute(_ATTRIBUTION_SQL, {"user_id": user_id})).mappings().all()
    return [
        {
            "month": r["month"],
            "uploads": int(r["uploads"] or 0),
            "views": int(r["views"] or 0),
            "likes": int(r["likes"] or 0),
            "comments": int(r["comments"] or 0),
            "watch_time_hours": round(float(r["watch_time_hours"] or 0), 2),
            # Not measurable from video rows; left absent rather than zeroed so
            # series_total() reports None instead of a confident 0.
            "subscribers_gained": None,
        }
        for r in rows
    ]


async def monthly_series(session: AsyncSession, user_id: str) -> tuple[list[dict], str]:
    """The best monthly history available, with the basis that produced it."""
    from app.services.youtube_sync_service import get_monthly_channel_series

    try:
        rows = await asyncio.to_thread(get_monthly_channel_series, user_id)
        if rows:
            # The API series has no upload counts; fold them in from the DB so
            # the uploads card works on both paths.
            uploads_by_month = {
                r["month"]: r["uploads"] for r in await _attribution_series(session, user_id)
            }
            for row in rows:
                row["uploads"] = uploads_by_month.get(row["month"], 0)
            return rows, "analytics_api"
        logger.info("achievements: Analytics API returned no monthly rows for %s", user_id)
    except Exception as exc:
        logger.info(
            "achievements: monthly Analytics series unavailable for %s (%s); "
            "falling back to upload-month attribution", user_id, exc,
        )

    return await _attribution_series(session, user_id), "upload_month"


# ── Assembly ─────────────────────────────────────────────────────────────────


async def build_achievements(session: AsyncSession, user_id: str) -> dict:
    """The payload behind GET /api/youtube-analytics/achievements."""
    series, basis = await monthly_series(session, user_id)
    current_month = date.today().strftime("%Y-%m")

    # Only the Analytics API path measures watch time; on the attribution path the
    # stored column may be the retired synthetic formula, and a fabricated
    # milestone is exactly what this page is being fixed for.
    skip_watch_time = basis != "analytics_api" and await watch_time_is_synthetic(
        session, user_id
    )

    key_achievements: list[dict] = []
    top_months: list[dict] = []
    unavailable: list[dict] = []

    for metric, cfg in METRICS.items():
        if metric == "watch_time" and skip_watch_time:
            unavailable.append({
                "metric": metric,
                "reason": "not measured yet — run Sync Analytics or import a Studio CSV",
            })
            continue

        key = cfg["series"]
        value, note = await goal_service.read_metric(session, user_id, cfg["goal_metric"])
        if value is None:
            unavailable.append({"metric": metric, "reason": note})
            continue

        achieved, next_up = rungs_for(value)

        # An attributed history cannot time subscriber growth, so that card
        # carries its current value and its next goal and nothing else.
        has_history = not (basis == "upload_month" and metric in NO_HISTORY_UNDER_ATTRIBUTION)
        month_key = achieved_month(series, key, achieved) if (has_history and achieved) else None

        wants_eta = basis == "analytics_api" or metric in ETA_UNDER_ATTRIBUTION
        rate = monthly_rate(series, key) if wants_eta else None

        key_achievements.append({
            "metric": metric,
            "milestone": achieved,
            "milestone_label": format_label(achieved),
            "achieved_date": format_month(month_key) if month_key else None,
            "current_value": round(value, 1) if isinstance(value, float) else value,
            "next_milestone": next_up,
            "next_milestone_label": format_label(next_up),
            "next_milestone_eta": eta_for(next_up - value, rate) if next_up else None,
            "progress_pct": int(min(value / next_up * 100, 100)) if next_up else 100,
        })

        if not has_history:
            continue

        values = _series_values(series, key)
        if not values:
            continue
        best_month, best_value = max(values, key=lambda pair: pair[1])
        if best_value <= 0:
            continue
        this_month = next((v for m, v in values if m == current_month), 0.0)
        top_months.append({
            "metric": metric,
            "milestone": best_value,
            "milestone_label": format_label(best_value),
            "achieved_date": format_month(best_month),
            "current_value": round(this_month, 1),
            "progress_pct": int(min(this_month / best_value * 100, 100)),
        })

    return {
        "basis": basis,
        "as_of": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "months_of_history": len(series),
        "key_achievements": key_achievements,
        "top_performing_months": top_months,
        "unavailable": unavailable,
    }
