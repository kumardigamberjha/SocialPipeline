"""
Shared Redis clients and key namespacing.

Two instances, deliberately:

* **cache** (``REDIS_CACHE_URL``) — ``allkeys-lru``. Analytics and AI payloads.
  Losing one costs a recompute.
* **state** (``REDIS_STATE_URL``) — ``noeviction``, AOF-persisted. The auth
  revocation denylist, WebSocket tickets and job pub/sub. Losing an entry here
  costs *correctness*: an evicted denylist key silently un-revokes a token that
  was logged out.

Never put state on the cache instance, and never call ``Redis.from_url``
elsewhere. Before this module, four call sites each opened a brand-new
connection on *every* get and set — one page load cost ten TCP handshakes.
Connections are pooled here and reused.

Key namespacing
---------------
Every key is built with :func:`uk` (user-scoped) or :func:`gk` (deliberately
global). Under the previous free-form keys, ``yt:stats:28d`` was shared by every
tenant, so one user's analytics were served to another. ``uk`` makes the owner
part of the key by construction rather than by remembering.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Bumping this orphans every previously-written key. It was bumped to v1 when
# keys became user-scoped, so no pre-existing unscoped key could be served to
# the wrong tenant after the upgrade.
NAMESPACE = "nx:v1"

_POOL_KWARGS = dict(
    decode_responses=True,
    max_connections=50,
    socket_connect_timeout=2,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,
)


# ── Key builders ──────────────────────────────────────────────────────────────


def uk(user_id: str, *parts: str) -> str:
    """User-scoped key: ``nx:v1:u:{user_id}:...``."""
    if not user_id:
        raise ValueError("uk() requires a user_id; use gk() for global keys")
    return ":".join((NAMESPACE, "u", str(user_id), *parts))


def gk(*parts: str) -> str:
    """Deliberately global key: ``nx:v1:g:...``.

    Only for data that is genuinely not tenant-specific — public web-search
    results, for instance. Using this is a security decision.
    """
    return ":".join((NAMESPACE, "g", *parts))


def auth_key(*parts: str) -> str:
    """Auth-state key on the *state* instance: ``nx:v1:auth:...``."""
    return ":".join((NAMESPACE, "auth", *parts))


# ── Clients ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _async_cache_pool() -> aioredis.ConnectionPool:
    return aioredis.ConnectionPool.from_url(
        get_settings().redis_cache_url, **_POOL_KWARGS
    )


@lru_cache(maxsize=1)
def _async_state_pool() -> aioredis.ConnectionPool:
    return aioredis.ConnectionPool.from_url(
        get_settings().redis_state_url, **_POOL_KWARGS
    )


@lru_cache(maxsize=1)
def _sync_cache_pool() -> redis.ConnectionPool:
    return redis.ConnectionPool.from_url(
        get_settings().redis_cache_url, **_POOL_KWARGS
    )


@lru_cache(maxsize=1)
def _sync_state_pool() -> redis.ConnectionPool:
    return redis.ConnectionPool.from_url(
        get_settings().redis_state_url, **_POOL_KWARGS
    )


def acache() -> aioredis.Redis:
    """Async client for the evictable analytics cache (API path)."""
    return aioredis.Redis(connection_pool=_async_cache_pool())


def astate() -> aioredis.Redis:
    """Async client for durable auth/job state (API path)."""
    return aioredis.Redis(connection_pool=_async_state_pool())


def scache() -> redis.Redis:
    """Sync client for the evictable analytics cache (Celery path)."""
    return redis.Redis(connection_pool=_sync_cache_pool())


def sstate() -> redis.Redis:
    """Sync client for durable auth/job state (Celery path)."""
    return redis.Redis(connection_pool=_sync_state_pool())


# ── Lifecycle / health ────────────────────────────────────────────────────────


async def close_redis() -> None:
    """Release pooled connections. Called from the app lifespan on shutdown."""
    for pool_fn in (_async_cache_pool, _async_state_pool):
        if pool_fn.cache_info().currsize:
            await pool_fn().disconnect()
    for pool_fn in (_sync_cache_pool, _sync_state_pool):
        if pool_fn.cache_info().currsize:
            pool_fn().disconnect()
    logger.info("Redis connection pools closed.")


async def check_connection() -> dict[str, bool]:
    """Liveness probe for both instances, for the health endpoint."""
    result = {}
    for name, client in (("cache", acache()), ("state", astate())):
        try:
            await client.ping()
            result[name] = True
        except Exception as exc:  # pragma: no cover - reported, not raised
            logger.warning("Redis %s health check failed: %s", name, exc)
            result[name] = False
    return result


# ── Cache-generation helper ───────────────────────────────────────────────────


async def bump_epoch(user_id: str, domain: str) -> int:
    """Invalidate a user's cached ``domain`` data in O(1).

    Callers fold the returned epoch into their keys, so a bump makes every
    previous key unreachable and lets it die on its own TTL. This replaces
    ``KEYS <pattern>`` + ``DELETE``, which scans the entire keyspace and blocks
    Redis for every other client while it runs.
    """
    return await acache().incr(uk(user_id, domain, "epoch"))


async def get_epoch(user_id: str, domain: str) -> int:
    raw = await acache().get(uk(user_id, domain, "epoch"))
    return int(raw or 0)


def bump_epoch_sync(user_id: str, domain: str) -> int:
    """Sync twin of :func:`bump_epoch`, for Celery tasks (no event loop)."""
    return scache().incr(uk(user_id, domain, "epoch"))
