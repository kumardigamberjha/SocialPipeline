"""
Instagram Graph API service.

Fetches profile metrics, media (posts & reels), per-post engagement, windowed
account insights and hashtag analytics for the connected Instagram account,
using the caller's per-user Instagram connection.

The rule this module follows is the one ``goal_service.read_metric`` states:
**a metric with no source is None, not a plausible-looking number.** The
previous version filled every unmeasured field with arithmetic — a post whose
insights call failed got ``reach = views = likes + comments``, and the account
stats block hardcoded ``followers_gained``, ``profile_visits`` and
``link_clicks`` to 0 because account-level insights were never requested at
all. Both read as measurements on the dashboard. Now a value Meta did not
return is ``None`` and the UI renders it as "not measured".

Three further correctness fixes live here:

*Windowed stats.* ``/stats?time_range=`` was accepted and then ignored, so 7
days, 90 days and all-time returned identical numbers. Stats are now computed
per window from the account insights endpoint (``since``/``until``), and the
whole set is returned keyed by range so a sync serves every option.

*Complete like/comment history.* Media is paginated instead of stopping at the
first 50 items, so lifetime totals (and the milestone history built on them)
cover the account rather than its most recent page.

*One HTTP client.* Every call opened its own ``httpx.Client`` — a fresh TCP and
TLS handshake per request, 50+ of them per sync. One pooled client is reused
for the whole fetch.
"""

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.instagram.com/v20.0"
# NOTE: graph.instagram.com is the correct base for Instagram Business Login tokens.
# graph.facebook.com is only for Facebook Login / legacy tokens.

# ── Fetch budget ─────────────────────────────────────────────────────────────

MEDIA_PAGE_SIZE = 50
# Up to 500 posts. The media edge is cheap (one call per page) and it is what
# makes lifetime like/comment totals real rather than "the last 50 posts".
MAX_MEDIA_PAGES = 10
# Per-post insights are one call *each*, so they stay on the recent window the
# dashboard actually shows. Everything derived from them is scoped accordingly.
INSIGHTS_LIMIT = 50

# Meta rejects an account-insights since/until span wider than 30 days.
INSIGHTS_MAX_WINDOW_DAYS = 30

# Ranges the dashboard's dropdown offers. all_time has no entry because account
# insights cannot answer it — it is served from lifetime post aggregates.
RANGE_DAYS: Dict[str, Optional[int]] = {
    "7_days": 7,
    "30_days": 30,
    "90_days": 90,
    "all_time": None,
}
DEFAULT_RANGE = "30_days"

# ── Metric vocabulary ────────────────────────────────────────────────────────

# Account metrics Meta returns as a per-day series, which we sum over the window.
# `impressions` is deprecated from v22 and simply resolves to None there — an
# absent measurement, which is exactly how it is then reported.
_ACCOUNT_SERIES_METRICS = ("reach", "follower_count", "impressions")

# Account metrics Meta only returns as one total for the window.
_ACCOUNT_TOTAL_METRICS = (
    "accounts_engaged",
    "total_interactions",
    "profile_views",
    "website_clicks",
    "views",
)

# Per-post insights, by media type. Requesting a metric a type does not support
# fails the *whole* call, which is how every post used to end up with fabricated
# fallbacks; _media_insights degrades to the pair every type supports instead.
_MEDIA_METRICS: Dict[str, Tuple[str, ...]] = {
    "reel": ("reach", "saved", "shares", "likes", "comments", "views", "total_interactions"),
    "carousel": ("reach", "saved", "shares", "total_interactions", "views"),
    "single": ("reach", "saved", "shares", "total_interactions", "views"),
}
_MEDIA_METRICS_FALLBACK = ("reach", "saved")

MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,"
    "timestamp,like_count,comments_count"
)
PROFILE_FIELDS = (
    "id,username,name,biography,profile_picture_url,"
    "followers_count,follows_count,media_count,website"
)


class InstagramGraphAPIError(Exception):
    """Raised when the Meta Graph API returns an error or is unreachable."""


# ── HTTP ─────────────────────────────────────────────────────────────────────


