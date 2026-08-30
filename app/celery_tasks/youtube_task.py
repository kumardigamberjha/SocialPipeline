"""
Celery task: nightly YouTube full sync.

Runs at 12:05 AM IST (18:35 UTC) via Celery Beat for all users who have
connected their Google account with youtube.readonly scope.

What this does every night:
  1. Fetches EVERY video from the channel's uploads playlist.
  2. For videos already in the DB → updates views, likes, comments, status.
  3. For new videos → inserts full metadata + SEO analysis.
  4. Flushes all YouTube Redis cache keys so next requests see fresh data.
"""
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.celery_tasks.youtube_task.youtube_nightly_sync", bind=True)
def youtube_nightly_sync(self):
    """Nightly job: full sync of YouTube videos for all connected users."""
    from app.services.youtube_cache import flush_youtube_cache_sync
    from app.services.youtube_sync_service import (
        sync_all_videos,
        get_all_connected_user_ids,
        YoutubeSyncError,
    )

    user_ids = get_all_connected_user_ids()

    if not user_ids:
        logger.info("YouTube nightly sync: no connected users found — skipping.")
        return {"status": "no_users"}

    results = {}
    for uid in user_ids:
        try:
            # Sync ALL videos — no max_results cap
            r = sync_all_videos(uid)
            results[uid] = r
            flush_youtube_cache_sync(uid)
            logger.info(
                "Nightly sync user %s: %d total (%d new, %d updated) — Redis cache flushed",
                uid, r["synced"], r["new"], r["updated"],
            )
        except YoutubeSyncError as exc:
            logger.warning("Nightly sync failed for user %s: %s", uid, exc)
            results[uid] = {"error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error in nightly sync for user %s: %s", uid, exc)
            results[uid] = {"error": str(exc)}

    return {"status": "done", "users_processed": len(user_ids), "results": results}

