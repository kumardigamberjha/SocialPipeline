"""
Usage enforcement service.

Checks whether a user is within their tier's rate limits before allowing
a pipeline run. Updates the counter on success.

Tier limits:
    free:       10 runs/month,  2 runs/hour
    pro:        100 runs/month, 10 runs/hour
    enterprise: unlimited
"""

import logging
from datetime import datetime, timezone
from app.db import queries

logger = logging.getLogger(__name__)

TIER_LIMITS = {
    "free":       {"max_per_month": 10,  "max_per_hour": 2},
    "pro":        {"max_per_month": 100, "max_per_hour": 10},
    "enterprise": {"max_per_month": None, "max_per_hour": None},  # unlimited
}


def check_and_increment(user_id: str) -> tuple[bool, str]:
    """
    Check if the user is within their tier limits. If yes, increment the
    monthly counter and return (True, ""). If no, return (False, reason).

    For the dummy/anonymous user_id, always allows (no enforcement).
    """
    if user_id == "00000000-0000-0000-0000-000000000000":
        return True, ""

    try:
        queries.reset_usage_if_expired(user_id)
        usage = queries.get_usage(user_id)

        if not usage:
            queries.init_usage(user_id)
            usage = queries.get_usage(user_id)

        if not usage:
            return True, ""

        plan = usage.get("plan", "free")
        limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
        runs_this_month = usage.get("runs_this_month", 0)

        # Check monthly limit
        max_monthly = limits["max_per_month"]
        if max_monthly is not None and runs_this_month >= max_monthly:
            return False, (
                f"Monthly limit reached ({runs_this_month}/{max_monthly} runs). "
                f"Upgrade to {'pro' if plan == 'free' else 'enterprise'} for more."
            )

        # Check hourly limit
        max_hourly = limits["max_per_hour"]
        if max_hourly is not None:
            hourly_count = _count_recent_runs_sqlite(user_id, hours=1)
            if hourly_count >= max_hourly:
                return False, (
                    f"Hourly rate limit reached ({hourly_count}/{max_hourly} runs/hour). "
                    f"Please wait before starting another pipeline."
                )

        # Increment the counter
        queries.increment_usage(user_id)
        return True, ""

    except Exception as e:
        logger.error("Usage check failed: %s", e)
        # Fail-open: allow the request if the check itself errors
        return True, ""


def _count_recent_runs_sqlite(user_id: str, hours: int = 1) -> int:
    """Count agent_runs created within the last N hours for this user in SQLite."""
    from app.db.database import get_db
    try:
        db = get_db()
        cursor = db.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE user_id = ? AND created_at >= datetime('now', ?)",
            (user_id, f"-{hours} hours")
        )
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error("Failed to count recent runs: %s", e)
        return 0
