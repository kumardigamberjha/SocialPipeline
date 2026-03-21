from fastapi import APIRouter
import logging
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.get("")
def get_recent_runs(limit: int = 50):
    """Fetch the most recent agent runs for the telemetry ledger."""
    client = get_supabase()
    if not client:
        logger.warning("Supabase client not initialized, returning empty runs list.")
        return []
    try:
        # Pull latest 50 runs ordered by newest first
        res = client.table("agent_runs").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        logger.error(f"Failed to fetch runs from Supabase: {e}")
        return []
