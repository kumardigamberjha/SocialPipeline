"""
Supabase client and helper functions for database operations.
"""
import logging
from supabase import create_client, Client
from app.config import get_settings

logger = logging.getLogger(__name__)

# Core singleton
_supabase: Client | None = None

def get_supabase() -> Client | None:
    """Get the initialized Supabase client."""
    global _supabase
    if _supabase:
        return _supabase
        
    settings = get_settings()
    url = settings.supabase_url or settings.supabase_project_link
    # Prioritize Secret Key (service_role) for backend inserts into agent_runs/task_steps
    key = settings.supabase_secret_key or settings.supabase_key or settings.supabase_publishable_key
    
    if url and key:
        try:
            _supabase = create_client(url, key)
            logger.info("Supabase client initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            _supabase = None
    else:
        logger.warning("Supabase URL or Key is missing from config.")
        
    return _supabase

# ── Helpers for SaaS Models ───────────────────────────────

def create_agent_run(run_id: str, user_id: str, topic: str, provider_used: str):
    """Creates the initial agent run record in Supabase."""
    client = get_supabase()
    if not client:
        return None
    try:
        data = {
            "id": run_id,
            "user_id": user_id,
            "topic": topic,
            "provider_used": provider_used,
            "status": "running"
        }
        res = client.table("agent_runs").insert(data).execute()
        return res.data
    except Exception as e:
        logger.error(f"Supabase create_agent_run error: {e}")
        return None

def save_task_step(run_id: str, agent_name: str, task_name: str, output: str, status: str = "done"):
    """Saves a task step to Supabase."""
    client = get_supabase()
    if not client:
        return None
    try:
        data = {
            "run_id": run_id,
            "agent_name": agent_name,
            "task_name": task_name,
            "output": output,
            "status": status
        }
        res = client.table("task_steps").insert(data).execute()
        return res.data
    except Exception as e:
        logger.error(f"Supabase save_task_step error: {e}")
        return None

def update_agent_run(run_id: str, final_result: str, duration: float, status: str = "completed", topic: str = None):
    """Updates the overall agent run record, optionally overriding the topic with a generated title."""
    client = get_supabase()
    if not client:
        return None
    try:
        from datetime import datetime
        data = {
            "status": status,
            "final_result": final_result,
            "duration_seconds": duration,
            "completed_at": datetime.utcnow().isoformat()
        }
        if topic:
            data["topic"] = topic
            
        res = client.table("agent_runs").update(data).eq("id", run_id).execute()
        return res.data
    except Exception as e:
        logger.error(f"Supabase update_agent_run error: {e}")
        return None

def get_user_api_key(user_id: str, provider: str) -> str | None:
    """Fetches a specific user's API key for a given provider."""
    client = get_supabase()
    if not client:
        return None
    try:
        res = client.table("api_keys").select("api_key_encrypted").eq("user_id", user_id).eq("provider", provider).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["api_key_encrypted"]
    except Exception as e:
        logger.error(f"Supabase get_user_api_key error: {e}")
    return None
