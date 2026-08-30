"""Milestone ladder and monthly-history maths, shared by every platform.

This started inside ``youtube_achievements_service`` and is platform-agnostic:
a rung ladder, the "which rung has this number passed" lookup, display
formatting, and the two facts a monthly series can support — *when* a running
total first crossed a rung, and *how fast* it is still growing.

The rule the whole module is built around is the one
``goal_service.read_metric`` states: **a metric with no source returns None, not
a plausible-looking number.** Nothing here invents a value to fill a gap —
``monthly_rate`` returns None for a flat channel rather than a zero rate, and
``eta_for`` returns None rather than a date derived from one.
"""

from __future__ import annotations

from datetime import date, datetime

MONTHS_FOR_RATE = 6      # trailing window the pace projection averages over
MAX_ETA_MONTHS = 600     # past ~50 years, say nothing rather than print a date


# ── Milestone ladder ─────────────────────────────────────────────────────────

# Multiples of 0.5 per decade (e.g. 500, 1000, 1500, 2000, 2500, 3000, 3500...
# or 5K, 10K, 15K, 20K, 25K... or 5, 10, 15, 20, 25...).
_LADDER_STEPS = tuple(round(i * 0.5, 1) for i in range(1, 20))
_LADDER_MIN_EXP = 1     # start the ladder at 5
_LADDER_MAX_EXP = 11    # …and stop at 50 billion


def ladder() -> list[float]:
    """Every milestone rung, ascending."""
    rungs = {
        round(step * (10 ** exp), 2)
        for exp in range(_LADDER_MIN_EXP, _LADDER_MAX_EXP)
        for step in _LADDER_STEPS
    }
    return sorted(rungs)


def rungs_for(value: float) -> tuple[float | None, float | None]:
    """The largest rung ``value`` has passed and the smallest it has not.

    Returns ``(None, first_rung)`` for an account below the bottom of the
    ladder, so a new account gets a goal to aim at rather than a fake
    achievement.
    """
    achieved = next_up = None
    for rung in ladder():
        if rung <= value:
            achieved = rung
        else:
            next_up = rung
            break
    return achieved, next_up


# ── Display ──────────────────────────────────────────────────────────────────


def format_label(value: float | None) -> str:
    """Compact display label: 1500 -> '1.5K', 183616 -> '183.6K', 402 -> '402'."""
    if value is None:
        return ""
    for cutoff, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(value) >= cutoff:
            scaled = value / cutoff
            # 1.5K keeps its decimal; 150K does not need one.
            text_ = f"{scaled:.1f}".rstrip("0").rstrip(".")
            return f"{text_}{suffix}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _ordinal(day: int) -> str:
    # 11th/12th/13th are the exceptions the naive %10 rule gets wrong.
    if 11 <= day <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def format_full_date(value: date) -> str:
    """'5th January 2025' — the display contract the cards already expect."""
    return f"{_ordinal(value.day)} {value.strftime('%B %Y')}"


def format_month(month_key: str) -> str:
    """'2023-04' -> 'April 2023'."""
    try:
        return datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return month_key


# ── Derived facts ────────────────────────────────────────────────────────────


def series_values(series: list[dict], key: str) -> list[tuple[str, float]]:
    """(month, value) pairs for one metric, skipping months it cannot measure."""
    return [
        (row["month"], float(row[key]))
        for row in series
        if row.get(key) is not None
    ]


def achieved_month(series: list[dict], key: str, rung: float) -> str | None:
    """The month a running total first reached ``rung``, or None if never."""
    running = 0.0
    for month, value in series_values(series, key):
        running += value
        if running >= rung:
            return month
    return None


def monthly_rate(series: list[dict], key: str) -> float | None:
    """Mean monthly gain over the trailing window, or None if not growing.

    A flat or shrinking account gets no projection at all — printing a date
    derived from a zero rate is how the old page ended up promising "9th August
    2028".
    """
    values = [v for _, v in series_values(series, key)][-MONTHS_FOR_RATE:]
    if not values:
        return None
    rate = sum(values) / len(values)
    return rate if rate > 0 else None


def eta_for(remaining: float, rate: float | None) -> str | None:
    """Formatted date by which ``remaining`` is closed at ``rate`` per month."""
    if not rate or remaining <= 0:
        return None
    months = remaining / rate
    if months > MAX_ETA_MONTHS:
        return None
    target = date.today()
    total = target.month - 1 + int(round(months))
    year, month = target.year + total // 12, total % 12 + 1
    try:
        return format_full_date(target.replace(year=year, month=month))
    except ValueError:  # e.g. 31st landing on a short month
        return format_full_date(date(year, month, 28))
