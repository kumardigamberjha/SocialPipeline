"""
Helpers shared by the async (:mod:`app.db.queries`) and sync
(:mod:`app.db.sync_queries`) query layers.

Nothing here performs I/O, so it is safe to import from either side.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from datetime import date, datetime

from sqlalchemy import Row

from app.db.base import Base

# Average adult reads ~238 words per minute (Brysbaert, 2019 meta-analysis).
WORDS_PER_MINUTE = 238

# Sentinel distinguishing "clear this column" (None) from "leave it alone"
# (argument omitted). A plain None default cannot express both.
UNSET: Any = object()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def _iso(value: Any) -> Any:
    """Render dates/datetimes as ISO strings.

    The pre-Postgres layer returned whatever SQLite stored, which was always an
    ISO string. Pydantic accepts an ISO string for ``str``, ``date`` and
    ``datetime`` fields alike, and the app declares all three across its
    response models — so emitting strings keeps every one of them working.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _entity_to_dict(obj: Base) -> dict:
    return {c.key: _iso(getattr(obj, c.key)) for c in obj.__table__.columns}


def row_to_dict(row: Row | None) -> dict | None:
    """Map a result row to a plain dict, or None.

    Callers across the app expect dicts (they came from ``sqlite3.Row``), so the
    query layer keeps returning dicts rather than ORM instances. That also keeps
    results detached from the session — no lazy loads after it closes.

    ``select(Model)`` and ``.returning(Model)`` produce a row holding a single
    ORM *entity*, not its columns, so those are expanded here. Doing it in one
    place means query functions can be written the readable way
    (``select(BlogPost)``) instead of spelling out every column, and mixed rows
    like ``select(ContentPlan, item_count)`` flatten correctly too.
    """
    if row is None:
        return None

    out: dict[str, Any] = {}
    for key, value in row._mapping.items():
        if isinstance(value, Base):
            out.update(_entity_to_dict(value))
        else:
            out[key] = _iso(value)
    return out


def rows_to_dicts(result) -> list[dict]:
    return [row_to_dict(r) for r in result]


def scalar_or(result, default=0):
    value = result.scalar()
    return default if value is None else value


def slugify(text: str) -> str:
    """Convert a title into a URL-safe slug: lowercase, hyphenated, ASCII-only."""
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)  # drop punctuation
    text = re.sub(r"[\s_-]+", "-", text)  # collapse whitespace/underscores
    text = text.strip("-")
    return text[:80] or "untitled-post"


def reading_time_minutes(word_count: int) -> int:
    return max(1, word_count // WORDS_PER_MINUTE)


def hashtag_count(post_text: str) -> int:
    return len(re.findall(r"#\w+", post_text or ""))
