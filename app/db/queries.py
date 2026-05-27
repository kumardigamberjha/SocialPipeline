from typing import Dict, List, Optional
from app.db.database import get_db, dict_from_row, generate_uuid

# -- User Operations --

def create_user(email: str, password_hash: str) -> dict:
    db = get_db()
    user_id = generate_uuid()
    db.execute(
        "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
        (user_id, email, password_hash)
    )
    db.commit()
    return get_user_by_id(user_id)

def get_user_by_email(email: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    return dict_from_row(row) if row else None


# -- Agent Run Operations --

def create_run(user_id: str, topic: str, provider: str) -> dict:
    db = get_db()
    run_id = generate_uuid()
    db.execute(
        "INSERT INTO agent_runs (id, user_id, topic, provider_used, status) VALUES (?, ?, ?, ?, ?)",
        (run_id, user_id, topic, provider, 'pending')
    )
    db.commit()
    return get_run_by_id(run_id)

def create_agent_run(run_id: str, user_id: str, topic: str, provider: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO agent_runs (id, user_id, topic, provider_used, status) VALUES (?, ?, ?, ?, ?)",
        (run_id, user_id, topic, provider, 'pending')
    )
    db.commit()

def update_run_status(run_id: str, status: str, final_result: str = None, duration: float = None) -> None:
    db = get_db()
    if status in ('completed', 'failed'):
        db.execute(
            "UPDATE agent_runs SET status = ?, final_result = ?, duration_seconds = ?, completed_at = datetime('now') WHERE id = ?",
            (status, final_result, duration, run_id)
        )
    else:
        db.execute(
            "UPDATE agent_runs SET status = ?, final_result = ?, duration_seconds = ? WHERE id = ?",
            (status, final_result, duration, run_id)
        )
    db.commit()

def update_agent_run(run_id: str, final_result: str, duration: float, status: str, image_url: str = None, topic: str = None) -> None:
    db = get_db()
    updates = ["status = ?", "final_result = ?", "duration_seconds = ?"]
    params = [status, final_result, duration]
    
    if status in ('completed', 'failed'):
        updates.append("completed_at = datetime('now')")
        
    if image_url is not None:
        updates.append("image_url = ?")
        params.append(image_url)
        
    if topic is not None:
        updates.append("topic = ?")
        params.append(topic)
        
    params.append(run_id)
    query = f"UPDATE agent_runs SET {', '.join(updates)} WHERE id = ?"
    db.execute(query, tuple(params))
    db.commit()

def update_run_image(run_id: str, image_url: str) -> None:
    db = get_db()
    db.execute("UPDATE agent_runs SET image_url = ? WHERE id = ?", (image_url, run_id))
    db.commit()

def get_run_by_id(run_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def get_runs_by_user(user_id: str, limit: int = 50) -> List[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM agent_runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    return [dict_from_row(row) for row in cursor.fetchall()]


# -- Task Step Operations --

def insert_task_step(run_id: str, agent_name: str, task_name: str, output: str, status: str = 'done') -> dict:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO task_steps (run_id, agent_name, task_name, output, status) VALUES (?, ?, ?, ?, ?)",
        (run_id, agent_name, task_name, output, status)
    )
    db.commit()
    step_id = cursor.lastrowid
    cursor = db.execute("SELECT * FROM task_steps WHERE id = ?", (step_id,))
    return dict_from_row(cursor.fetchone())

def save_task_step(run_id: str, agent_name: str, task_name: str, output: str, status: str = 'done') -> dict:
    return insert_task_step(run_id, agent_name, task_name, output, status)

def get_steps_by_run(run_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM task_steps WHERE run_id = ? ORDER BY id ASC", (run_id,))
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_new_steps_since(run_id: str, last_step_id: int) -> List[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM task_steps WHERE run_id = ? AND id > ? ORDER BY id ASC", (run_id, last_step_id))
    return [dict_from_row(row) for row in cursor.fetchall()]


# -- Usage Limit Operations --

def get_usage(user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM usage_limits WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def init_usage(user_id: str) -> None:
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO usage_limits (user_id, plan, runs_this_month, max_runs_per_month, reset_at) VALUES (?, 'free', 0, 10, datetime('now', '+1 month'))",
        (user_id,)
    )
    db.commit()

def increment_usage(user_id: str) -> None:
    db = get_db()
    db.execute("UPDATE usage_limits SET runs_this_month = runs_this_month + 1 WHERE user_id = ?", (user_id,))
    db.commit()

def reset_usage_if_expired(user_id: str) -> None:
    db = get_db()
    cursor = db.execute("SELECT reset_at FROM usage_limits WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row['reset_at']:
        # Check if reset_at is in the past
        check_cursor = db.execute("SELECT datetime('now') > ?", (row['reset_at'],))
        is_expired = check_cursor.fetchone()[0]
        if is_expired:
            db.execute("UPDATE usage_limits SET runs_this_month = 0, reset_at = datetime('now', '+1 month') WHERE user_id = ?", (user_id,))
            db.commit()

def update_plan(user_id: str, plan: str, max_runs: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE usage_limits SET plan = ?, max_runs_per_month = ? WHERE user_id = ?",
        (plan, max_runs, user_id)
    )
    db.commit()


# -- API Key Operations --

def save_api_key(user_id: str, provider: str, encrypted_key: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO api_keys (user_id, provider, api_key_encrypted) VALUES (?, ?, ?)",
        (user_id, provider, encrypted_key)
    )
    db.commit()

def get_api_key(user_id: str, provider: str) -> Optional[str]:
    db = get_db()
    cursor = db.execute(
        "SELECT api_key_encrypted FROM api_keys WHERE user_id = ? AND provider = ? ORDER BY created_at DESC LIMIT 1",
        (user_id, provider)
    )
    row = cursor.fetchone()
    return row['api_key_encrypted'] if row else None
