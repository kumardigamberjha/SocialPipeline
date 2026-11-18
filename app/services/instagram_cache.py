"""
Instagram Analytics Cache Service.

Strategy (in priority order):
  1. Redis    → TTL 25 hours (refreshed nightly)
  2. Postgres → last persisted snapshot (fallback if Redis is down)
  3. Instagram API → only called by the nightly Celery task or a manual refresh

Everything here is keyed by ``user_id``. The previous version used fixed global
keys (``ig:profile``, ``ig:stats``, …) and a single ``instagram_snapshots``
table with no owner column, so every user was served whichever account had
synced last.

Cache invalidation uses a per-user *epoch* counter rather than ``KEYS ig:*`` +
``DELETE``. ``KEYS`` is O(keyspace) and blocks Redis for every other client;
bumping an epoch is a single ``INCR`` and lets stale keys expire on their own.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import delete, select

from app.db.sync_session import sync_session_scope
from app.db.tables import InstagramSnapshot

logger = logging.getLogger(__name__)

# Redis cache TTL: 25 hours (nightly job runs every 24h, +1h safety buffer)
REDIS_TTL = 60 * 60 * 25

# How many snapshots to retain per user.
SNAPSHOT_RETENTION = 7

# Fields written to Redis as their own keys and read back in one MGET.
_FIELDS = ("profile", "stats", "stats_by_range", "posts", "hashtags", "coverage")

# Which of them are lists, so a missing key restores as [] rather than {}.
_LIST_FIELDS = frozenset({"posts", "hashtags"})


# ── Redis helpers ─────────────────────────────────────────────────────────────


def _get_redis():
    """Returns a Redis client for the cache instance, or None if unavailable."""
    try:
        from app.core.redis_client import scache

        return scache()
    except Exception as e:
        logger.warning("Redis unavailable for Instagram cache: %s", e)
        return None


def _epoch(rc, user_id: str) -> int:
    """Current cache generation for this user (0 when Redis has none)."""
    from app.core.redis_client import uk

    try:
        return int(rc.get(uk(user_id, "ig", "epoch")) or 0)
    except Exception:
        return 0


def _key(user_id: str, epoch: int, field: str) -> str:
    from app.core.redis_client import uk

    return uk(user_id, "ig", str(epoch), field)


def _redis_get_all(user_id: str) -> Optional[Dict[str, Any]]:
    rc = _get_redis()
    if not rc:
        return None
    try:
        epoch = _epoch(rc, user_id)
        keys = [_key(user_id, epoch, f) for f in _FIELDS] + [
            _key(user_id, epoch, "synced_at")
        ]
        # One round trip for the whole snapshot instead of five connections.
        raw = rc.mget(keys)
    except Exception as e:
        logger.warning("Redis MGET for user %s failed: %s", user_id, e)
        return None

    values = [json.loads(v) if v else None for v in raw]
    data = dict(zip(_FIELDS, values))
    synced_at = values[-1]
    if not (data.get("profile") and data.get("stats")):
        return None
    for field in _FIELDS:
        if data.get(field) is None:
            data[field] = [] if field in _LIST_FIELDS else {}
    return {**data, "synced_at": synced_at, "source": "redis"}


def _write_to_redis(user_id: str, data: Dict[str, Any]) -> None:
    rc = _get_redis()
    if not rc:
        return
    try:
        epoch = _epoch(rc, user_id)
        pipe = rc.pipeline()
        for field in _FIELDS:
            default = [] if field in _LIST_FIELDS else {}
            pipe.setex(
                _key(user_id, epoch, field),
                REDIS_TTL,
                json.dumps(data.get(field, default), default=str),
            )
        pipe.setex(
            _key(user_id, epoch, "synced_at"),
            REDIS_TTL,
            json.dumps(data.get("synced_at")),
        )
        pipe.execute()
    except Exception as e:
        logger.warning("Redis write for user %s failed: %s", user_id, e)


def _bump_epoch(user_id: str) -> None:
    """Invalidate this user's cached Instagram data in O(1)."""
    rc = _get_redis()
    if not rc:
        return
    try:
        from app.core.redis_client import uk

        rc.incr(uk(user_id, "ig", "epoch"))
    except Exception as e:
        logger.warning("Redis epoch bump for user %s failed: %s", user_id, e)


# ── Postgres helpers ──────────────────────────────────────────────────────────


