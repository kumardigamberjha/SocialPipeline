import re
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


# -- Blog Post Operations --

# Average adult reads ~238 words per minute (Brysbaert, 2019 meta-analysis).
WORDS_PER_MINUTE = 238


def slugify(text: str) -> str:
    """Convert a title into a URL-safe slug: lowercase, hyphenated, ASCII-only."""
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)   # drop punctuation
    text = re.sub(r"[\s_-]+", "-", text)        # collapse whitespace/underscores to single hyphen
    text = text.strip("-")
    return text[:80] or "untitled-post"


def save_blog_post(
    run_id: str,
    user_id: str,
    topic: str,
    title: str,
    content: str,
    niche: str,
    approved: bool = False,
    word_count: int = None,
) -> dict:
    """Persist a generated long-form blog post and return the full row.

    word_count may be supplied by the pipeline (Python-counted) or computed here
    from the content. reading_time_minutes and a unique URL-safe slug (from the
    title, falling back to the topic) are always derived.
    """
    db = get_db()
    blog_id = generate_uuid()

    if word_count is None:
        word_count = len(content.split())
    reading_time_minutes = max(1, word_count // WORDS_PER_MINUTE)

    base_slug = slugify(title or topic)
    slug = base_slug
    # The slug column is UNIQUE — disambiguate collisions with a short id suffix.
    existing = db.execute("SELECT 1 FROM blog_posts WHERE slug = ?", (slug,)).fetchone()
    if existing:
        slug = f"{base_slug}-{blog_id[:8]}"

    db.execute(
        """
        INSERT INTO blog_posts
            (id, run_id, user_id, topic, title, content, word_count,
             reading_time_minutes, niche, approved, slug)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            blog_id, run_id, user_id, topic, title, content, word_count,
            reading_time_minutes, niche, 1 if approved else 0, slug,
        ),
    )
    db.commit()

    cursor = db.execute("SELECT * FROM blog_posts WHERE id = ?", (blog_id,))
    return dict_from_row(cursor.fetchone())


def get_blog_posts(user_id: str, limit: int = 20) -> List[dict]:
    """Return the most recent non-deleted blog posts for a user (newest first)."""
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM blog_posts WHERE user_id = ? AND deleted_at IS NULL "
        "ORDER BY published_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [dict_from_row(row) for row in cursor.fetchall()]


def get_blog_by_id(blog_id: str, user_id: str) -> Optional[dict]:
    """Return a single non-deleted post, enforcing user ownership."""
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM blog_posts WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (blog_id, user_id),
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None


def get_blog_by_slug(slug: str) -> Optional[dict]:
    """Return a single non-deleted post by slug. Public — no ownership check."""
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM blog_posts WHERE slug = ? AND deleted_at IS NULL", (slug,)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None


def soft_delete_blog(blog_id: str, user_id: str) -> bool:
    """Soft-delete a post (set deleted_at). Returns True if a live row was updated."""
    db = get_db()
    cursor = db.execute(
        "UPDATE blog_posts SET deleted_at = datetime('now') "
        "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (blog_id, user_id),
    )
    db.commit()
    return cursor.rowcount > 0


def get_blog_posts_by_run_id(run_id: str) -> List[dict]:
    """Return all blog posts produced by a given run (used by the WS on completion)."""
    db = get_db()
    cursor = db.execute("SELECT * FROM blog_posts WHERE run_id = ?", (run_id,))
    return [dict_from_row(row) for row in cursor.fetchall()]


# -- LinkedIn Post Operations --

def save_linkedin_post(
    run_id: str, user_id: str, topic: str, post_text: str,
    hook: str, angle_type: str, word_count: int, approved: bool, niche: str
) -> dict:
    db = get_db()
    post_id = generate_uuid()
    
    hashtag_count = len(re.findall(r'#\w+', post_text))
    
    db.execute(
        """
        INSERT INTO linkedin_posts
            (id, run_id, user_id, topic, post_text, hook, angle_type, word_count, hashtag_count, approved, niche)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (post_id, run_id, user_id, topic, post_text, hook, angle_type, word_count, hashtag_count, 1 if approved else 0, niche)
    )
    db.commit()
    
    cursor = db.execute("SELECT * FROM linkedin_posts WHERE id = ?", (post_id,))
    return dict_from_row(cursor.fetchone())

def get_linkedin_posts(user_id: str, limit: int = 20) -> list[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT id, run_id, user_id, topic, hook, angle_type, word_count, hashtag_count, approved, niche, created_at, deleted_at FROM linkedin_posts WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_linkedin_post_by_id(post_id: str, user_id: str) -> dict | None:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM linkedin_posts WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (post_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def get_linkedin_posts_by_run_id(run_id: str) -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM linkedin_posts WHERE run_id = ?", (run_id,))
    return [dict_from_row(row) for row in cursor.fetchall()]

def soft_delete_linkedin_post(post_id: str, user_id: str) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE linkedin_posts SET deleted_at = datetime('now') WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (post_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0
