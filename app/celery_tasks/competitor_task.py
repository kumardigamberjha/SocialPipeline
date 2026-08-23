"""
Celery task: weekly competitor resync.

Runs Sunday 14:00 IST (08:30 UTC — Celery Beat runs in UTC, see celery_app.py)
for every user with connected competitors. Refreshes channel-level stats for
every approved competitor (cheap: 1 quota unit per 50 channels) and the latest
videos for the stalest `settings.competitor_weekly_sync_cap` of them (~2 units
each), so the per-user weekly spend stays bounded regardless of how many
thousands of competitors a user has tracked — the cap rotates through the
whole list over successive Sundays via the
``last_synced_at ASC NULLS FIRST`` ordering in
``sync_queries.select_competitors_for_weekly_sync``.
"""

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.celery_tasks.competitor_task.competitor_weekly_sync",
    bind=True,
    soft_time_limit=1500,
    time_limit=1800,
)
def competitor_weekly_sync(self):
    from app.config import get_settings
    from app.core.redis_client import bump_epoch_sync
    from app.db import sync_queries
    from app.db.sync_session import sync_session_scope
    from app.services import youtube_competitor as yc
    from app.services.youtube_sync_service import get_all_connected_user_ids

    settings = get_settings()
    cap = settings.competitor_weekly_sync_cap
    video_limit = settings.competitor_weekly_video_limit

    user_ids = get_all_connected_user_ids()
    if not user_ids:
        logger.info("Competitor weekly sync: no connected users — skipping.")
        return {"status": "no_users"}

    results = {}
    for uid in user_ids:
        with sync_session_scope() as session:
            competitors = sync_queries.select_competitors_for_weekly_sync(session, uid, cap)
        if not competitors:
            continue

        ledger = yc.QuotaLedger()

        # Pass 1 — cheap stats refresh for every selected competitor, batched
        # at 50 per channels.list call (1 unit per batch).
        try:
            yt = yc._service(uid)
            resolved = yc._resolve_by_ids(yt, [c["channel_id"] for c in competitors], ledger)
        except Exception as exc:
            logger.warning("Competitor weekly sync: could not build client for %s: %s", uid, exc)
            continue

        stats_rows = []
        for c in competitors:
            item = resolved.get(c["channel_id"])
            if not item:
                continue
            stats = item.get("statistics", {})
            stats_rows.append(
                {
                    "channel_id": c["channel_id"],
                    "subscriber_count": int(stats.get("subscriberCount", 0) or 0),
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "video_count": int(stats.get("videoCount", 0) or 0),
                }
            )
        if stats_rows:
            with sync_session_scope() as session:
                sync_queries.bulk_upsert_competitor_stats(session, uid, stats_rows)

        # Pass 2 — latest videos, per competitor, until the budget runs out.
        synced, errors = 0, 0
        for c in competitors:
            if ledger.spent >= ledger.budget:
                break
            uploads_id = c.get("uploads_playlist_id")
            if not uploads_id:
                with sync_session_scope() as session:
                    sync_queries.mark_competitor_synced(
                        session, uid, c["channel_id"], error="no uploads playlist on file"
                    )
                continue
            try:
                videos = yc.sync_competitor_videos(
                    uid, c["channel_id"], uploads_id, ledger, limit=video_limit
                )
                with sync_session_scope() as session:
                    if videos:
                        sync_queries.bulk_upsert_competitor_videos(session, uid, videos)
                    sync_queries.mark_competitor_synced(session, uid, c["channel_id"])
                synced += 1
            except Exception as exc:
                errors += 1
                with sync_session_scope() as session:
                    sync_queries.mark_competitor_synced(
                        session, uid, c["channel_id"], error=str(exc)[:500]
                    )

        for domain in ("yt-competitors", "yt-strategy", "yt-roadmap", "yt-ai-analysis"):
            try:
                bump_epoch_sync(uid, domain)
            except Exception as exc:
                logger.warning("Could not bump %s epoch for %s: %s", domain, uid, exc)

        results[uid] = {
            "competitors_considered": len(competitors),
            "videos_synced": synced,
            "errors": errors,
            "quota_units_spent": ledger.spent,
        }
        logger.info(
            "Competitor weekly sync user %s: %d considered, %d synced, %d errors, %d quota units",
            uid, len(competitors), synced, errors, ledger.spent,
        )

    return {"status": "done", "users_processed": len(results), "results": results}
