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

_FIELDS = ("profile", "stats", "posts", "hashtags")


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
    profile, stats, posts, hashtags, synced_at = values
    if not (profile and stats):
        return None
    return {
        "profile": profile,
        "stats": stats,
        "posts": posts or [],
        "hashtags": hashtags or [],
        "synced_at": synced_at,
        "source": "redis",
    }


def _write_to_redis(user_id: str, data: Dict[str, Any]) -> None:
    rc = _get_redis()
    if not rc:
        return
    try:
        epoch = _epoch(rc, user_id)
        pipe = rc.pipeline()
        for field in _FIELDS:
            default = [] if field in ("posts", "hashtags") else {}
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
            return None
        return {
            "profile": row.profile_json,
            "stats": row.stats_json,
            "posts": row.posts_json,
            "hashtags": row.hashtags_json,
            "synced_at": row.synced_at.isoformat(),
            "source": "db",
        }
    except Exception as e:
        logger.error("Failed to load Instagram snapshot for %s: %s", user_id, e)
        return None


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
        return cached

    snapshot = _db_load_latest_snapshot(user_id)
    if snapshot:
        logger.info("Instagram cache MISS (Redis) for %s — serving from DB.", user_id)
        _write_to_redis(user_id, snapshot)
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
