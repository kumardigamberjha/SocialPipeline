"""User-local dates — the single source of truth for "today".

Three different notions of "today" coexist in this codebase and disagree by 5h30m
whenever the process runs in a UTC container:

* Python ``date.today()`` — server-local (``db/queries.py`` board plans,
  ``saved_topic_service``, ``roadmap_to_plan``, the analytics routers)
* Postgres ``func.current_date()`` — the *database session's* timezone
  (``get_planner_analytics``'s overdue/upcoming counts)
* Asia/Kolkata — what Google Calendar events are actually written in
  (``services/google_calendar.py``)

Between 00:00 and 05:30 IST those answers differ by a full day. That was
survivable while every feature phrased dates relative to rows the user was
already looking at; it is not survivable for an assistant whose entire job is
answering "aaj kya post karna hai?".

This module introduces the correct one. It deliberately does **not** retrofit the
existing call sites — that is a separate change with its own blast radius, and
folding it into a chat feature would make neither reviewable. The one exception is
``get_planner_analytics``, which grew an optional ``today`` parameter so the
assistant can pass an IST-anchored date without altering any existing caller.

There is no ``user_id`` parameter anywhere here on purpose: per-user timezone is
not modelled in ``users`` or in settings — ``default_timezone`` is process-global.
Naming these ``user_today()`` rather than ``today_for_user(user_id)`` avoids
implying a per-tenant setting that does not exist. If per-user timezones ever
land, this is the one module that changes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings

# The widest range a single question may scan. "saara schedule dikha" must not
# turn into a two-year sequential scan.
MAX_RANGE_DAYS = 62


def user_tz() -> ZoneInfo:
    """The configured display timezone (default Asia/Kolkata).

    Falls back to UTC rather than raising: a typo'd IANA name should degrade the
    assistant's date arithmetic, not take down every request that touches it.
    """
    name = get_settings().default_timezone or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def user_now() -> datetime:
    """Timezone-aware 'now' in the user's timezone."""
    return datetime.now(user_tz())


def user_today() -> date:
    """Today's date as the user experiences it.

    Callers should invoke this **once** per request and thread the result, so a
    request that straddles local midnight stays internally consistent.
    """
    return user_now().date()


def user_today_iso() -> str:
    return user_today().isoformat()


def week_bounds(d: date, week_start: int = 0) -> tuple[date, date]:
    """The (Monday, Sunday) week containing ``d``.

    ``week_start`` is a ``date.weekday()`` value — 0 is Monday, 6 is Sunday.
    """
    offset = (d.weekday() - week_start) % 7
    start = d - timedelta(days=offset)
    return start, start + timedelta(days=6)


def month_bounds(d: date) -> tuple[date, date]:
    """The (first, last) day of the calendar month containing ``d``."""
    start = d.replace(day=1)
    # The 28th of next month is always in next month; back up to this month's end.
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def clamp_range(
    date_from: date, date_to: date, max_days: int = MAX_RANGE_DAYS
) -> tuple[date, date]:
    """Normalise a requested range: order it, then cap its span.

    An inverted range is swapped rather than rejected — a model that emits
    ``date_from > date_to`` still told us which two days it meant.
    """
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > max_days:
        date_to = date_from + timedelta(days=max_days)
    return date_from, date_to


def parse_iso_date(value: str | None) -> date | None:
    """Tolerant ISO-date parse. Returns None for anything unparseable.

    Used on the boundary where LLM output becomes a query parameter: a bad value
    must degrade to "no filter", never raise out of the query layer.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None
