"""
Async database engine and session factory (the API path).

Replaces the thread-local ``sqlite3`` connection in the old
``app/db/database.py``. Two things change materially:

* Sessions are request-scoped and handed out by a FastAPI dependency, rather
  than fetched ad-hoc from a module-level global, so a request either commits
  as a unit or rolls back as a unit. The old connection ran in autocommit
  (``isolation_level=None``), which meant a handler that failed halfway left
  its earlier writes behind.
* Nothing blocks the event loop. Celery workers do not use this module — see
  ``app/db/sync_session.py``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """The process-wide async engine.

    Cached rather than created at import so that tests can override settings
    before the first connection is made.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # Cloudflare tunnels and container restarts leave stale sockets in the
        # pool; without pre-ping the first query after an idle period fails.
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        # Attributes stay readable after commit, so a handler can return the
        # object it just wrote without triggering a lazy reload on a closed
        # session (which raises MissingGreenlet under asyncio).
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session.

    Commits on success, rolls back on any exception. Handlers should not commit
    themselves unless they need a savepoint boundary mid-request.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for code outside the request cycle (lifespan, scripts, WS loops).

    Same commit/rollback contract as :func:`get_session`, usable with ``async
    with`` instead of ``Depends``.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close every pooled connection. Called from the app lifespan on shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        logger.info("Database connection pool disposed.")


async def check_connection() -> bool:
    """Cheap liveness probe for the health endpoint."""
    from sqlalchemy import text as _text

    try:
        async with get_engine().connect() as conn:
            await conn.execute(_text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - reported, not raised
        logger.warning("Database health check failed: %s", exc)
        return False
