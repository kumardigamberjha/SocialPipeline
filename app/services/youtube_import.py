"""
Bulk import of YouTube Studio CSV exports.

Reads the ``data/Youtube`` folder (Content* and Traffic source* exports) and
upserts them into the analytics tables for **one** user. The import is scoped
to a ``user_id``: both destination tables are now keyed per tenant, so an
unscoped import would have written one user's Studio export over everyone's.

Synchronous by design — it is filesystem- and CPU-bound, and the only callers
are a Celery task and a threadpooled endpoint.
"""

import csv
import glob
import os
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.sync_session import sync_session_scope
from app.db.tables import YoutubePublishedVideo, YoutubeTrafficSource

BASE_DIR = "./data/Youtube"


def parse_date(date_str: str) -> str | None:
    """Parse a YouTube date ('Jan 3, 2023') into ISO 8601 (YYYY-MM-DD).

    Returns None on an unparseable value. The previous version returned an
    ``"ERR:..."`` marker string, which then got stored verbatim in the
    publish_time column; Postgres rejects that outright rather than silently
    keeping garbage.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_duration(duration_str: str) -> int:
    """Parse a duration in HH:MM:SS, MM:SS or plain seconds."""
    if not duration_str:
        return 0
    try:
        if ":" in duration_str:
            parts = duration_str.split(":")
            if len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
        return int(float(duration_str))
    except ValueError:
        return 0


def _int(row: dict, key: str) -> int:
    raw = row.get(key)
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def _float(row: dict, key: str) -> float:
    raw = row.get(key)
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def _table_rows(pattern: str):
    """Yield CSV rows from every ``<pattern>*/Table data.csv`` under BASE_DIR."""
    for directory in glob.glob(os.path.join(BASE_DIR, f"{pattern}*")):
        csv_file = os.path.join(directory, "Table data.csv")
        if not os.path.exists(csv_file):
            continue
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            yield from csv.DictReader(f)


def import_youtube_data(user_id: str) -> dict:
    """Import the CSV exports into ``user_id``'s analytics tables."""
    if not os.path.exists(BASE_DIR):
        return {"status": "error", "message": "Youtube data directory not found"}

    videos_upserted = 0
    sources_upserted = 0

    with sync_session_scope() as session:
        # -- Content export -> youtube_published_videos --
        for row in _table_rows("Content"):
            video_id = row.get("Content")
            if not video_id or video_id == "Total":
                continue

            stmt = pg_insert(YoutubePublishedVideo).values(
                user_id=user_id,
                video_id=video_id,
                title=row.get("Video title", ""),
                publish_time=parse_date(row.get("Video publish time", "")),
                duration_seconds=parse_duration(row.get("Duration", "0")),
                views=_int(row, "Views"),
                watch_time_hours=_float(row, "Watch time (hours)"),
                subscribers=_int(row, "Subscribers"),
                impressions=_int(row, "Impressions"),
                impressions_ctr=_float(row, "Impressions click-through rate (%)"),
            )
            # GREATEST, not the CSV value: exports are cumulative and a partial
            # or older export must never walk a metric backwards.
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[
                        YoutubePublishedVideo.user_id,
                        YoutubePublishedVideo.video_id,
                    ],
                    set_={
                        "title": stmt.excluded.title,
                        "publish_time": func.coalesce(
                            stmt.excluded.publish_time,
                            YoutubePublishedVideo.publish_time,
                        ),
                        "duration_seconds": func.coalesce(
                            stmt.excluded.duration_seconds,
                            YoutubePublishedVideo.duration_seconds,
                        ),
                        "views": func.greatest(
                            YoutubePublishedVideo.views, stmt.excluded.views
                        ),
                        "watch_time_hours": func.greatest(
                            YoutubePublishedVideo.watch_time_hours,
                            stmt.excluded.watch_time_hours,
                        ),
                        "subscribers": func.greatest(
                            YoutubePublishedVideo.subscribers,
                            stmt.excluded.subscribers,
                        ),
                        "impressions": func.greatest(
                            YoutubePublishedVideo.impressions,
                            stmt.excluded.impressions,
                        ),
                        "impressions_ctr": func.greatest(
                            YoutubePublishedVideo.impressions_ctr,
                            stmt.excluded.impressions_ctr,
                        ),
                        "imported_at": func.now(),
                    },
                )
            )
            videos_upserted += 1

        # -- Traffic source export -> youtube_traffic_sources --
        for row in _table_rows("Traffic source"):
            source = row.get("Traffic source")
            if not source or source == "Total":
                continue

            stmt = pg_insert(YoutubeTrafficSource).values(
                user_id=user_id,
                traffic_source=source,
                views=_int(row, "Views"),
                watch_time_hours=_float(row, "Watch time (hours)"),
                avg_view_duration=row.get("Average view duration", ""),
                impressions=_int(row, "Impressions"),
                impressions_ctr=_float(row, "Impressions click-through rate (%)"),
            )
            session.execute(
                stmt.on_conflict_do_update(
                    # The upsert target is the per-user unique constraint; the
                    # old schema made traffic_source globally unique, so two
                    # users' imports collided on it.
                    index_elements=[
                        YoutubeTrafficSource.user_id,
                        YoutubeTrafficSource.traffic_source,
                    ],
                    set_={
                        "views": func.greatest(
                            YoutubeTrafficSource.views, stmt.excluded.views
                        ),
                        "watch_time_hours": func.greatest(
                            YoutubeTrafficSource.watch_time_hours,
                            stmt.excluded.watch_time_hours,
                        ),
                        "avg_view_duration": func.coalesce(
                            stmt.excluded.avg_view_duration,
                            YoutubeTrafficSource.avg_view_duration,
                        ),
                        "impressions": func.greatest(
                            YoutubeTrafficSource.impressions,
                            stmt.excluded.impressions,
                        ),
                        "impressions_ctr": func.greatest(
                            YoutubeTrafficSource.impressions_ctr,
                            stmt.excluded.impressions_ctr,
                        ),
                        "imported_at": func.now(),
                    },
                )
            )
            sources_upserted += 1

    return {
        "status": "success",
        "videos_imported": videos_upserted,
        "traffic_sources_imported": sources_upserted,
    }
