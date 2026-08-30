"""
YouTube Analytics & Metadata Redis Cache Service.

Strategy:
  1. Redis Cache:
     - User-scoped keys with epoch-based invalidation (O(1) invalidation)
     - Multi-domain partitioning (stats, videos, live, achievements, playlists, audience, reporting)
     - Configurable TTLs (5m default, up to 25h for snapshots)
  2. Postgres:
     - Durable persistence in youtube_videos_live, youtube_published_videos, etc.
  3. YouTube Data / Analytics / Reporting APIs:
     - Called on explicit user sync, Celery nightly sync, or metadata updates.

Invalidation uses per-user epoch counters in Redis rather than keyspace scanning (KEYS).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from app.core.redis_client import (
    acache,
    bump_epoch,
    bump_epoch_sync,
    get_epoch,
    scache,
    uk,
)

logger = logging.getLogger(__name__)

# Default Cache TTLs (in seconds)
DEFAULT_CACHE_TTL = 300       # 5 minutes for general analytics & queries
STATS_CACHE_TTL = 600         # 10 minutes for aggregate stats
PLAYLISTS_CACHE_TTL = 900     # 15 minutes for playlists
AUDIENCE_CACHE_TTL = 1800     # 30 minutes for demographic / audience breakdowns
REPORTING_CACHE_TTL = 600     # 10 minutes for reporting jobs and listings

ALL_YOUTUBE_DOMAINS: tuple[str, ...] = (
    "yt-videos",
    "yt-stats",
    "yt-traffic",
    "yt-live",
    "yt-live-video",
    "yt-live-sync-status",
    "yt-achievements",
    "yt-playlists",
    "yt-playlist-videos",
    "yt-audience-insights",
    "yt-reporting",
    "yt-strategy",
    "yt-roadmap",
    "yt-ai-analysis",
    "yt-own-stats",
    "yt-prospect",
    # Bumped by app.celery_tasks.competitor_task but previously missing here,
    # so a global flush silently left stale competitor data behind.
    "yt-competitors",
)


# ── Key Builders ──────────────────────────────────────────────────────────────


async def get_domain_key(user_id: str, domain: str, *parts: str) -> str:
    """Build a versioned, user-scoped Redis key using the user's current epoch for this domain."""
    epoch = await get_epoch(user_id, domain)
    return uk(user_id, domain, str(epoch), *parts)


def get_domain_key_sync(user_id: str, domain: str, *parts: str) -> str:
    """Synchronous version of get_domain_key for Celery workers and synchronous services."""
    try:
        raw = scache().get(uk(user_id, domain, "epoch"))
        epoch = int(raw or 0)
    except Exception:
        epoch = 0
    return uk(user_id, domain, str(epoch), *parts)


# ── Async Cache Access (FastAPI Router Path) ───────────────────────────────────


async def get_cached(user_id: str, domain: str, *parts: str) -> Any | None:
    """Fetch and deserialize JSON payload from Redis cache."""
    try:
        key = await get_domain_key(user_id, domain, *parts)
        raw = await acache().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("[REDIS CACHE GET ERROR] user=%s domain=%s: %s", user_id, domain, exc)
        return None


async def set_cached(
    user_id: str,
    domain: str,
    data: Any,
    *parts: str,
    ttl: int = DEFAULT_CACHE_TTL,
) -> None:
    """Serialize and store JSON payload in Redis cache."""
    try:
        key = await get_domain_key(user_id, domain, *parts)
        payload = json.dumps(data, default=str)
        await acache().setex(key, ttl, payload)
    except Exception as exc:
        logger.warning("[REDIS CACHE SET ERROR] user=%s domain=%s: %s", user_id, domain, exc)


async def flush_youtube_cache(
    user_id: str,
    domains: Sequence[str] | None = None,
) -> None:
    """Invalidate cached YouTube data for a user by bumping the epoch for all or selected domains."""
    target_domains = domains or ALL_YOUTUBE_DOMAINS
    for domain in target_domains:
        try:
            await bump_epoch(user_id, domain)
        except Exception as exc:
            logger.warning("[REDIS CACHE FLUSH ERROR] user=%s domain=%s: %s", user_id, domain, exc)


# ── Sync Cache Access (Celery & Sync Service Path) ─────────────────────────────


def get_cached_sync(user_id: str, domain: str, *parts: str) -> Any | None:
    """Synchronous fetch and deserialize JSON payload from Redis cache."""
    try:
        key = get_domain_key_sync(user_id, domain, *parts)
        raw = scache().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("[REDIS SYNC CACHE GET ERROR] user=%s domain=%s: %s", user_id, domain, exc)
        return None


def set_cached_sync(
    user_id: str,
    domain: str,
    data: Any,
    *parts: str,
    ttl: int = DEFAULT_CACHE_TTL,
) -> None:
    """Synchronous serialize and store JSON payload in Redis cache."""
    try:
        key = get_domain_key_sync(user_id, domain, *parts)
        payload = json.dumps(data, default=str)
        scache().setex(key, ttl, payload)
    except Exception as exc:
        logger.warning("[REDIS SYNC CACHE SET ERROR] user=%s domain=%s: %s", user_id, domain, exc)


def flush_youtube_cache_sync(
    user_id: str,
    domains: Sequence[str] | None = None,
) -> None:
    """Synchronous invalidate cached YouTube data for a user by bumping domain epochs."""
    target_domains = domains or ALL_YOUTUBE_DOMAINS
    for domain in target_domains:
        try:
            bump_epoch_sync(user_id, domain)
        except Exception as exc:
            logger.warning("[REDIS SYNC CACHE FLUSH ERROR] user=%s domain=%s: %s", user_id, domain, exc)