def _db_save_snapshot(user_id: str, data: Dict[str, Any]) -> None:
    """Persist a fresh Instagram snapshot, pruning this user's older rows."""
    try:
        with sync_session_scope() as session:
            session.add(
                InstagramSnapshot(
                    user_id=user_id,
                    profile_json=data.get("profile", {}),
                    stats_json=data.get("stats", {}),
                    stats_by_range_json=data.get("stats_by_range", {}),
                    coverage_json=data.get("coverage", {}),
                    posts_json=data.get("posts", []),
                    hashtags_json=data.get("hashtags", []),
                    synced_at=datetime.now(timezone.utc),
                )
            )
            session.flush()

            # Retention is per user; the previous DELETE kept the newest 7 rows
            # across the whole table, so an active account evicted everyone else.
            keep = select(InstagramSnapshot.id).where(
                InstagramSnapshot.user_id == user_id
            ).order_by(InstagramSnapshot.synced_at.desc()).limit(SNAPSHOT_RETENTION)
            session.execute(
                delete(InstagramSnapshot).where(
                    InstagramSnapshot.user_id == user_id,
                    InstagramSnapshot.id.not_in(keep),
                )
            )
        logger.info("Instagram snapshot saved for user %s.", user_id)
    except Exception as e:
        logger.error("Failed to save Instagram snapshot for %s: %s", user_id, e)


