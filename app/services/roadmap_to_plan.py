"""
Turns YouTube roadmap items into scheduled content-plan items.

A roadmap item already carries everything a plan item needs (title, format,
theme, rationale, a rough date) — what it lacks is a *schedule*. This module
supplies that, using four rules:

1. Publish on the weekdays that actually perform for THIS channel, measured from
   youtube_published_videos rather than guessed.
2. Work on it before it goes live: scheduled_date = publish_date - lead time,
   shorter for Shorts than for full videos.
3. Don't stack same-format videos back to back, and never double-book a date
   another item in the plan already owns.
4. Skip anything already planned or already published.

With strategic=False only rules 3 and 4 apply and the roadmap's own dates are
kept, which is the escape hatch when the channel has too little history to have
a meaningful "best weekday".
"""

import logging
import re
from datetime import date, datetime, timedelta

from app.db import content_tracker
from sqlalchemy import select

from app.db.sync_session import sync_session_scope
from app.db.tables import YoutubePublishedVideo

logger = logging.getLogger(__name__)

# Days between working on a video and publishing it. Shorts turn around faster.
LEAD_DAYS = {"full": 5, "short": 2}

# Below this many dated videos the weekday averages are noise, so we fall back
# to the roadmap's own dates.
MIN_HISTORY_VIDEOS = 8

# A weekday needs at least this many videos before it can win.
MIN_VIDEOS_PER_WEEKDAY = 2

DEFAULT_EVENT_TIME = "09:00"

# How far forward a collision may push an item before we give up and accept a
# duplicate date (guards against an infinite walk on a very full plan).
MAX_SLOT_SEARCH_DAYS = 120


def covered_topics(existing_items: list[dict]) -> set[str]:
    """Normalised topics already sitting in a plan — the seed for `skip_reason`."""
    return {
        content_tracker.normalize_topic(item["topic"])
        for item in existing_items
        if item.get("topic")
    }


def skip_reason(title: str, seen: set[str]) -> str | None:
    """Why `title` should not be added, or None when it is genuinely new.

    On acceptance the normalised title is added to `seen`, so a single batch
    cannot duplicate within itself. Shared by the YouTube scheduler below and
    the Instagram roadmap → plan endpoint, which need identical semantics.
    """
    norm = content_tracker.normalize_topic(title)
    if norm in seen:
        return "already in plan"
    try:
        duplicate, _score = content_tracker.is_duplicate_topic(title)
    except Exception:  # tracker DB is best-effort
        duplicate = False
    if duplicate:
        return "already published"
    seen.add(norm)
    return None


def _to_video_format(fmt: str) -> str:
    """Roadmap 'format' is free text ('YouTube Short', '12-min tutorial', …).
    Same short/full convention the playlist trends UI uses."""
    return "short" if re.search(r"shorts?", fmt or "", re.IGNORECASE) else "full"


