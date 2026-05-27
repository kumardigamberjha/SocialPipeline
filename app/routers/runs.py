from fastapi import APIRouter, Depends, HTTPException
import logging
from app.db import queries
from app.core.auth_deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.get("")
def get_recent_runs(limit: int = 50, user: dict = Depends(get_current_user)):
    """Fetch the most recent agent runs for the telemetry ledger."""
    try:
        runs = queries.get_runs_by_user(user['id'], limit)
        return runs
    except Exception as e:
        logger.error(f"Failed to fetch runs from SQLite: {e}")
        return []

@router.get("/{run_id}")
def get_run(run_id: str, user: dict = Depends(get_current_user)):
    """Fetch a specific run and its task steps."""
    try:
        run = queries.get_run_by_id(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run['user_id'] != user['id']:
            raise HTTPException(status_code=403, detail="Not authorized to access this run")
            
        steps = queries.get_steps_by_run(run_id)
        run['task_steps'] = steps
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch run from SQLite: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
