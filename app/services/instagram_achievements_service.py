"""Milestone achievements from the user's own Instagram data.

The YouTube twin of this module (``youtube_achievements_service``) was written
against a page that rendered a hardcoded ``FALLBACK`` constant; the rule both
are built around is the one ``goal_service.read_metric`` states: **a metric
with no source returns None, not a plausible-looking number.** Every field here
is either measured or absent, and the ladder/formatting/projection maths is the
shared implementation in ``app.services.milestones``.

What Instagram can and cannot honestly support:

``followers`` and ``posts``
    Lifetime and exact — ``followers_count`` and ``media_count`` come straight
    off the profile. Posts additionally get a real history, because a post's
    publish month is a fact rather than an estimate, so its milestone dates and
    its pace projection are both genuine. Followers have no stored history at
    all (the nightly snapshot keeps 7 rows, not a series), so that card carries
    its current value and its next rung and deliberately nothing else.

``likes`` and ``comments``
    Summed from the synced media, which is a *lifetime* total only when
    pagination reached the whole account. ``coverage.media_complete`` decides
    that; when it is false these are reported as unavailable rather than as a
    total that silently omits everything past the fetch cap.

``reach``, ``views``, ``saves``, ``shares``
    Per-post insights cost one API call each, so the sync measures them for the
    most recent ``INSIGHTS_LIMIT`` posts only. There is no window in which
    summing them yields a lifetime figure, so they get no milestone card — they
    are listed as unavailable with the reason.

The single basis is therefore ``post_month``: per-post lifetime totals credited
to the month each post was published. It is exact for counts of posts and
approximate for engagement (likes a 2024 post earned in 2026 are counted in
2024), which the client is told so an approximation is never rendered as an
exact claim.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.instagram_data import INSIGHTS_LIMIT
from app.services.milestones import (
    achieved_month,
    eta_for,
    format_label,
    format_month,
    monthly_rate,
    rungs_for,
    series_values,
)

logger = logging.getLogger(__name__)

BASIS = "post_month"

# ── Metric vocabulary ────────────────────────────────────────────────────────

# The cards the UI renders, in display order. ``series`` is the monthly key each
# one aggregates; ``lifetime`` says where its current value legitimately comes
# from:
#   profile   – a live count on the account itself, exact and complete
#   posts_sum – summed from synced media, honest only under full coverage
METRICS: Dict[str, Dict[str, str]] = {
    "followers": {"series": "followers_gained", "lifetime": "profile", "field": "followers"},
    "posts":     {"series": "posts",            "lifetime": "profile", "field": "total_posts"},
    "likes":     {"series": "likes",            "lifetime": "posts_sum"},
    "comments":  {"series": "comments",         "lifetime": "posts_sum"},
}

# Followers have no stored history anywhere — the profile exposes a point-in-time
# count and nothing before it. The count is real, so the card shows current +
# next rung, but an achieved date or a best month would be invention.
NO_HISTORY = frozenset({"followers"})

# A post's publish month is a fact, so counting posts per month is exact and its
# projection is a real rate. Projecting likes from lifetime totals pinned to
# publish dates is not a growth rate, so those cards get no ETA.
ETA_ALLOWED = frozenset({"posts"})

# Measured for the recent window only (see the module docstring), so never
# summable into a lifetime milestone.
INSIGHTS_ONLY_METRICS: Tuple[str, ...] = ("reach", "views", "saves", "shares")


# ── History ──────────────────────────────────────────────────────────────────


def monthly_series(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-post lifetime totals bucketed by publish month, oldest first."""
    buckets: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"posts": 0.0, "likes": 0.0, "comments": 0.0}
    )

    for post in posts:
        month = _publish_month(post.get("publish_time"))
        if not month:
            continue
        bucket = buckets[month]
        bucket["posts"] += 1
        bucket["likes"] += int(post.get("likes") or 0)
        bucket["comments"] += int(post.get("comments") or 0)

    return [
        {
            "month": month,
            "posts": int(bucket["posts"]),
            "likes": int(bucket["likes"]),
            "comments": int(bucket["comments"]),
            # Not measurable from a post's own record; left absent rather than
            # zeroed so series_values() skips it instead of averaging in a 0.
            "followers_gained": None,
        }
        for month, bucket in sorted(buckets.items())
    ]