def _db_load_latest_snapshot(user_id: str) -> Optional[Dict[str, Any]]:
    """Load this user's most recent Instagram snapshot."""
    try:
        with sync_session_scope() as session:
            row = session.execute(
                select(InstagramSnapshot)
                .where(InstagramSnapshot.user_id == user_id)
                .order_by(InstagramSnapshot.synced_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if row is None:
            # Fallback to the latest workspace snapshot if this user has none yet
            row = session.execute(
                select(InstagramSnapshot)
                .order_by(InstagramSnapshot.synced_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "profile": row.profile_json,
            "stats": row.stats_json,
            # A snapshot written before the per-range sync existed has no
            # breakdown; the default range falls back to its single stats blob.
            "stats_by_range": row.stats_by_range_json or {},
            "coverage": row.coverage_json or {},
            "posts": row.posts_json,
            "hashtags": row.hashtags_json,
            "synced_at": row.synced_at.isoformat(),
            "source": "db",
        }
    except Exception as e:
        logger.error("Failed to load Instagram snapshot for %s: %s", user_id, e)
        return None


# ── Legacy snapshots ──────────────────────────────────────────────────────────
#
# Snapshots written before insights provenance was tracked cannot be trusted
# field-by-field. The sync that produced them filled a failed insights call with
# ``reach = views = likes + comments``, so a post with 26 likes was stored with
# 26 reach and an engagement rate of "100.0%". Nothing in the row distinguishes
# that from a real measurement, so every insights-derived field on an old
# snapshot is treated as unmeasured — the same rule the rest of this feature
# follows, applied to data that predates it.
#
# What survives is what the media edge always returned exactly: likes, comments,
# captions, timestamps, permalinks. Publication counts per window are recomputed
# from those timestamps, so an old snapshot still shows real post counts while
# reporting "—" for anything it cannot vouch for.

# Insights-derived on a post, and therefore unverifiable on a legacy row.
_LEGACY_SUSPECT_FIELDS = ("views", "reach", "saves", "shares", "engagement_rate")


def _is_legacy(data: Dict[str, Any]) -> bool:
    """True for a snapshot written before provenance tracking existed."""
    return "media_complete" not in (data.get("coverage") or {})


def _normalize_legacy(data: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the unverifiable fields off an old snapshot and re-derive the rest."""
    from app.services.instagram_data import recompute_derived

    posts = []
    for raw in data.get("posts") or []:
        post = dict(raw)
        for field in _LEGACY_SUSPECT_FIELDS:
            post[field] = None
        post["insights_available"] = False
        post.setdefault("metrics_updated_at", data.get("synced_at"))
        posts.append(post)

    # Dropping the stored stats block too: it carries the same fabricated reach,
    # plus a hardcoded followers_gained of 0. recompute_derived rebuilds each
    # window from the post timestamps, which are real.
    rebuilt = recompute_derived({
        **data,
        "posts": posts,
        "stats": {},
        "stats_by_range": {},
    })
    rebuilt["coverage"] = {
        "media_fetched": len(posts),
        "media_total": (data.get("profile") or {}).get("total_posts") or len(posts),
        # Not "we saw everything" — we cannot know, and lifetime milestones must
        # not be claimed from it.
        "media_complete": False,
        "insights_requested": 0,
        "insights_measured": 0,
    }
    # Surfaced so the UI can ask for a re-sync rather than silently showing dashes.
    rebuilt["stale"] = True
    return rebuilt


# ── Public API ────────────────────────────────────────────────────────────────


def get_cached_instagram_data(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns this user's cached Instagram data.

    Priority: Redis → Postgres → None (caller should show a no-data state).
    Never calls the Instagram API — that's the refresh path's job.
    """
    cached = _redis_get_all(user_id)
    if cached:
        logger.debug("Instagram cache HIT (Redis) for %s", user_id)
        return _normalize_legacy(cached) if _is_legacy(cached) else cached

    snapshot = _db_load_latest_snapshot(user_id)
    if snapshot:
        logger.info("Instagram cache MISS (Redis) for %s — serving from DB.", user_id)
        _write_to_redis(user_id, snapshot)
        if _is_legacy(snapshot):
            logger.info(
                "Instagram snapshot for %s predates insights provenance; serving its "
                "verifiable fields only until the next sync.", user_id,
            )
            return _normalize_legacy(snapshot)
        return snapshot

    logger.warning("Instagram cache MISS (Redis + DB) for %s.", user_id)
    return None


def refresh_instagram_cache(user_id: str) -> Dict[str, Any]:
    """
    Fetch fresh data from the Instagram API and store it for this user.
    Called by the nightly Celery task or a manual refresh.
    """
    from app.services.instagram_data import fetch_live_instagram_data

    logger.info("Instagram refresh for user %s...", user_id)

    data = fetch_live_instagram_data(user_id)
    data["synced_at"] = datetime.now(timezone.utc).isoformat()

    _bump_epoch(user_id)
    _write_to_redis(user_id, data)
    _db_save_snapshot(user_id, data)

    logger.info(
        "Instagram cache refreshed for %s. Profile: @%s | Posts: %d | Hashtags: %d",
        user_id,
        data.get("profile", {}).get("handle", "?"),
        len(data.get("posts", [])),
        len(data.get("hashtags", [])),
    )
    return data


def _db_update_latest_snapshot(user_id: str, data: Dict[str, Any]) -> None:
    """Rewrite this user's newest snapshot in place.

    A single-post refresh amends the last sync rather than being one; writing a
    new row for it would push a real nightly snapshot out of the 7-row retention
    window every time someone clicked a refresh button.
    """
    try:
        with sync_session_scope() as session:
            row = session.execute(
                select(InstagramSnapshot)
                .where(InstagramSnapshot.user_id == user_id)
                .order_by(InstagramSnapshot.synced_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return
            row.profile_json = data.get("profile", {})
            row.stats_json = data.get("stats", {})
            row.stats_by_range_json = data.get("stats_by_range", {})
            row.coverage_json = data.get("coverage", {})
            row.posts_json = data.get("posts", [])
            row.hashtags_json = data.get("hashtags", [])
    except Exception as e:
        logger.error("Failed to update Instagram snapshot for %s: %s", user_id, e)


def update_cached_post(user_id: str, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Replace one post inside this user's cached data and re-derive the rest.

    Backs the per-post refresh button. Returns the updated snapshot, or None if
    there is nothing cached to amend (the caller should run a full sync first).
    Makes no Instagram API calls of its own — ``post`` is already the fresh
    reading, and every figure recomputed from it is local arithmetic.
    """
    from app.services.instagram_data import recompute_derived

    cached = get_cached_instagram_data(user_id)
    if not cached:
        return None

    posts = list(cached.get("posts") or [])
    index = next((i for i, p in enumerate(posts) if p.get("id") == post.get("id")), None)
    if index is None:
        # A post published since the last sync: newest first is the media edge's
        # own order, and its timestamp puts it at the front.
        posts.insert(0, post)
    else:
        posts[index] = post

    updated = recompute_derived({**cached, "posts": posts})
    updated["synced_at"] = cached.get("synced_at")
    updated["source"] = cached.get("source")

    _write_to_redis(user_id, updated)
    _db_update_latest_snapshot(user_id, updated)
    return updated