def channel_publish_profile(user_id: str) -> dict:
    """Best-performing publish weekdays for the channel, from its own history.

    Scoped to ``user_id`` — this used to read every tenant's publish history and
    derive one user's posting schedule from another's channel.

    Returns {"weekdays": [0-6 …] | None, "event_time": "HH:MM", "source": …}
    where weekday 0 is Monday. weekdays is None when there is too little data.
    """
    profile = {"weekdays": None, "event_time": DEFAULT_EVENT_TIME, "source": "roadmap_dates"}
    try:
        with sync_session_scope() as session:
            rows = session.execute(
                select(
                    YoutubePublishedVideo.publish_time,
                    YoutubePublishedVideo.views,
                ).where(
                    YoutubePublishedVideo.user_id == user_id,
                    YoutubePublishedVideo.publish_time.is_not(None),
                )
            ).all()
    except Exception:
        logger.exception("Could not read publish history; falling back to roadmap dates")
        return profile

    stats: dict[int, list[int]] = {}
    hours: list[int] = []
    for row in rows:
        stamp = row.publish_time
        if stamp is None:
            continue
        stats.setdefault(stamp.weekday(), []).append(row.views or 0)
        # The CSV export usually carries date only; keep the hour when it isn't.
        if stamp.hour or stamp.minute:
            hours.append(stamp.hour)

    if sum(len(v) for v in stats.values()) < MIN_HISTORY_VIDEOS:
        return profile

    ranked = sorted(
        ((wd, sum(v) / len(v)) for wd, v in stats.items() if len(v) >= MIN_VIDEOS_PER_WEEKDAY),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if not ranked:
        return profile

    profile["weekdays"] = sorted(wd for wd, _ in ranked[:2])
    profile["source"] = "channel_data"
    if hours:
        profile["event_time"] = f"{round(sum(hours) / len(hours)):02d}:00"
    return profile


def _next_allowed(day: date, weekdays: list[int] | None) -> date:
    """First date on/after `day` whose weekday is allowed."""
    if not weekdays:
        return day
    for offset in range(7):
        candidate = day + timedelta(days=offset)
        if candidate.weekday() in weekdays:
            return candidate
    return day


def _rebalance_formats(items: list[dict]) -> list[dict]:
    """Reorder so no more than two consecutive items share a video_format.

    Relative order within each format is preserved, so the roadmap's week
    sequencing still shows through.
    """
    queues = {"full": [i for i in items if i["video_format"] == "full"],
              "short": [i for i in items if i["video_format"] == "short"]}
    ordered: list[dict] = []
    run_format, run_length = None, 0
    while queues["full"] or queues["short"]:
        other = "short" if run_format == "full" else "full"
        if run_length >= 2 and queues[other]:
            pick = other                       # break a run of two
        elif run_format and queues[run_format]:
            pick = run_format
        else:
            # Start (or restart) on whichever format has more left to place.
            pick = "full" if len(queues["full"]) >= len(queues["short"]) else "short"
        if not queues[pick]:
            pick = other
        ordered.append(queues[pick].pop(0))
        run_length = run_length + 1 if pick == run_format else 1
        run_format = pick
    return ordered


def _taken_dates(existing_items: list[dict]) -> set[str]:
    taken: set[str] = set()
    for item in existing_items:
        for key in ("publish_date", "scheduled_date"):
            if item.get(key):
                taken.add(item[key])
    return taken


def schedule_items(user_id: str, raw_items: list[dict], existing_items: list[dict],
                   strategic: bool = True, today: date | None = None,
                   source_label: str = "YouTube") -> tuple[list[dict], list[dict], dict]:
    """Map roadmap items onto plan-item kwargs.

    Returns (scheduled, skipped, profile) where `scheduled` entries are ready to
    hand to queries.create_plan_item and `skipped` entries are {title, reason}.

    ``source_label`` only names the roadmap in each item's notes — the Instagram
    caller passes "Instagram" so its cards don't claim to come from YouTube.
    """
    today = today or date.today()
    profile = channel_publish_profile(user_id) if strategic else {
        "weekdays": None, "event_time": DEFAULT_EVENT_TIME, "source": "roadmap_dates",
    }
    weekdays = profile["weekdays"] if strategic else None

    # ── Rule 4: drop anything already planned or already published ───────────
    seen = covered_topics(existing_items)
    candidates, skipped = [], []
    for raw in raw_items:
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        reason = skip_reason(title, seen)
        if reason:
            skipped.append({"title": title, "reason": reason})
            continue
        candidates.append({
            "topic": title,
            "video_format": _to_video_format(raw.get("format")),
            "theme": (raw.get("theme") or "").strip(),
            "rationale": (raw.get("rationale") or "").strip(),
            "week_number": raw.get("week_number"),
            "roadmap_date": raw.get("date"),
        })

    if not candidates:
        return [], skipped, profile

    # ── Rules 2+3: order, then walk forward date by date ─────────────────────
    candidates.sort(key=lambda c: (c["week_number"] or 0))
    if strategic:
        candidates = _rebalance_formats(candidates)

    taken = _taken_dates(existing_items)
    scheduled: list[dict] = []
    cursor = today
    for item in candidates:
        anchor = item["roadmap_date"] or cursor.isoformat()
        try:
            anchor_date = date.fromisoformat(str(anchor)[:10])
        except ValueError:
            anchor_date = cursor
        publish = _next_allowed(max(anchor_date, cursor), weekdays)

        searched = 0
        while publish.isoformat() in taken and searched < MAX_SLOT_SEARCH_DAYS:
            publish = _next_allowed(publish + timedelta(days=1), weekdays)
            searched += 1
        taken.add(publish.isoformat())

        lead = LEAD_DAYS.get(item["video_format"], LEAD_DAYS["full"])
        work_on = max(publish - timedelta(days=lead), today)

        source_line = f"From {source_label} roadmap"
        if item["week_number"]:
            source_line += f" (week {item['week_number']})"
        note_lines = [line for line in (
            item["rationale"],
            f"Theme: {item['theme']}" if item["theme"] else "",
            source_line,
        ) if line]

        scheduled.append({
            "topic": item["topic"],
            "scheduled_date": work_on.isoformat(),
            "publish_date": publish.isoformat(),
            "notes": "\n\n".join(note_lines),
            "topic_source": "ai",
            "video_format": item["video_format"],
            "event_time": profile["event_time"],
        })
        # Next item starts the day after this one publishes.
        cursor = publish + timedelta(days=1)

    return scheduled, skipped, profile