def make_meta_api_call(
    endpoint: str,
    access_token: str,
    params: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """
    Standard Meta Graph API call wrapper. Raises on Code 190 (expired token) like
    any other Graph API error — the retry-with-a-refreshed-token policy lives in
    ``fetch_live_instagram_data``, which is the one caller that knows the user_id
    needed to refresh.

    ``client`` lets a multi-call fetch reuse one pooled connection; omitting it
    opens a short-lived one, which is what single-shot callers want.
    """
    params = dict(params or {})
    params["access_token"] = access_token
    url = f"{GRAPH_API_BASE}/{endpoint.lstrip('/')}"

    if client is None:
        with httpx.Client(timeout=15.0) as owned:
            return make_meta_api_call(endpoint, access_token, params, client=owned)

    resp = client.get(url, params=params)
    data = resp.json()

    if "error" in data:
        err_code = data["error"].get("code")
        err_msg = data["error"].get("message", "Meta Graph API error")
        # debug, not error: several callers expect and handle these (an unknown
        # metric on a newer API version raises here on every single sync), and
        # the ones that do not re-log at their own level. The detail travels on
        # the exception either way.
        logger.debug("Meta Graph API error on %s: %s", endpoint, data["error"])
        if err_code == 190:
            raise InstagramGraphAPIError(f"Meta Access Token expired. {err_msg} (Code: {err_code})")
        raise InstagramGraphAPIError(f"{err_msg} (Code: {err_code})")

    return data


def _fetch(
    endpoint: str, params: Dict[str, Any], token: str, client: Optional[httpx.Client] = None
) -> Dict[str, Any]:
    return make_meta_api_call(endpoint, token, params, client=client)


def get_connected_instagram_account(
    token: str, client: Optional[httpx.Client] = None
) -> Dict[str, Any]:
    """
    Fetches the connected Instagram Business/Creator Account profile directly.
    Uses graph.instagram.com/me — correct for Instagram Business Login tokens.
    (graph.facebook.com /me/accounts is for Facebook Login only, not applicable here)
    """
    try:
        data = _fetch("me", {"fields": PROFILE_FIELDS}, token, client=client)
        if data.get("id"):
            logger.info(
                "Connected Instagram account: @%s (id=%s, followers=%s)",
                data.get("username"), data.get("id"), data.get("followers_count"),
            )
            return data
    except InstagramGraphAPIError:
        raise
    except Exception as e:
        logger.error("Failed to fetch Instagram profile via graph.instagram.com/me: %s", e)
        raise InstagramGraphAPIError(
            f"Could not fetch Instagram profile. Make sure the token is from "
            f"Instagram Business Login. Error: {e}"
        )

    raise InstagramGraphAPIError("No Instagram account data returned from graph.instagram.com/me")


# ── Insights parsing ─────────────────────────────────────────────────────────


def _insight_value(entry: Dict[str, Any]) -> Optional[float]:
    """The number in one insights entry, whichever shape Meta returned it in.

    ``metric_type=total_value`` responses carry ``total_value.value``; a
    ``period=day`` series carries ``values[]`` (summed here, since every series
    metric we request is a daily *gain*); lifetime media insights carry a
    single-element ``values[]``, which the same sum handles. Anything else is an
    absent measurement, not a zero.
    """
    total = entry.get("total_value")
    if isinstance(total, dict) and isinstance(total.get("value"), (int, float)):
        return float(total["value"])

    values = entry.get("values")
    if isinstance(values, list):
        nums = [
            v["value"]
            for v in values
            if isinstance(v, dict) and isinstance(v.get("value"), (int, float))
        ]
        if nums:
            return float(sum(nums))
    return None


def _parse_insights(payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for entry in payload.get("data", []) or []:
        name = entry.get("name")
        if name:
            out[name] = _insight_value(entry)
    return out


def _windows(days: int, now: Optional[datetime] = None) -> List[Tuple[int, int]]:
    """(since, until) unix pairs covering the last ``days``, each ≤ 30 days.

    Meta rejects a wider span in a single call, so a 90-day range is three
    requests whose per-day series are summed together.
    """
    now = now or datetime.now(timezone.utc)
    end = now
    spans: List[Tuple[int, int]] = []
    remaining = days
    while remaining > 0:
        span = min(remaining, INSIGHTS_MAX_WINDOW_DAYS)
        start = end - timedelta(days=span)
        spans.append((int(start.timestamp()), int(end.timestamp())))
        end = start
        remaining -= span
    return spans


# ── Account insights ─────────────────────────────────────────────────────────


def _account_insights_call(
    ig_id: str,
    token: str,
    metrics: Sequence[str],
    since: int,
    until: int,
    total_value: bool,
    client: httpx.Client,
    unsupported: set,
) -> Dict[str, Optional[float]]:
    """One insights request, degrading to per-metric calls if the batch fails.

    A batch naming one metric this API version does not support fails
    *entirely* — which is how the whole stats block used to come back empty and
    get replaced with hardcoded zeros. Retrying the metrics individually costs
    extra calls only on the error path, and ``unsupported`` remembers the names
    that failed so a 90-day range (three windows) pays that cost once instead of
    three times.
    """
    metrics = [m for m in metrics if m not in unsupported]
    if not metrics:
        return {}

    params: Dict[str, Any] = {
        "metric": ",".join(metrics),
        "period": "day",
        "since": since,
        "until": until,
    }
    if total_value:
        params["metric_type"] = "total_value"

    try:
        return _parse_insights(_fetch(f"{ig_id}/insights", params, token, client=client))
    except InstagramGraphAPIError as exc:
        if len(metrics) == 1:
            logger.info("Instagram insights: %s unavailable (%s)", metrics[0], exc)
            unsupported.add(metrics[0])
            return {metrics[0]: None}
        logger.info(
            "Instagram insights batch %s failed (%s); retrying metric by metric",
            ",".join(metrics), exc,
        )

    out: Dict[str, Optional[float]] = {}
    for metric in metrics:
        out.update(
            _account_insights_call(
                ig_id, token, [metric], since, until, total_value, client, unsupported
            )
        )
    return out


def _account_insights(
    ig_id: str, token: str, days: int, client: httpx.Client
) -> Dict[str, Optional[float]]:
    """Account metrics over the last ``days``, summed across ≤30-day windows.

    A metric is present with a number when Meta measured it in at least one
    window, and present as None when it measured it in none — so the caller can
    tell "zero reach" from "reach not available for this account".
    """
    totals: Dict[str, Optional[float]] = {
        m: None for m in (*_ACCOUNT_SERIES_METRICS, *_ACCOUNT_TOTAL_METRICS)
    }
    # Shared across every window of this range: a metric this API version
    # rejects is discovered once, not re-probed per 30-day chunk.
    unsupported: set = set()

    for since, until in _windows(days):
        for metrics, as_total in (
            (_ACCOUNT_SERIES_METRICS, False),
            (_ACCOUNT_TOTAL_METRICS, True),
        ):
            for name, value in _account_insights_call(
                ig_id, token, metrics, since, until, as_total, client, unsupported
            ).items():
                if value is None:
                    continue
                totals[name] = (totals.get(name) or 0.0) + value

    return totals


# ── Media ────────────────────────────────────────────────────────────────────


def _classify(item: Dict[str, Any]) -> str:
    """reel | carousel | single, from the media and product types."""
    if item.get("media_product_type") == "REELS" or item.get("media_type") == "VIDEO":
        return "reel"
    if item.get("media_type") == "CAROUSEL_ALBUM":
        return "carousel"
    return "single"


def _media_insights(
    media_id: str, post_type: str, token: str, client: httpx.Client
) -> Dict[str, Optional[float]]:
    """Lifetime insights for one media item, or an empty dict if unavailable."""
    last: Optional[Exception] = None
    for metrics in (_MEDIA_METRICS.get(post_type, _MEDIA_METRICS_FALLBACK),
                    _MEDIA_METRICS_FALLBACK):
        try:
            return _parse_insights(
                _fetch(f"{media_id}/insights", {"metric": ",".join(metrics)}, token, client=client)
            )
        except InstagramGraphAPIError as exc:
            last = exc
    logger.info("Instagram: no insights for media %s (%s)", media_id, last)
    return {}


def _as_int(value: Optional[float]) -> Optional[int]:
    return None if value is None else int(value)


def _engagement_rate(
    likes: int,
    comments: int,
    saves: Optional[int],
    shares: Optional[int],
    reach: Optional[int],
    followers: Optional[int] = None,
) -> Tuple[Optional[float], str]:
    """Interactions as a percentage of reach, or fallback to followers (ERR).

    Returns (rate, rate_type) where rate_type is "reach", "followers", or "none".
    """
    interactions = likes + comments + (saves or 0) + (shares or 0)
    if reach and reach > 0:
        return round(interactions / reach * 100, 1), "reach"
    if followers and followers > 0:
        return round((likes + comments + (saves or 0) + (shares or 0)) / followers * 100, 1), "followers"
    return None, "none"


def _build_post(
    item: Dict[str, Any],
    token: str,
    client: httpx.Client,
    with_insights: bool,
    followers: Optional[int] = None,
) -> Dict[str, Any]:
    """One post record. Every insights-derived field is None when unmeasured."""
    media_id = item.get("id", "")
    caption = item.get("caption") or ""
    post_type = _classify(item)
    likes = int(item.get("like_count") or 0)
    comments = int(item.get("comments_count") or 0)

    insights = _media_insights(media_id, post_type, token, client) if with_insights else {}
    reach = _as_int(insights.get("reach"))
    saves = _as_int(insights.get("saved"))
    shares = _as_int(insights.get("shares"))
    # `plays` is the pre-v22 name for a reel's view count.
    views = _as_int(insights.get("views") if insights.get("views") is not None
                    else insights.get("plays"))

    # First line of the caption, as the table's title column.
    title = caption.split("\n")[0].strip() if caption else f"Post {media_id}"
    if len(title) > 70:
        title = title[:67] + "..."

    engagement_rate, rate_type = _engagement_rate(
        likes, comments, saves, shares, reach, followers=followers
    )

    return {
        "id": media_id,
        "title": title,
        "type": post_type,
        "publish_time": item.get("timestamp", ""),
        # Straight off the media edge — exact for every post, always present.
        "likes": likes,
        "comments": comments,
        # Insights-derived — null rather than a stand-in when Meta withheld them.
        "views": views,
        "reach": reach,
        "saves": saves,
        "shares": shares,
        "engagement_rate": engagement_rate,
        "rate_type": rate_type,
        "insights_available": bool(insights),
        "metrics_updated_at": datetime.now(timezone.utc).isoformat(),
        "thumbnail_url": item.get("thumbnail_url") or item.get("media_url") or "",
        "permalink": item.get("permalink", ""),
        "caption": caption,
    }


def _fetch_media_pages(
    ig_id: str, token: str, client: httpx.Client
) -> Tuple[List[Dict[str, Any]], bool]:
    """Media items newest-first, and whether the edge was read to its end.

    The bool is the honest answer to "is this the whole account?", and it comes
    from the cursor running out rather than from comparing against the profile's
    ``media_count`` — that counter and this edge do not always agree on what
    counts as a post, so a count comparison can report an incomplete fetch for a
    fully-paginated account (and would then withhold correct lifetime totals).
    """
    items: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"fields": MEDIA_FIELDS, "limit": MEDIA_PAGE_SIZE}
    endpoint = f"{ig_id}/media"
    exhausted = False

    for _ in range(MAX_MEDIA_PAGES):
        resp = _fetch(endpoint, params, token, client=client)
        page = resp.get("data") or []
        items.extend(page)
        after = ((resp.get("paging") or {}).get("cursors") or {}).get("after")
        if not after or not page:
            exhausted = True
            break
        params = {**params, "after": after}

    if not exhausted:
        logger.info(
            "Instagram: stopped at the %d-page cap for %s with more media pending; "
            "lifetime engagement totals will be withheld rather than under-reported.",
            MAX_MEDIA_PAGES, ig_id,
        )
    return items, exhausted


# ── Hashtags ─────────────────────────────────────────────────────────────────

_HASHTAG_CATEGORIES: Tuple[Tuple[str, frozenset], ...] = (
    ("Language", frozenset({"python", "javascript", "typescript", "java", "cpp", "golang", "sql"})),
    ("AI / ML", frozenset({"ai", "aiagents", "machinelearning", "llm", "deeplearning",
                           "chatgpt", "ollama", "crewai", "langchain"})),
    ("Framework", frozenset({"fastapi", "react", "nextjs", "django", "vue", "node"})),
    ("Development", frozenset({"backend", "frontend", "fullstack", "webdev"})),
)


def _categorize(tag: str) -> str:
    lowered = tag.lower()
    if "codingindia" in lowered or "brand" in lowered:
        return "Brand"
    for name, members in _HASHTAG_CATEGORIES:
        if lowered in members:
            return name
    return "General"


def _hashtag_analytics(posts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hashtag performance, averaged over the posts whose reach was measured.

    ``posts_used`` counts every post carrying the tag; ``posts_measured`` counts
    the subset reach is known for, and ``avg_reach``/``score`` are None when that
    subset is empty. Previously the un-measured posts contributed a fabricated
    ``likes + comments`` reach into the same average.
    """
    tally: Dict[str, Dict[str, Any]] = {}

    for post in posts:
        reach = post.get("reach")
        for raw in set(re.findall(r"#([a-zA-Z0-9_]+)", post.get("caption") or "")):
            tag = f"#{raw.lower()}"
            row = tally.setdefault(
                tag,
                {"tag": tag, "posts_used": 0, "posts_measured": 0,
                 "total_reach": 0, "category": _categorize(raw)},
            )
            row["posts_used"] += 1
            if reach is not None:
                row["posts_measured"] += 1
                row["total_reach"] += reach

    out = []
    for row in tally.values():
        measured = row["posts_measured"]
        avg_reach = int(row["total_reach"] / measured) if measured else None
        # Ranking by raw avg_reach lets a hashtag used on a single lucky post
        # dominate; weighting by sqrt(posts_measured) rewards hashtags with
        # consistent, repeated performance instead.
        score = int(avg_reach * math.sqrt(measured)) if avg_reach else None
        out.append({
            "tag": row["tag"],
            "posts_used": row["posts_used"],
            "posts_measured": measured,
            "avg_reach": avg_reach,
            "score": score,
            "category": row["category"],
        })

    out.sort(key=lambda h: (h["score"] is not None, h["score"] or 0), reverse=True)
    return out


# ── Stats ────────────────────────────────────────────────────────────────────


def _mean(values: Sequence[float]) -> Optional[int]:
    return int(sum(values) / len(values)) if values else None


def _posts_in_window(posts: Sequence[Dict[str, Any]], days: Optional[int]) -> List[Dict[str, Any]]:
    if days is None:
        return list(posts)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    inside = []
    for post in posts:
        stamp = post.get("publish_time")
        if not stamp:
            continue
        try:
            published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published >= cutoff:
            inside.append(post)
    return inside


def _build_stats(
    time_range: str,
    followers: int,
    posts: Sequence[Dict[str, Any]],
    insights: Optional[Dict[str, Optional[float]]],
) -> Dict[str, Any]:
    """The stats block for one window.

    Publication counts come from the media timestamps, so they are exact for any
    window. Reach/engagement come from account insights when the account exposes
    them and are None otherwise — never the sum of a partial post sample dressed
    up as an account total.
    """
    days = RANGE_DAYS.get(time_range)
    window = _posts_in_window(posts, days)
    insights = insights or {}

    reels = [p for p in window if p["type"] == "reel"]
    carousels = [p for p in window if p["type"] == "carousel"]
    singles = [p for p in window if p["type"] == "single"]

    rates = [p["engagement_rate"] for p in window if p.get("engagement_rate") is not None]
    all_rates = [p["engagement_rate"] for p in posts if p.get("engagement_rate") is not None]

    # Calculate interactions from posts if insights total_interactions is None
    window_likes = sum(p.get("likes") or 0 for p in window)
    window_comments = sum(p.get("comments") or 0 for p in window)
    window_saves = sum(p.get("saves") or 0 for p in window)
    window_shares = sum(p.get("shares") or 0 for p in window)
    post_interactions = window_likes + window_comments + window_saves + window_shares

    total_interactions = _as_int(insights.get("total_interactions"))
    if total_interactions is None and post_interactions > 0:
        total_interactions = post_interactions

    avg_engagement = round(sum(rates) / len(rates), 1) if rates else (round(sum(all_rates) / len(all_rates), 1) if all_rates else None)

    return {
        "time_range": time_range,
        # Live from the profile — a point-in-time count, not a window figure.
        "total_followers": followers,
        "followers_gained": _as_int(insights.get("follower_count")),
        "total_reach": _as_int(insights.get("reach")),
        "total_views": _as_int(insights.get("views")),
        # Deprecated by Meta from v22; None there rather than a copy of reach,
        # which is what this field used to be.
        "total_impressions": _as_int(insights.get("impressions")),
        "accounts_engaged": _as_int(insights.get("accounts_engaged")),
        "total_interactions": total_interactions,
        "profile_visits": _as_int(insights.get("profile_views")),
        "link_clicks": _as_int(insights.get("website_clicks")),
        # Exact for every window: derived from each post's own timestamp.
        "posts_published": len(window),
        "total_posts_catalog": len(posts),
        "total_reels_published": len(reels),
        "total_carousels_published": len(carousels),
        "total_images_published": len(singles),
        "avg_reel_views": _mean([p["views"] for p in reels if p.get("views") is not None]),
        "avg_carousel_saves": _mean([p["saves"] for p in carousels if p.get("saves") is not None]),
        "avg_engagement_rate": avg_engagement,
        # Two different absences, which the UI must not conflate: all_time has
        # no account insights because the endpoint is windowed, not because the
        # connection lacks the permission.
        "insights_supported": days is not None,
        "insights_available": any(v is not None for v in insights.values()),
    }


# ── Public API ───────────────────────────────────────────────────────────────


def _with_fresh_token(user_id: str, call, *args, **kwargs):
    """Run ``call``, refreshing an expired token once and retrying."""
    from app.services.instagram_auth import get_instagram_access_token, refresh_if_needed

    token = get_instagram_access_token(user_id)
    if not token:
        raise InstagramGraphAPIError("Instagram account not connected.")
    try:
        return token, call(token, *args, **kwargs)
    except InstagramGraphAPIError as exc:
        if "Code: 190" not in str(exc):
            raise
        # Token expired between the read and this call — force a refresh, retry once.
        refresh_if_needed(user_id, force=True)
        token = get_instagram_access_token(user_id)
        if not token:
            raise
        return token, call(token, *args, **kwargs)


def fetch_live_instagram_data(user_id: str) -> Dict[str, Any]:
    """
    Complete live data from the Instagram Graph API:
      - profile information
      - media (reels, carousels, images) with per-post engagement
      - account stats for every supported time range
      - hashtag analytics
      - a ``coverage`` block describing what this fetch could and could not see

    ``user_id`` identifies whose connected account to read (per-user token,
    stored encrypted in ``instagram_oauth_tokens``).
    """
    with httpx.Client(timeout=15.0) as client:
        token, profile = _with_fresh_token(
            user_id, lambda tok: get_connected_instagram_account(tok, client=client)
        )

        ig_id = profile.get("id")
        if not ig_id:
            raise InstagramGraphAPIError("Invalid Instagram account ID received from Meta API.")

        media_items, media_complete = _fetch_media_pages(ig_id, token, client)
        followers = int(profile.get("followers_count") or 0)

        # Per-post insights are one call each, so only the recent window the
        # dashboard renders gets them; older posts still contribute their exact
        # like/comment counts to the lifetime totals.
        posts = [
            _build_post(item, token, client, with_insights=index < INSIGHTS_LIMIT, followers=followers)
            for index, item in enumerate(media_items)
        ]

        stats_by_range: Dict[str, Dict[str, Any]] = {}
        for time_range, days in RANGE_DAYS.items():
            insights = None
            if days is not None:
                try:
                    insights = _account_insights(ig_id, token, days, client)
                except InstagramGraphAPIError as exc:
                    # Insights need instagram_business_manage_insights and a
                    # Business/Creator account; a Basic connection simply has
                    # none, which the None-filled block reports honestly.
                    logger.info(
                        "Instagram account insights unavailable for %s over %sd: %s",
                        user_id, days, exc,
                    )
            stats_by_range[time_range] = _build_stats(time_range, followers, posts, insights)

    hashtags = _hashtag_analytics(posts)
    measured = [p for p in posts if p["reach"] is not None]
    media_total = int(profile.get("media_count") or len(posts))

    username = profile.get("username", "")
    rates = [p["engagement_rate"] for p in posts if p["engagement_rate"] is not None]

    profile_data = {
        "handle": f"@{username}" if username else "@instagram",
        "brand_name": profile.get("name") or (f"@{username}" if username else "Instagram User"),
        "url": f"https://instagram.com/{username}" if username else "https://instagram.com",
        "bio": profile.get("biography", ""),
        "followers": followers,
        "following": int(profile.get("follows_count") or 0),
        "total_posts": media_total,
        # Mean of the per-post rates that could be computed. None — not 0.0 —
        # when no post has measured reach. The windowed reach that used to be
        # mislabelled here as "monthly_reach" now lives in the stats block,
        # where it is actually scoped to a window.
        "avg_engagement_rate": round(sum(rates) / len(rates), 1) if rates else None,
        "profile_picture_url": profile.get("profile_picture_url", ""),
    }

    coverage = {
        # What the milestone history is allowed to call a lifetime total.
        "media_fetched": len(posts),
        "media_total": media_total,
        "media_complete": media_complete,
        "insights_requested": min(len(posts), INSIGHTS_LIMIT),
        "insights_measured": len(measured),
    }

    return {
        "profile": profile_data,
        "stats": stats_by_range[DEFAULT_RANGE],
        "stats_by_range": stats_by_range,
        "posts": posts,
        "hashtags": hashtags,
        "coverage": coverage,
    }


def fetch_single_post(user_id: str, media_id: str, followers: Optional[int] = None) -> Dict[str, Any]:
    """Re-read one media item and its insights — the per-post refresh button.

    Deliberately narrow: two API calls against one media id, rather than the
    whole-account sync a user would otherwise have to run (and wait through) to
    correct a single stale row.
    """
    with httpx.Client(timeout=15.0) as client:
        def _read(tok: str) -> Dict[str, Any]:
            item = _fetch(media_id, {"fields": MEDIA_FIELDS}, tok, client=client)
            if not item.get("id"):
                raise InstagramGraphAPIError(f"No Instagram media found for id {media_id}.")
            return _build_post(item, tok, client, with_insights=True, followers=followers)

        _, post = _with_fresh_token(user_id, _read)
    return post


# ── Local recomputation ──────────────────────────────────────────────────────

# Which stats key each account-insights metric lands in. Used to read a stored
# stats block back into the insights shape, so post-derived fields can be
# recomputed after a single-post refresh without re-billing Meta for the
# account-level metrics that did not change.
_STATS_INSIGHT_KEYS: Dict[str, str] = {
    "followers_gained": "follower_count",
    "total_reach": "reach",
    "total_views": "views",
    "total_impressions": "impressions",
    "accounts_engaged": "accounts_engaged",
    "total_interactions": "total_interactions",
    "profile_visits": "profile_views",
    "link_clicks": "website_clicks",
}


def _insights_from_stats(stats: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {metric: stats.get(key) for key, metric in _STATS_INSIGHT_KEYS.items()}


def recompute_derived(data: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild everything derived from ``posts``, making no API calls.

    After one post's metrics are refreshed, the averages, hashtag scores and
    per-window publication counts computed from those posts are stale. The
    account-level insights are not — nothing about them changed — so they are
    read back out of the stored blocks and carried through untouched.
    """
    posts = data.get("posts") or []
    profile = dict(data.get("profile") or {})
    followers = int(profile.get("followers") or 0)
    stored_ranges = data.get("stats_by_range") or {}

    # Ensure every post has engagement_rate and rate_type calculated
    for p in posts:
        if p.get("rate_type") is None:
            rate, rtype = _engagement_rate(
                p.get("likes") or 0,
                p.get("comments") or 0,
                p.get("saves"),
                p.get("shares"),
                p.get("reach"),
                followers=followers,
            )
            p["rate_type"] = rtype
            if p.get("engagement_rate") is None:
                p["engagement_rate"] = rate

    stats_by_range: Dict[str, Dict[str, Any]] = {}
    for time_range in RANGE_DAYS:
        previous = stored_ranges.get(time_range)
        if previous is None and time_range == DEFAULT_RANGE:
            previous = data.get("stats")
        stats_by_range[time_range] = _build_stats(
            time_range, followers, posts, _insights_from_stats(previous or {})
        )

    rates = [p["engagement_rate"] for p in posts if p.get("engagement_rate") is not None]
    profile["avg_engagement_rate"] = round(sum(rates) / len(rates), 1) if rates else None

    coverage = dict(data.get("coverage") or {})
    coverage["insights_measured"] = len([p for p in posts if p.get("reach") is not None])

    return {
        **data,
        "profile": profile,
        "stats": stats_by_range[DEFAULT_RANGE],
        "stats_by_range": stats_by_range,
        "hashtags": _hashtag_analytics(posts),
        "coverage": coverage,
    }
