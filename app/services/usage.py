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
import os
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries
from app.db.tables import AgentRun

logger = logging.getLogger(__name__)

# Usage enforcement is disabled by default for self-hosted / private deployments.
# Can be enabled via ENABLE_USAGE_LIMITS=true in .env if desired.
ENABLE_USAGE_LIMITS = os.getenv("ENABLE_USAGE_LIMITS", "false").lower() in ("true", "1")

TIER_LIMITS = {
    "free":       {"max_per_month": None, "max_per_hour": None},  # unlimited
    "pro":        {"max_per_month": None, "max_per_hour": None},  # unlimited
    "enterprise": {"max_per_month": None, "max_per_hour": None},  # unlimited
}


async def check_and_increment(session: AsyncSession, user_id: str) -> tuple[bool, str]:
    """
    Check if the user is within their tier limits. If usage limits are disabled (default),
    always allows execution without blocking.
    """
    if not ENABLE_USAGE_LIMITS:
        return True, ""

    try:
        await queries.reset_usage_if_expired(session, user_id)
        usage = await queries.get_usage(session, user_id)

        if not usage:
            await queries.init_usage(session, user_id)
            usage = await queries.get_usage(session, user_id)

        if not usage:
            return True, ""

        plan = usage.get("plan", "enterprise")
        limits = TIER_LIMITS.get(plan, TIER_LIMITS["enterprise"])
        runs_this_month = usage.get("runs_this_month", 0)

        # Check monthly limit
        max_monthly = limits.get("max_per_month")
        if max_monthly is not None and runs_this_month >= max_monthly:
            return False, (
                f"Monthly limit reached ({runs_this_month}/{max_monthly} runs). "
                f"Upgrade to {'pro' if plan == 'free' else 'enterprise'} for more."
            )

        # Check hourly limit
        max_hourly = limits.get("max_per_hour")
        if max_hourly is not None:
            hourly_count = await _count_recent_runs(session, user_id, hours=1)
            if hourly_count >= max_hourly:
                return False, (
                    f"Hourly rate limit reached ({hourly_count}/{max_hourly} runs/hour). "
                    f"Please wait before starting another pipeline."
                )

        # Increment the counter
        await queries.increment_usage(session, user_id)
        return True, ""

    except Exception as e:
        logger.error("Usage check failed: %s", e)
        # Fail-open: a broken quota check must not take the product down.
        return True, ""


async def _count_recent_runs(
    session: AsyncSession, user_id: str, hours: int = 1
) -> int:
    """Count agent_runs created within the last N hours for this user."""
    try:
        cutoff = func.now() - timedelta(hours=hours)
        return (
            await session.execute(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.user_id == user_id, AgentRun.created_at >= cutoff)
            )
        ).scalar_one()
    except Exception as e:
        logger.error("Failed to count recent runs: %s", e)
        return 0
