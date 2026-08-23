"""
Synchronous database engine and session factory (the Celery path).

Celery tasks are plain synchronous callables. Driving the asyncpg engine from
them would mean an ``asyncio.run()`` per task — a fresh event loop and a fresh
connection pool for every unit of work, with the pool discarded immediately
after. This module gives workers a normal psycopg pool instead.

Both engines point at the same database; only the driver differs (see
``Settings.sync_database_url``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        echo=settings.db_echo,
        # Workers are configured with a low concurrency and long tasks, so a
        # small pool is right; a large one just holds Postgres slots idle.
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache(maxsize=1)
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_sync_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


@contextmanager
def sync_session_scope() -> Iterator[Session]:
    """Transactional session for a Celery task.

    Long tasks should use several short scopes rather than holding one open for
    their whole duration — a transaction kept open across a multi-minute LLM
    call pins a connection and blocks vacuum.
    """
    session = get_sync_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_sync_engine() -> None:
    if get_sync_engine.cache_info().currsize:
        get_sync_engine().dispose()
        logger.info("Sync database connection pool disposed.")
