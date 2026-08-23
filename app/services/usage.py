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
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries
from app.db.tables import AgentRun

logger = logging.getLogger(__name__)

TIER_LIMITS = {
    "free":       {"max_per_month": 10,  "max_per_hour": 2},
    "pro":        {"max_per_month": 100, "max_per_hour": 10},
    "enterprise": {"max_per_month": None, "max_per_hour": None},  # unlimited
}


async def check_and_increment(session: AsyncSession, user_id: str) -> tuple[bool, str]:
    """
    Check if the user is within their tier limits. If yes, increment the
    monthly counter and return (True, ""). If no, return (False, reason).

    There is no longer an anonymous exemption: the dummy user that this used to
    wave through no longer exists, and every caller now arrives authenticated.
    """
    try:
        await queries.reset_usage_if_expired(session, user_id)
        usage = await queries.get_usage(session, user_id)

        if not usage:
            await queries.init_usage(session, user_id)
            usage = await queries.get_usage(session, user_id)

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
        # Fail-open: a broken quota check must not take the product down. This
        # is a billing control, not a security control — authentication and
        # tenant scoping are enforced elsewhere and never fail open.
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
