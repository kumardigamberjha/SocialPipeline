"""Fixtures for the report-integrity suite.

The numbers here are the ones that shipped in the WillPower Star audit and were
caught by the channel owner: a recommended window the report's own table
contradicted, a breakout count larger than the list it came from, a roadmap that
cited the audit's own flagged video as a proven pillar, and a length bucket built
from one video sitting on top of the chart.

They are reproduced exactly rather than approximated, because the point of the
suite is that *these* figures can no longer produce *those* claims.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── The shipped figures ──────────────────────────────────────────────────────
CHANNEL_MEDIAN = 452_697
CHANNEL_MEAN = 744_786

MORNING_AVG = 1_027_562      # 09:00-12:00, 2.27x — the real winner
AFTERNOON_AVG = 625_091      # 12:00-15:00, 1.38x — what the report recommended
SHORT_BUCKET_VIEWS = 1_502_300   # the 1-5 min bucket, n=1, tallest bar on the chart
MESSI_VIDEO = "I Found A Neuroscience Paper On Messi's Brain"
MESSI_VIEWS = 213_644

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def now() -> datetime:
    return NOW


def _video(vid, title, views, when, duration=1500):
    return {
        "video_id": vid,
        "title": title,
        "views": views,
        "likes": views // 60,
        "comments": views // 300,
        "duration_seconds": duration,
        "published_at": when,
    }


@pytest.fixture
def willpower_videos() -> list[dict]:
    """The catalogue, shaped so every original defect is reproducible.

    * 09:00-12:00 holds 6 uploads averaging ~1.03M (clears the 5-video floor).
    * 12:00-15:00 holds 9 uploads averaging 625,091 — more volume, less lift,
      which is exactly what beat the stronger window under the old scoring.
    * Saturday carries the top videos, so day and window agree once fixed.
    * One 1-5 min video at 1,502,300 — the whole 1-5 min bucket.
    * The Messi video, old enough to judge and far under the median.
    * One three-day-old upload that a lifetime baseline would call a failure.
    """
    vids: list[dict] = []

    # 09:00-12:00 UTC, Saturdays — the genuine peak window.
    for i, views in enumerate([1_500_000, 1_100_000, 1_027_562, 900_000, 830_000, 810_248]):
        day = NOW - timedelta(days=7 * (i + 4))
        sat = day - timedelta(days=(day.weekday() - 5) % 7)
        vids.append(_video(f"morn{i}", f"Discipline Deep Dive {i}", views,
                           sat.replace(hour=10, minute=30).isoformat()))

    # 12:00-15:00 UTC — high volume, middling performance. All well outside the
    # 21-day fresh window, so exactly one video in this catalogue is "too new to
    # judge" and the age tests have a single unambiguous subject.
    for i in range(9):
        day = NOW - timedelta(days=25 + 5 * i)
        vids.append(_video(f"aft{i}", f"Mindset Session {i}", AFTERNOON_AVG,
                           day.replace(hour=13, minute=0).isoformat()))

    # The single short video that dominated the length chart.
    vids.append(_video("short1", "Two Minute Reset", SHORT_BUCKET_VIEWS,
                       (NOW - timedelta(days=60)).replace(hour=13).isoformat(), duration=200))

    # Mature underperformers, including the one the roadmap cited back.
    vids.append(_video("messi", MESSI_VIDEO, MESSI_VIEWS,
                       (NOW - timedelta(days=95)).replace(hour=13).isoformat()))
    vids.append(_video("theory1", "The Philosophy Of Abstract Willpower", 190_000,
                       (NOW - timedelta(days=120)).replace(hour=13).isoformat()))

    # Three days old and still climbing — a lifetime baseline calls this a failure.
    vids.append(_video("fresh1", "Brand New Documentary Drop", 41_000,
                       (NOW - timedelta(days=3)).replace(hour=10, minute=30).isoformat()))

    return vids


@pytest.fixture
def willpower_metrics(willpower_videos):
    from app.services.youtube_prospect_service import compute_prospect_metrics

    return compute_prospect_metrics(
        {"title": "WillPower Star", "handle": "@willpowerstar", "subscriber_count": 2_400_000},
        willpower_videos,
    )


@pytest.fixture
def willpower_timing(willpower_videos):
    from app.services.youtube_metrics import analyze_upload_timing

    return analyze_upload_timing(willpower_videos, CHANNEL_MEDIAN)


# ── The same channel, from a feed that carries no publish times ──────────────
#
# The second timing contradiction shipped from exactly this shape: a strong,
# well-sampled day-of-week signal and not one usable hour. Page 2's widget said
# "Not enough uploads carry a publish time to recommend a time of day" and showed
# the window as "—"; page 1's Format & Cadence narrative and Strategic Priorities
# recommended "Saturday & Sunday between 09:00–12:00 UTC (2.27× channel median)".


#: Tuned so Saturday lands on the 2.98x the shipped report quoted, against the
#: 380,000 median this catalogue produces.
SATURDAY_VIEWS = (1_650_000, 1_250_000, 1_100_000, 1_020_000, 930_000, 844_400)
DATEONLY_MEDIAN = 380_000     # what compute_prospect_metrics derives from this catalogue
SATURDAY_MULTIPLIER = 2.98


def _date_only(when: datetime) -> str:
    """A YYYY-MM-DD publish date, the way a feed without timestamps reports it.

    Not a truncated ISO datetime: the point is that no hour was ever recorded,
    and ``_has_clock_time`` distinguishes the two by the missing "T".
    """
    return when.date().isoformat()


def _weekday_before(when: datetime, weekday: int) -> datetime:
    return when - timedelta(days=(when.weekday() - weekday) % 7)


@pytest.fixture
def dateonly_videos() -> list[dict]:
    """Day-of-week is strong and well sampled; time-of-day does not exist.

    * 6 Saturdays carry the catalogue — the strongest day by a distance.
    * 4 Sundays sit clearly above the median, so both days are recommended.
    * 9 Tuesdays are the volume day and sit below it.
    * The Messi video and one theory piece are mature underperformers.
    * One three-day-old upload is still climbing.
    """
    vids: list[dict] = []

    for i, views in enumerate(SATURDAY_VIEWS):
        sat = _weekday_before(NOW - timedelta(days=7 * (i + 4)), 5)
        vids.append(_video(f"sat{i}", f"Discipline Deep Dive {i}", views, _date_only(sat)))

    for i, views in enumerate([760_000, 720_000, 690_000, 655_000]):
        sun = _weekday_before(NOW - timedelta(days=14 + 9 * i), 6)
        vids.append(_video(f"sun{i}", f"Sunday Reset {i}", views, _date_only(sun)))

    for i in range(9):
        tue = _weekday_before(NOW - timedelta(days=25 + 5 * i), 1)
        vids.append(_video(f"tue{i}", f"Mindset Session {i}", 380_000, _date_only(tue)))

    wed = _weekday_before(NOW - timedelta(days=95), 2)
    vids.append(_video("messi", MESSI_VIDEO, MESSI_VIEWS, _date_only(wed)))
    vids.append(_video("theory1", "The Philosophy Of Abstract Willpower", 190_000,
                       _date_only(_weekday_before(NOW - timedelta(days=120), 2))))

    vids.append(_video("fresh1", "Brand New Documentary Drop", 41_000,
                       _date_only(NOW - timedelta(days=3))))

    return vids


@pytest.fixture
def dateonly_metrics(dateonly_videos):
    from app.services.youtube_prospect_service import compute_prospect_metrics

    return compute_prospect_metrics(
        {"title": "WillPower Star", "handle": "@willpowerstar", "subscriber_count": 2_400_000},
        dateonly_videos,
    )


@pytest.fixture
def dateonly_timing(dateonly_videos):
    from app.services.youtube_metrics import analyze_upload_timing

    return analyze_upload_timing(dateonly_videos, DATEONLY_MEDIAN)
