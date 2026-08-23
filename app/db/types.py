"""
Column types that bridge Postgres' strict date handling to the app's ISO strings.

SQLite accepted ``'2026-01-01'`` for a date column and handed it back verbatim.
Postgres does not: asyncpg rejects a ``str`` bound to ``DATE`` or ``TIMESTAMPTZ``
outright. The application passes ISO strings from end to end — Pydantic request
models, the Next.js client, the Google Calendar service — so rather than rewrite
every call site, the coercion lives in the column type.

The columns are still real ``DATE`` / ``TIMESTAMPTZ`` in the database, which is
what makes ``scheduled_date < current_date`` and ``ORDER BY created_at`` correct
rather than lexicographic. Only the Python boundary is forgiving.

Results are converted back to ISO strings by :func:`app.db._util.row_to_dict`,
preserving the contract callers were already written against.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime
from sqlalchemy.types import TypeDecorator


class IsoDate(TypeDecorator):
    """``DATE`` that also accepts ``'YYYY-MM-DD'`` strings on bind."""

    impl = Date
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            if not value.strip():
                return None
            # Tolerate a full timestamp where a date is expected.
            return date.fromisoformat(value.strip()[:10])
        raise TypeError(f"Cannot bind {type(value).__name__} to a DATE column")


class IsoDateTime(TypeDecorator):
    """``TIMESTAMPTZ`` that also accepts ISO-8601 strings on bind.

    Naive input is read as UTC. The old schema stored ``datetime('now')``, which
    was naive UTC, so this keeps previously-written timestamps meaning the same
    thing.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        if isinstance(value, str):
            if not value.strip():
                return None
            raw = value.strip().replace("Z", "+00:00").replace(" ", "T", 1)
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        raise TypeError(f"Cannot bind {type(value).__name__} to a TIMESTAMPTZ column")
