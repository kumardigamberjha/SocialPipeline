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

def get_runs_by_user(user_id: str, limit: int = 50, offset: int = 0) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM agent_runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
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


# -- YouTube Script Operations --

def save_youtube_script(
    run_id: str, user_id: str, topic: str, title: str, script: str,
    word_count: int, seo_title: str, seo_description: str, seo_tags: str,
    approved: bool, niche: str,
) -> dict:
    db = get_db()
    script_id = generate_uuid()
    db.execute(
        """
        INSERT INTO youtube_scripts
            (id, run_id, user_id, topic, title, script, word_count,
             seo_title, seo_description, seo_tags, approved, niche)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (script_id, run_id, user_id, topic, title, script, word_count,
         seo_title, seo_description, seo_tags, 1 if approved else 0, niche)
    )
    db.commit()
    cursor = db.execute("SELECT * FROM youtube_scripts WHERE id = ?", (script_id,))
    return dict_from_row(cursor.fetchone())

def get_youtube_scripts(user_id: str, limit: int = 20) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT id, run_id, user_id, topic, title, word_count, seo_title, approved, niche, created_at "
        "FROM youtube_scripts WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_youtube_script_by_id(script_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM youtube_scripts WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (script_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def get_youtube_scripts_by_run_id(run_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM youtube_scripts WHERE run_id = ?", (run_id,))
    return [dict_from_row(row) for row in cursor.fetchall()]

def soft_delete_youtube_script(script_id: str, user_id: str) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE youtube_scripts SET deleted_at = datetime('now') WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (script_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0


# -- Content Plan Operations --
# NOTE: update_plan() above belongs to usage_limits/billing; everything here is
# prefixed content_plan / plan_item to avoid collision.

def create_content_plan(user_id: str, name: str, plan_type: str, niche: str,
                        start_date: str, end_date: str) -> dict:
    db = get_db()
    plan_id = generate_uuid()
    db.execute(
        "INSERT INTO content_plans (id, user_id, name, plan_type, niche, start_date, end_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (plan_id, user_id, name, plan_type, niche, start_date, end_date)
    )
    db.commit()
    return get_content_plan_by_id(plan_id, user_id)

def get_content_plans(user_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM plan_items i WHERE i.plan_id = p.id) AS item_count,
               (SELECT COUNT(*) FROM plan_items i WHERE i.plan_id = p.id
                 AND i.production_status = 'video_published') AS published_count
        FROM content_plans p
        WHERE p.user_id = ?
        ORDER BY p.start_date DESC
        """,
        (user_id,)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_content_plan_by_id(plan_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM content_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def update_content_plan(plan_id: str, user_id: str, name: str = None, status: str = None) -> bool:
    db = get_db()
    updates, params = [], []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if not updates:
        return False
    params += [plan_id, user_id]
    cursor = db.execute(
        f"UPDATE content_plans SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        tuple(params)
    )
    db.commit()
    return cursor.rowcount > 0

def delete_content_plan(plan_id: str, user_id: str) -> bool:
    """Hard delete; plan_items and plan_item_content cascade (FK pragma is ON)."""
    db = get_db()
    cursor = db.execute(
        "DELETE FROM content_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0


# -- Plan Item Operations --

def create_plan_item(plan_id: str, user_id: str, topic: str, scheduled_date: str,
                     notes: str = None, topic_source: str = "manual",
                     publish_date: str = None, video_format: str = "full",
                     event_time: str = None, event_duration_minutes: int = None) -> dict:
    db = get_db()
    item_id = generate_uuid()
    db.execute(
        "INSERT INTO plan_items (id, plan_id, user_id, topic, scheduled_date, publish_date, notes, topic_source, video_format, event_time, event_duration_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, plan_id, user_id, topic, scheduled_date, publish_date, notes, topic_source, video_format, event_time, event_duration_minutes)
    )
    db.commit()
    return get_plan_item_by_id(item_id, user_id)

def get_plan_items(plan_id: str, user_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM plan_items WHERE plan_id = ? AND user_id = ? ORDER BY scheduled_date ASC, created_at ASC",
        (plan_id, user_id)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_plan_item_by_id(item_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM plan_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

# Sentinel so callers can clear publish_date (pass None) vs. leave it unchanged (omit).
_UNSET = object()

def update_plan_item(item_id: str, user_id: str, topic: str = None, scheduled_date: str = None,
                     notes: str = None, production_status: str = None,
                     publish_date=_UNSET, video_format: str = None,
                     event_time=_UNSET, event_duration_minutes: int = None) -> bool:
    db = get_db()
    updates, params = [], []
    if topic is not None:
        updates.append("topic = ?")
        params.append(topic)
    if scheduled_date is not None:
        updates.append("scheduled_date = ?")
        params.append(scheduled_date)
    if publish_date is not _UNSET:
        updates.append("publish_date = ?")
        params.append(publish_date)  # None clears it; a date string sets it
    if event_time is not _UNSET:
        updates.append("event_time = ?")
        params.append(event_time)  # None clears it; 'HH:MM' sets it
    if event_duration_minutes is not None:
        updates.append("event_duration_minutes = ?")
        params.append(event_duration_minutes)
    if video_format is not None:
        updates.append("video_format = ?")
        params.append(video_format)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if production_status is not None:
        updates.append("production_status = ?")
        params.append(production_status)
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params += [item_id, user_id]
    cursor = db.execute(
        f"UPDATE plan_items SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        tuple(params)
    )
    db.commit()
    return cursor.rowcount > 0

def set_plan_item_calendar_event(item_id: str, event_id: str, event_link: str,
                                 event_time: str = None, event_duration_minutes: int = None) -> None:
    db = get_db()
    fields = ["gcal_event_id = ?", "gcal_event_link = ?"]
    params = [event_id, event_link]
    if event_time is not None:
        fields.append("event_time = ?")
        params.append(event_time)
    if event_duration_minutes is not None:
        fields.append("event_duration_minutes = ?")
        params.append(event_duration_minutes)
    fields.append("updated_at = datetime('now')")
    params.append(item_id)
    db.execute(f"UPDATE plan_items SET {', '.join(fields)} WHERE id = ?", tuple(params))
    db.commit()

def clear_plan_item_calendar_event(item_id: str) -> None:
    """Forget the linked calendar event (e.g. it was deleted in Google Calendar)
    so the UI offers 'Add to Calendar' again."""
    db = get_db()
    db.execute(
        "UPDATE plan_items SET gcal_event_id = NULL, gcal_event_link = NULL, updated_at = datetime('now') WHERE id = ?",
        (item_id,)
    )
    db.commit()

def delete_plan_item(item_id: str, user_id: str) -> bool:
    db = get_db()
    cursor = db.execute(
        "DELETE FROM plan_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0

# -- YouTube Playlist Item Operations (local pending → published tracker) --

def create_youtube_playlist_item(user_id: str, playlist_id: str, title: str,
                                 playlist_title: str = None, description: str = None,
                                 video_format: str = "full", scheduled_date: str = None,
                                 publish_date: str = None, source: str = "manual") -> dict:
    db = get_db()
    item_id = generate_uuid()
    db.execute(
        "INSERT INTO youtube_playlist_items "
        "(id, user_id, playlist_id, playlist_title, title, description, video_format, scheduled_date, publish_date, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, user_id, playlist_id, playlist_title, title, description, video_format, scheduled_date, publish_date, source)
    )
    db.commit()
    return get_youtube_playlist_item_by_id(item_id, user_id)

def get_youtube_playlist_items(user_id: str, playlist_id: str = None) -> List[dict]:
    db = get_db()
    if playlist_id is not None:
        cursor = db.execute(
            "SELECT * FROM youtube_playlist_items WHERE user_id = ? AND playlist_id = ? "
            "ORDER BY production_status ASC, scheduled_date ASC, created_at ASC",
            (user_id, playlist_id)
        )
    else:
        cursor = db.execute(
            "SELECT * FROM youtube_playlist_items WHERE user_id = ? "
            "ORDER BY production_status ASC, scheduled_date ASC, created_at ASC",
            (user_id,)
        )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_youtube_playlist_item_by_id(item_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM youtube_playlist_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def update_youtube_playlist_item(item_id: str, user_id: str, title: str = None,
                                 description=_UNSET, video_format: str = None,
                                 scheduled_date=_UNSET, publish_date=_UNSET,
                                 production_status: str = None) -> bool:
    db = get_db()
    updates, params = [], []
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not _UNSET:
        updates.append("description = ?")
        params.append(description)  # None clears it
    if video_format is not None:
        updates.append("video_format = ?")
        params.append(video_format)
    if scheduled_date is not _UNSET:
        updates.append("scheduled_date = ?")
        params.append(scheduled_date)  # None clears it
    if publish_date is not _UNSET:
        updates.append("publish_date = ?")
        params.append(publish_date)  # None clears it
    if production_status is not None:
        updates.append("production_status = ?")
        params.append(production_status)
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params += [item_id, user_id]
    cursor = db.execute(
        f"UPDATE youtube_playlist_items SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        tuple(params)
    )
    db.commit()
    return cursor.rowcount > 0

def delete_youtube_playlist_item(item_id: str, user_id: str) -> bool:
    db = get_db()
    cursor = db.execute(
        "DELETE FROM youtube_playlist_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0


def get_recent_plan_topics(user_id: str, days: int = 90) -> List[str]:
    """Topics already placed in any plan recently — dedup context for the suggester."""
    db = get_db()
    cursor = db.execute(
        "SELECT topic FROM plan_items WHERE user_id = ? AND created_at > datetime('now', ?)",
        (user_id, f"-{days} days")
    )
    return [row["topic"] for row in cursor.fetchall()]


# -- Plan Item Content Operations --

def create_plan_item_content(item_id: str, user_id: str, content_type: str, run_id: str) -> dict:
    db = get_db()
    content_id = generate_uuid()
    db.execute(
        "INSERT INTO plan_item_content (id, item_id, user_id, content_type, run_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (content_id, item_id, user_id, content_type, run_id)
    )
    db.commit()
    return get_plan_item_content_by_id(content_id, user_id)

def get_plan_item_contents(item_id: str, user_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM plan_item_content WHERE item_id = ? AND user_id = ? ORDER BY created_at DESC, id DESC",
        (item_id, user_id)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_plan_item_content_by_id(content_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM plan_item_content WHERE id = ? AND user_id = ?", (content_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def update_plan_item_content(content_id: str, content_ref_id: str = None,
                             review_status: str = None) -> None:
    db = get_db()
    updates, params = [], []
    if content_ref_id is not None:
        updates.append("content_ref_id = ?")
        params.append(content_ref_id)
    if review_status is not None:
        updates.append("review_status = ?")
        params.append(review_status)
        if review_status in ("approved", "rejected"):
            updates.append("reviewed_at = datetime('now')")
    if not updates:
        return
    params.append(content_id)
    db.execute(
        f"UPDATE plan_item_content SET {', '.join(updates)} WHERE id = ?",
        tuple(params)
    )
    db.commit()


# -- Saved Topic Operations --

def create_saved_topic(user_id: str, topic: str, rationale: str = None, niche: str = "ai",
                       source: str = "auto_research",
                       source_run_id: str = None) -> Optional[dict]:
    """Save one candidate topic as 'uncovered'.

    Returns None when the user already has a topic with the same normalized
    form — INSERT OR IGNORE against idx_saved_topics_user_norm, so re-running
    auto-research quietly skips ideas already in the backlog.
    """
    # Imported here: queries.py does not otherwise depend on content_tracker,
    # which opens a different database file (./data/content_tracker.db).
    from app.db.content_tracker import normalize_topic

    db = get_db()
    topic_id = generate_uuid()
    cursor = db.execute(
        "INSERT OR IGNORE INTO saved_topics "
        "(id, user_id, topic, topic_normalized, rationale, niche, source, source_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (topic_id, user_id, topic, normalize_topic(topic), rationale, niche, source, source_run_id)
    )
    db.commit()
    if cursor.rowcount == 0:
        return None
    return get_saved_topic_by_id(topic_id, user_id)

def get_saved_topics(user_id: str, status: str = None,
                     include_dismissed: bool = False) -> List[dict]:
    db = get_db()
    conditions = ["user_id = ?"]
    params: list = [user_id]
    if status:
        conditions.append("status = ?")
        params.append(status)
    if not include_dismissed:
        conditions.append("dismissed_at IS NULL")
    cursor = db.execute(
        f"SELECT * FROM saved_topics WHERE {' AND '.join(conditions)} "
        "ORDER BY created_at DESC, id DESC",
        tuple(params)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_saved_topic_by_id(topic_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM saved_topics WHERE id = ? AND user_id = ?", (topic_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def count_uncovered_topics(user_id: str) -> int:
    """Backlog size — the only query the banner needs."""
    db = get_db()
    cursor = db.execute(
        "SELECT COUNT(*) AS c FROM saved_topics "
        "WHERE user_id = ? AND status = 'uncovered' AND dismissed_at IS NULL",
        (user_id,)
    )
    return cursor.fetchone()["c"]

def get_latest_saved_topic_at(user_id: str) -> Optional[str]:
    db = get_db()
    cursor = db.execute(
        "SELECT MAX(created_at) AS latest FROM saved_topics "
        "WHERE user_id = ? AND status = 'uncovered' AND dismissed_at IS NULL",
        (user_id,)
    )
    return cursor.fetchone()["latest"]

def update_saved_topic(topic_id: str, user_id: str, status: str = None,
                       dismissed_at=_UNSET, topic: str = None) -> bool:
    db = get_db()
    updates, params = [], []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status == "generated":
            # First success wins; regenerating must not move the timestamp.
            updates.append("generated_at = COALESCE(generated_at, datetime('now'))")
    if dismissed_at is not _UNSET:
        updates.append("dismissed_at = ?")
        params.append(dismissed_at)
    if topic is not None:
        from app.db.content_tracker import normalize_topic
        updates.append("topic = ?")
        params.append(topic)
        updates.append("topic_normalized = ?")
        params.append(normalize_topic(topic))
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params += [topic_id, user_id]
    cursor = db.execute(
        f"UPDATE saved_topics SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        tuple(params)
    )
    db.commit()
    return cursor.rowcount > 0

def delete_saved_topic(topic_id: str, user_id: str) -> bool:
    db = get_db()
    cursor = db.execute(
        "DELETE FROM saved_topics WHERE id = ? AND user_id = ?", (topic_id, user_id)
    )
    db.commit()
    return cursor.rowcount > 0

def get_uncovered_topic_titles(user_id: str) -> List[str]:
    """Titles still awaiting generation — extra DO-NOT-REPEAT context for the
    suggester, so it stops re-proposing what is already in the backlog."""
    db = get_db()
    cursor = db.execute(
        "SELECT topic FROM saved_topics WHERE user_id = ? AND status != 'generated' "
        "ORDER BY created_at DESC LIMIT 40",
        (user_id,)
    )
    return [row["topic"] for row in cursor.fetchall()]


# -- Saved Topic Run Operations --

def create_saved_topic_run(saved_topic_id: str, user_id: str, content_type: str,
                           run_id: str) -> dict:
    db = get_db()
    row_id = generate_uuid()
    db.execute(
        "INSERT INTO saved_topic_runs (id, saved_topic_id, user_id, content_type, run_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (row_id, saved_topic_id, user_id, content_type, run_id)
    )
    db.commit()
    return get_saved_topic_run_by_id(row_id, user_id)

def get_saved_topic_runs(saved_topic_id: str, user_id: str) -> List[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM saved_topic_runs WHERE saved_topic_id = ? AND user_id = ? "
        "ORDER BY created_at DESC, id DESC",
        (saved_topic_id, user_id)
    )
    return [dict_from_row(row) for row in cursor.fetchall()]

def get_saved_topic_run_by_id(row_id: str, user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM saved_topic_runs WHERE id = ? AND user_id = ?", (row_id, user_id)
    )
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def update_saved_topic_run(row_id: str, content_ref_id: str = None,
                           review_status: str = None) -> None:
    db = get_db()
    updates, params = [], []
    if content_ref_id is not None:
        updates.append("content_ref_id = ?")
        params.append(content_ref_id)
    if review_status is not None:
        updates.append("review_status = ?")
        params.append(review_status)
    if not updates:
        return
    params.append(row_id)
    db.execute(
        f"UPDATE saved_topic_runs SET {', '.join(updates)} WHERE id = ?",
        tuple(params)
    )
    db.commit()


# -- Planner Analytics --

# Production lifecycle order (mirrors app.models.planner.ProductionStatus).
PRODUCTION_STATUS_ORDER = [
    "pending",
    "script_generated",
    "presentation_created",
    "video_created",
    "video_edited",
    "video_published",
]
CONTENT_TYPES = ["linkedin", "blog", "youtube_script"]
REVIEW_STATUSES = ["generating", "ready", "approved", "rejected", "failed"]


def _count_map(rows, key: str) -> Dict[str, int]:
    """Turn [{key: 'x', 'n': 3}, ...] rows into {'x': 3}."""
    return {row[key]: row["n"] for row in rows}


def get_planner_analytics(user_id: str) -> dict:
    """Aggregate planner metrics for the analytics dashboard (scoped to a user).

    Returns status breakdowns, content mix, generation reliability, schedule
    adherence, per-platform word metrics and top-line KPIs in a single dict.
    All sub-queries are index-backed GROUP BYs over the planner tables.
    """
    db = get_db()

    def rows(sql: str, params=(user_id,)):
        return [dict_from_row(r) for r in db.execute(sql, params).fetchall()]

    def scalar(sql: str, params=(user_id,)):
        row = db.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else 0

    # -- Plans --
    total_plans = scalar("SELECT COUNT(*) FROM content_plans WHERE user_id = ?")
    plans_by_status = _count_map(
        rows("SELECT status, COUNT(*) n FROM content_plans WHERE user_id = ? GROUP BY status"),
        "status",
    )
    plans_by_type = _count_map(
        rows("SELECT plan_type, COUNT(*) n FROM content_plans WHERE user_id = ? GROUP BY plan_type"),
        "plan_type",
    )
    plans_by_niche = _count_map(
        rows("SELECT niche, COUNT(*) n FROM content_plans WHERE user_id = ? GROUP BY niche"),
        "niche",
    )

    # -- Items funnel --
    status_counts = _count_map(
        rows(
            "SELECT production_status, COUNT(*) n FROM plan_items "
            "WHERE user_id = ? GROUP BY production_status"
        ),
        "production_status",
    )
    items_funnel = [
        {"status": s, "count": status_counts.get(s, 0)} for s in PRODUCTION_STATUS_ORDER
    ]
    total_items = sum(status_counts.values())
    published_items = status_counts.get("video_published", 0)
    items_by_format = _count_map(
        rows("SELECT video_format, COUNT(*) n FROM plan_items WHERE user_id = ? GROUP BY video_format"),
        "video_format",
    )
    items_by_source = _count_map(
        rows("SELECT topic_source, COUNT(*) n FROM plan_items WHERE user_id = ? GROUP BY topic_source"),
        "topic_source",
    )

    # -- Content mix (type x review status) --
    mix_rows = rows(
        "SELECT content_type, review_status, COUNT(*) n FROM plan_item_content "
        "WHERE user_id = ? GROUP BY content_type, review_status"
    )
    content_by_type = {t: 0 for t in CONTENT_TYPES}
    content_by_review = {s: 0 for s in REVIEW_STATUSES}
    for r in mix_rows:
        content_by_type[r["content_type"]] = content_by_type.get(r["content_type"], 0) + r["n"]
        content_by_review[r["review_status"]] = content_by_review.get(r["review_status"], 0) + r["n"]
    total_content = sum(content_by_type.values())

    # -- Volume over time (content pieces generated per day) --
    volume_over_time = rows(
        "SELECT date(created_at) AS day, COUNT(*) n FROM plan_item_content "
        "WHERE user_id = ? GROUP BY day ORDER BY day"
    )

    # -- Schedule adherence --
    overdue = scalar(
        "SELECT COUNT(*) FROM plan_items WHERE user_id = ? "
        "AND production_status != 'video_published' AND date(scheduled_date) < date('now')"
    )
    upcoming = scalar(
        "SELECT COUNT(*) FROM plan_items WHERE user_id = ? "
        "AND production_status != 'video_published' AND date(scheduled_date) >= date('now')"
    )
    schedule = {
        "published": published_items,
        "overdue": overdue,
        "upcoming": upcoming,
    }

    # -- Generation reliability (runs behind planner content) --
    gen_rows = rows(
        "SELECT r.status, COUNT(*) n, AVG(r.duration_seconds) avg_seconds "
        "FROM agent_runs r JOIN plan_item_content c ON c.run_id = r.id "
        "WHERE c.user_id = ? GROUP BY r.status"
    )
    generation = {
        r["status"]: {"count": r["n"], "avg_seconds": round(r["avg_seconds"] or 0, 2)}
        for r in gen_rows
    }
    avg_gen_seconds = round(
        scalar(
            "SELECT AVG(r.duration_seconds) FROM agent_runs r "
            "JOIN plan_item_content c ON c.run_id = r.id "
            "WHERE c.user_id = ? AND r.duration_seconds IS NOT NULL"
        )
        or 0,
        2,
    )

    # -- Per-platform word metrics (join to source tables via content_ref_id) --
    word_metrics = {}
    for content_type, table in (
        ("linkedin", "linkedin_posts"),
        ("blog", "blog_posts"),
        ("youtube_script", "youtube_scripts"),
    ):
        row = db.execute(
            f"SELECT COUNT(*) c, COALESCE(SUM(word_count), 0) total, "
            f"COALESCE(AVG(word_count), 0) avg FROM {table} WHERE id IN "
            f"(SELECT content_ref_id FROM plan_item_content "
            f"WHERE user_id = ? AND content_type = ?)",
            (user_id, content_type),
        ).fetchone()
        word_metrics[content_type] = {
            "count": row[0],
            "total_words": row[1],
            "avg_words": round(row[2], 1),
        }

    # -- Top-line KPIs --
    approved = content_by_review.get("approved", 0)
    rejected = content_by_review.get("rejected", 0)
    ready = content_by_review.get("ready", 0)
    reviewed_pool = approved + rejected + ready
    approval_rate = round(100 * approved / reviewed_pool, 1) if reviewed_pool else 0.0

    return {
        "kpis": {
            "total_plans": total_plans,
            "total_items": total_items,
            "total_content": total_content,
            "published_items": published_items,
            "approval_rate": approval_rate,
            "avg_gen_seconds": avg_gen_seconds,
        },
        "plans": {
            "by_status": plans_by_status,
            "by_type": plans_by_type,
            "by_niche": plans_by_niche,
        },
        "items_funnel": items_funnel,
        "items_by_format": items_by_format,
        "items_by_source": items_by_source,
        "content_by_type": content_by_type,
        "content_by_review": content_by_review,
        "volume_over_time": volume_over_time,
        "schedule": schedule,
        "generation": generation,
        "word_metrics": word_metrics,
    }


# -- Google OAuth Token Operations --

def save_google_tokens(user_id: str, token_json_encrypted: str, scopes: str = None,
                       connected_email: str = None) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO google_oauth_tokens (user_id, token_json_encrypted, scopes, connected_email, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            token_json_encrypted = excluded.token_json_encrypted,
            scopes = COALESCE(excluded.scopes, scopes),
            connected_email = COALESCE(excluded.connected_email, connected_email),
            updated_at = datetime('now')
        """,
        (user_id, token_json_encrypted, scopes, connected_email)
    )
    db.commit()

def get_google_tokens(user_id: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM google_oauth_tokens WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return dict_from_row(row) if row else None

def delete_google_tokens(user_id: str) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM google_oauth_tokens WHERE user_id = ?", (user_id,))
    db.commit()
    return cursor.rowcount > 0
