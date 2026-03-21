import json
import logging
import os
from datetime import datetime
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

# Fallback local storage
LOGS_DIR = "run_logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

async def save_run_log(topic: str, provider: str, tasks: list[dict], final_result: str):
    """
    Saves the execution log to Supabase (if configured) or a local JSON file.
    """
    timestamp = datetime.now().isoformat()
    log_data = {
        "topic": topic,
        "provider": provider,
        "timestamp": timestamp,
        "tasks": tasks,
        "final_result": final_result
    }

    # 1. Try Supabase
    supabase = get_supabase()
    if supabase:
        try:
            # Table 'pipeline_runs' assumed to exist as per SaaS architecture
            supabase.table("pipeline_runs").insert(log_data).execute()
            logger.info("Successfully saved run log to Supabase.")
            return
        except Exception as e:
            logger.warning(f"Failed to save to Supabase, falling back to local: {e}")

    # 2. Local fallback
    filename = f"{LOGS_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
        logger.info(f"Saved run log locally to {filename}")
    except Exception as e:
        logger.error(f"Critical: Failed to save run log locally: {e}")
