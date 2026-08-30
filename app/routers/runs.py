import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/stats")
async def get_runs_stats(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fetch aggregate telemetry statistics for the current user."""
    try:
        return await queries.get_runs_stats_by_user(session, user["id"])
    except Exception as e:
        logger.error("Failed to fetch runs stats: %s", e)
        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "running": 0,
            "pending": 0,
            "avg_duration": 0.0,
            "success_rate": 0.0,
            "providers": [],
        }


@router.get("")
async def get_recent_runs(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    provider: str | None = None,
    time_range: str | None = None,
    sort_by: str = "created_at_desc",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fetch a filtered page of agent runs for the telemetry ledger and history page."""
    try:
        items = await queries.get_runs_by_user(
            session=session,
            user_id=user["id"],
            limit=limit,
            offset=offset,
            status=status,
            search=search,
            provider=provider,
            time_range=time_range,
            sort_by=sort_by,
        )
        total = await queries.count_runs_by_user(
            session=session,
            user_id=user["id"],
            status=status,
            search=search,
            provider=provider,
            time_range=time_range,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Failed to fetch runs: %s", e)
        return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fetch a specific run and its task steps."""
    try:
        # Scoped to the caller, so a run belonging to someone else is simply
        # not found. The previous version fetched unscoped and then compared
        # owners to return 403 — which confirms the id exists to anyone probing.
        run = await queries.get_run_by_id(session, run_id, user["id"])
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        run["task_steps"] = await queries.get_steps_by_run(session, run_id, user["id"])
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch run: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
