import json
import logging
import os
from datetime import datetime
from app.db.database import get_db

logger = logging.getLogger(__name__)

# Fallback local storage
LOGS_DIR = "run_logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

async def save_run_log(topic: str, provider: str, tasks: list[dict], final_result: str):
    """
    Saves the execution log to SQLite and a local JSON file.
    """
    timestamp = datetime.now().isoformat()
    log_data = {
        "topic": topic,
        "provider": provider,
        "timestamp": timestamp,
        "tasks": tasks,
        "final_result": final_result
    }

    # 1. Try SQLite
    try:
        db = get_db()
        import uuid
        run_id = str(uuid.uuid4())
        dummy_user_id = "00000000-0000-0000-0000-000000000000"
        db.execute(
            "INSERT INTO agent_runs (id, user_id, topic, provider_used, status, final_result) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, dummy_user_id, topic, provider, 'completed', final_result)
        )
        db.commit()
        logger.info("Successfully saved run log to SQLite.")
    except Exception as e:
        logger.warning(f"Failed to save to SQLite, falling back to local: {e}")

    # 2. Local fallback
    filename = f"{LOGS_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
        logger.info(f"Saved run log locally to {filename}")
    except Exception as e:
        logger.error(f"Critical: Failed to save run log locally: {e}")
