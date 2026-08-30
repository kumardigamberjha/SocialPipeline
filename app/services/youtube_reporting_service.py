"""
YouTube Reporting API Service — schedules reporting jobs and downloads bulk CSV data.

Provides bulk report scheduling and CSV report ingestion for:
- channel_basic_a3 (video views, watch time, shares, comments, likes)
- channel_traffic_source_a3 (bulk traffic sources breakdown)
- channel_device_os_a3 (devices and operating systems)
- channel_demographics_a1 (viewer age and gender)
- channel_playback_location_a3 (embedded vs watch page)
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.sync_session import sync_session_scope
from app.db.tables import YoutubePublishedVideo, YoutubeTrafficSource, YoutubeVideoLive
from app.services.google_calendar import (
    YOUTUBE_SCOPE,
    YT_ANALYTICS_SCOPE,
    NotConnectedError,
    connection_status,
    load_credentials,
)
from app.services.youtube_sync_service import (
    TRAFFIC_SOURCE_LABELS,
    YoutubeApiDisabled,
    YoutubeScopeMissing,
    YoutubeSyncError,
    _handle_http_error,
)

logger = logging.getLogger(__name__)

STANDARD_REPORTING_JOBS = [
    ("channel_basic_a3", "Channel Basic Report"),
    ("channel_traffic_source_a3", "Channel Traffic Source Report"),
    ("channel_device_os_a3", "Channel Device and OS Report"),
    ("channel_demographics_a1", "Channel Demographics Report"),
    ("channel_playback_location_a3", "Channel Playback Location Report"),
]


def _get_reporting_service(user_id: str):
    """Build a YouTube Reporting API v1 client for the connected user."""
    status = connection_status(user_id)
    if not status.get("connected"):
        raise NotConnectedError("Google account is not connected.")

    creds = load_credentials(user_id)
    return build("youtubereporting", "v1", credentials=creds, cache_discovery=False)


def ensure_default_jobs(user_id: str) -> list[dict]:
    """Ensure standard YouTube Reporting API bulk jobs are scheduled for this user.

    Returns the list of all active reporting jobs.
    """
    try:
        ytr = _get_reporting_service(user_id)
    except Exception as exc:
        logger.warning("Could not build YouTube Reporting service for user %s: %s", user_id, exc)
        return []

    try:
        resp = ytr.jobs().list().execute()
        existing_jobs = resp.get("jobs", [])
    except Exception as exc:
        logger.warning("Failed to list YouTube Reporting jobs for user %s: %s", user_id, exc)
        return []

    existing_types = {j.get("reportTypeId"): j for j in existing_jobs if j.get("reportTypeId")}
    created_or_found: list[dict] = []

    for rtype, name in STANDARD_REPORTING_JOBS:
        if rtype in existing_types:
            created_or_found.append(existing_types[rtype])
        else:
            try:
                created = ytr.jobs().create(body={"reportTypeId": rtype, "name": name}).execute()
                logger.info("Scheduled YouTube Reporting job '%s' (%s) for user %s", name, rtype, user_id)
                created_or_found.append(created)
            except Exception as exc:
                logger.warning("Failed to schedule job '%s' for user %s: %s", rtype, user_id, exc)

    return created_or_found


def list_reporting_jobs(user_id: str) -> list[dict]:
    """List all scheduled YouTube Reporting jobs for user."""
    try:
        ytr = _get_reporting_service(user_id)
        resp = ytr.jobs().list().execute()
        return resp.get("jobs", [])
    except Exception as exc:
        logger.warning("Failed to list reporting jobs for %s: %s", user_id, exc)
        return []


def list_available_reports(user_id: str) -> list[dict]:
    """List all generated bulk reports across all scheduled jobs."""
    try:
        ytr = _get_reporting_service(user_id)
        jobs = ytr.jobs().list().execute().get("jobs", [])
    except Exception as exc:
        logger.warning("Failed to list jobs for reports on %s: %s", user_id, exc)
        return []

    all_reports: list[dict] = []
    for j in jobs:
        jid = j.get("id")
        jname = j.get("name")
        jtype = j.get("reportTypeId")
        if not jid:
            continue
        try:
            r_resp = ytr.jobs().reports().list(jobId=jid).execute()
            for r in r_resp.get("reports", []):
                all_reports.append({
                    "job_id": jid,
                    "job_name": jname,
                    "report_type": jtype,
                    "report_id": r.get("id"),
                    "start_time": r.get("startTime"),
                    "end_time": r.get("endTime"),
                    "create_time": r.get("createTime"),
                    "download_url": r.get("downloadUrl"),
                })
        except Exception as exc:
            logger.debug("Could not fetch reports for job %s: %s", jid, exc)

    return all_reports


def download_and_ingest_reports(user_id: str) -> dict:
    """Download available bulk report CSVs and ingest into the database.

    Updates video statistics, traffic sources, and device/demographic metrics.
    """
    creds = load_credentials(user_id)
    if not creds or not creds.token:
        return {"ingested_reports": 0, "rows_processed": 0}

    reports = list_available_reports(user_id)
    if not reports:
        # Ensure default jobs are at least scheduled for future generation
        ensure_default_jobs(user_id)
        return {"ingested_reports": 0, "rows_processed": 0, "message": "No reports generated yet; jobs scheduled."}

    ingested_count = 0
    rows_count = 0
    now = datetime.now(timezone.utc)

    headers = {"Authorization": f"Bearer {creds.token}"}

    for rep in reports:
        durl = rep.get("download_url")
        rtype = rep.get("report_type")
        if not durl:
            continue

        try:
            resp = requests.get(durl, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue

            csv_text = resp.text
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            if not rows:
                continue

            with sync_session_scope() as session:
                if rtype in ("channel_basic_a2", "channel_basic_a3", "channel_combined_a2", "channel_combined_a3"):
                    for r in rows:
                        vid = r.get("video_id")
                        if not vid:
                            continue
                        views = int(r.get("views", 0) or 0)
                        mins = float(r.get("watch_time_minutes", 0) or 0)
                        subs_gained = int(r.get("subscribers_gained", 0) or 0)
                        wt_hours = round(mins / 60.0, 4) if mins else None

                        session.execute(
                            text("""
                                UPDATE youtube_videos_live
                                SET watch_time_hours = COALESCE(:wt, watch_time_hours),
                                    subscribers_gained = COALESCE(:subs, subscribers_gained),
                                    analytics_synced_at = :now
                                WHERE user_id = :user_id AND video_id = :video_id
                            """),
                            {"user_id": user_id, "video_id": vid, "wt": wt_hours, "subs": subs_gained, "now": now},
                        )
                        rows_count += 1

                elif rtype in ("channel_traffic_source_a2", "channel_traffic_source_a3"):
                    for r in rows:
                        code = r.get("traffic_source_type", "")
                        views = int(r.get("views", 0) or 0)
                        mins = float(r.get("watch_time_minutes", 0) or 0)
                        label = TRAFFIC_SOURCE_LABELS.get(code, code)
                        if not label:
                            continue
                        wt = round(mins / 60.0, 2)
                        stmt = pg_insert(YoutubeTrafficSource).values(
                            user_id=user_id,
                            traffic_source=label,
                            views=views,
                            watch_time_hours=wt,
                            imported_at=now,
                        )
                        session.execute(
                            stmt.on_conflict_do_update(
                                index_elements=[YoutubeTrafficSource.user_id, YoutubeTrafficSource.traffic_source],
                                set_={
                                    "views": stmt.excluded.views,
                                    "watch_time_hours": stmt.excluded.watch_time_hours,
                                    "imported_at": stmt.excluded.imported_at,
                                },
                            )
                        )
                        rows_count += 1

            ingested_count += 1
        except Exception as exc:
            logger.warning("Failed to process report %s for user %s: %s", rep.get("report_id"), user_id, exc)

    return {
        "ingested_reports": ingested_count,
        "rows_processed": rows_count,
        "last_sync": now.isoformat(),
    }
