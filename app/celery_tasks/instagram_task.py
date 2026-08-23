"""
Celery task: nightly Instagram analytics refresh.

Runs at 12:10 AM IST (18:40 UTC) via Celery Beat.

For every user with a stored Instagram connection (instagram_oauth_tokens):
  1. Refreshes their long-lived token if it's expiring within 15 days.
  2. Fetches profile, media posts, hashtags and computes stats via the Graph API.
  3. Saves the full snapshot to Postgres (persistent backup).
  4. Writes all data to Redis, keyed per user.
  5. Flushes that user's stale Redis keys first so their page always gets fresh data.

One user's failure (expired/revoked token, Graph API error) is logged and
skipped rather than aborting the run for everyone else.

On page load: serve from Redis → Postgres snapshot → "sync pending" state.
"""
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.celery_tasks.instagram_task.instagram_nightly_refresh",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # Retry after 5 min on failure
)
def instagram_nightly_refresh(self):
    """Nightly job: refresh every connected user's Instagram token + cache."""
    from app.db import sync_queries
    from app.db.sync_session import sync_session_scope
    from app.services.instagram_auth import refresh_if_needed
    from app.services.instagram_cache import refresh_instagram_cache

    try:
        with sync_session_scope() as session:
            user_ids = sync_queries.list_instagram_connected_user_ids(session)
    except Exception as exc:
        logger.error("Instagram nightly refresh: could not list connected users: %s", exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Instagram nightly refresh: max retries exceeded. Giving up.")
            return {"status": "failed", "error": str(exc)}

    results = []
    for user_id in user_ids:
        try:
            refresh_if_needed(user_id, force=False)
            data = refresh_instagram_cache(user_id)
            results.append({
                "user_id": user_id,
                "status": "success",
                "handle": data.get("profile", {}).get("handle", "?"),
                "posts_cached": len(data.get("posts", [])),
                "hashtags_cached": len(data.get("hashtags", [])),
                "synced_at": data.get("synced_at"),
            })
        except Exception as exc:
            logger.error("Instagram nightly refresh failed for user %s: %s", user_id, exc)
            results.append({"user_id": user_id, "status": "failed", "error": str(exc)})

    return {"status": "success", "users_synced": len(user_ids), "results": results}