def _publish_month(stamp: Optional[str]) -> Optional[str]:
    """'2025-03-14T09:12:00+0000' -> '2025-03'."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%Y-%m")
    except ValueError:
        logger.debug("achievements: unparseable Instagram timestamp %r", stamp)
        return None


# ── Current values ───────────────────────────────────────────────────────────


def read_metric(
    metric: str,
    profile: Dict[str, Any],
    posts: List[Dict[str, Any]],
    coverage: Dict[str, Any],
) -> Tuple[Optional[float], str]:
    """Current value for ``metric``. Returns (value, note); None when unknown.

    Never a fabricated 0 — the same contract as ``goal_service.read_metric``.
    """
    config = METRICS[metric]

    if config["lifetime"] == "profile":
        value = profile.get(config["field"])
        if value is None:
            return None, "not synced yet — run Sync Metrics"
        return float(value), "live"

    # posts_sum: only a lifetime total when pagination saw the whole account.
    if not coverage.get("media_complete"):
        fetched = coverage.get("media_fetched")
        total = coverage.get("media_total")
        if fetched and total:
            return None, f"only the most recent {fetched} of {total} posts are synced"
        return None, "not synced yet — run Sync Metrics"

    return float(sum(int(p.get(metric) or 0) for p in posts)), "synced"


# ── Assembly ─────────────────────────────────────────────────────────────────


def build_achievements(cached: Dict[str, Any]) -> Dict[str, Any]:
    """The payload behind GET /api/instagram-analytics/achievements.

    Takes the already-cached snapshot rather than fetching: this is arithmetic
    over data the nightly sync already stored, so it costs no Meta API quota.
    """
    profile = cached.get("profile") or {}
    posts = cached.get("posts") or []
    coverage = cached.get("coverage") or {}
    series = monthly_series(posts)
    current_month = date.today().strftime("%Y-%m")

    # "Best month ever" is a claim about the whole history, so it needs the whole
    # history. Pagination fetches newest-first, which leaves the *recent* months
    # complete — enough for a pace projection, and enough for achieved_month to
    # simply return None when the running total cannot reach a rung — but the
    # oldest months are the ones missing, and those are exactly where a record
    # month is most likely to hide.
    history_complete = bool(coverage.get("media_complete"))

    key_achievements: List[Dict[str, Any]] = []
    top_months: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, str]] = [
        {
            "metric": metric,
            "reason": f"measured for the {INSIGHTS_LIMIT} most recent posts only, "
                      f"so it has no lifetime total",
        }
        for metric in INSIGHTS_ONLY_METRICS
    ]

    for metric, config in METRICS.items():
        value, note = read_metric(metric, profile, posts, coverage)
        if value is None:
            unavailable.append({"metric": metric, "reason": note})
            continue

        key = config["series"]
        achieved, next_up = rungs_for(value)
        has_history = metric not in NO_HISTORY

        month_key = achieved_month(series, key, achieved) if (has_history and achieved) else None
        rate = monthly_rate(series, key) if metric in ETA_ALLOWED else None

        key_achievements.append({
            "metric": metric,
            "milestone": achieved,
            "milestone_label": format_label(achieved),
            "achieved_date": format_month(month_key) if month_key else None,
            "current_value": int(value) if float(value).is_integer() else round(value, 1),
            "next_milestone": next_up,
            "next_milestone_label": format_label(next_up),
            "next_milestone_eta": eta_for(next_up - value, rate) if next_up else None,
            "progress_pct": int(min(value / next_up * 100, 100)) if next_up else 100,
        })

        if not has_history or not history_complete:
            continue

        values = series_values(series, key)
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

    if not history_complete and posts:
        unavailable.append({
            "metric": "best_months",
            "reason": "needs your full post history; only the most recent posts are synced",
        })

    return {
        "basis": BASIS,
        "as_of": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synced_at": cached.get("synced_at"),
        # True when the snapshot predates insights provenance, so the client can
        # ask for a re-sync instead of presenting thin data as complete.
        "stale": bool(cached.get("stale")),
        "months_of_history": len(series),
        "coverage": coverage,
        "key_achievements": key_achievements,
        "top_performing_months": top_months,
        "unavailable": unavailable,
    }
