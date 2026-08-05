import sqlite3
import threading
import uuid
from typing import Any, Dict
from app.config import get_settings

# Thread-local storage for DB connections
_local = threading.local()

def get_db() -> sqlite3.Connection:
    """Returns a thread-local SQLite connection with WAL and Foreign Keys enabled."""
    if not hasattr(_local, "connection"):
        settings = get_settings()
        # Connect to SQLite database
        conn = sqlite3.connect(
            settings.sqlite_db_path,
            check_same_thread=False,
            isolation_level=None  # Autocommit mode by default or manage manually
        )
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys=ON;")
        
        _local.connection = conn
    return _local.connection

def close_db():
    """Closes the thread-local SQLite connection if it exists."""
    if hasattr(_local, "connection"):
        _local.connection.close()
        del _local.connection

def dict_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts an sqlite3.Row object to a plain dictionary."""
    return dict(row)

def generate_uuid() -> str:
    """Generates a UUID string."""
    return str(uuid.uuid4())

def init_db():
    """Initializes the database schema."""
    conn = get_db()
    
    # Run all CREATE TABLE statements
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            provider_used TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            final_result TEXT,
            duration_seconds REAL,
            image_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        
        CREATE TABLE IF NOT EXISTS task_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            agent_name TEXT NOT NULL,
            task_name TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL DEFAULT 'done',
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            api_key_encrypted TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS usage_limits (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            plan TEXT NOT NULL DEFAULT 'free',
            runs_this_month INTEGER DEFAULT 0,
            max_runs_per_month INTEGER DEFAULT 10,
            reset_at TEXT,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT
        );
        
        CREATE TABLE IF NOT EXISTS published_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_normalized TEXT NOT NULL,
            topic_original TEXT NOT NULL,
            niche TEXT NOT NULL,
            content_types_generated TEXT NOT NULL,
            research_sources TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            run_id TEXT
        );
        
        CREATE TABLE IF NOT EXISTS research_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT UNIQUE NOT NULL,
            results_json TEXT NOT NULL,
            cached_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS niche_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_niche TEXT DEFAULT 'ai',
            last_run_at TEXT
        );

        CREATE TABLE IF NOT EXISTS blog_posts (
            id TEXT PRIMARY KEY,
            run_id TEXT REFERENCES agent_runs(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,          -- full markdown blog post ~20000 words
            word_count INTEGER,
            reading_time_minutes INTEGER,
            niche TEXT,
            approved INTEGER DEFAULT 0,     -- SQLite has no BOOLEAN, use 0/1
            deleted_at TEXT,                -- soft delete timestamp; NULL = live
            published_at TEXT DEFAULT (datetime('now')),
            slug TEXT UNIQUE                -- URL-safe version of title
        );

        CREATE TABLE IF NOT EXISTS linkedin_posts (
            id TEXT PRIMARY KEY,
            run_id TEXT REFERENCES agent_runs(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            post_text TEXT NOT NULL,
            hook TEXT,
            angle_type TEXT,
            word_count INTEGER,
            hashtag_count INTEGER,
            approved INTEGER DEFAULT 0,     -- 0/1 for SQLite boolean
            niche TEXT,
            deleted_at TEXT,                 -- soft delete
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS content_plans (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            plan_type TEXT NOT NULL CHECK (plan_type IN ('weekly', 'monthly')),
            niche TEXT DEFAULT 'ai',
            start_date TEXT NOT NULL,       -- ISO date 'YYYY-MM-DD'
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',   -- 'active' | 'archived'
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- production_status / review_status have NO CHECK constraint: SQLite cannot
        -- alter a CHECK later and the stage list may grow. Validated in Pydantic.
        CREATE TABLE IF NOT EXISTS plan_items (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES content_plans(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,   -- ISO date: working / production slot
            publish_date TEXT,              -- ISO date: when the content goes live (optional)
            event_time TEXT,                -- 'HH:MM' local time for the calendar reminder (optional)
            event_duration_minutes INTEGER, -- calendar event length in minutes (optional; default 60)
            notes TEXT,
            topic_source TEXT DEFAULT 'manual',  -- 'ai' | 'manual'
            video_format TEXT DEFAULT 'full',    -- 'short' | 'full' (drives YouTube script length)
            production_status TEXT NOT NULL DEFAULT 'pending',
            gcal_event_id TEXT,
            gcal_event_link TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- One row per (item x content_type) generation attempt; newest wins on
        -- regenerate. Content bodies stay in linkedin_posts / blog_posts /
        -- youtube_scripts; this is only the link + human-review state.
        CREATE TABLE IF NOT EXISTS plan_item_content (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES plan_items(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id),
            content_type TEXT NOT NULL,     -- 'linkedin' | 'blog' | 'youtube_script'
            run_id TEXT REFERENCES agent_runs(id),
            content_ref_id TEXT,            -- id in the content_type's own table
            review_status TEXT NOT NULL DEFAULT 'generating',
            reviewed_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Candidate topics an auto-research run surfaced but did NOT generate
        -- ("uncovered"), plus anything the user adds by hand. No CHECK on status:
        -- SQLite cannot alter a CHECK later and the stage list may grow.
        -- Validated in Pydantic (app/models/saved_topics.py).
        CREATE TABLE IF NOT EXISTS saved_topics (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            topic_normalized TEXT NOT NULL,      -- dedup key; content_tracker.normalize_topic()
            rationale TEXT,                      -- "why now" line from the suggester
            niche TEXT DEFAULT 'ai',
            source TEXT DEFAULT 'auto_research', -- 'auto_research' | 'manual'
            source_run_id TEXT REFERENCES agent_runs(id),  -- run whose sibling was generated
            status TEXT NOT NULL DEFAULT 'uncovered',      -- 'uncovered'|'generating'|'generated'
            dismissed_at TEXT,                   -- hidden without generating; NULL = still listed
            generated_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- One row per (saved_topic x content_type) attempt; newest wins on
        -- regenerate. Mirrors plan_item_content but owned by saved_topics --
        -- plan_item_content.item_id is a hard FK to plan_items and cannot be
        -- reused without inventing a fake plan. Bodies stay in the content tables.
        CREATE TABLE IF NOT EXISTS saved_topic_runs (
            id TEXT PRIMARY KEY,
            saved_topic_id TEXT NOT NULL REFERENCES saved_topics(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id),
            content_type TEXT NOT NULL,     -- 'linkedin' | 'blog' | 'youtube_script'
            run_id TEXT REFERENCES agent_runs(id),
            content_ref_id TEXT,            -- id in the content_type's own table
            review_status TEXT NOT NULL DEFAULT 'generating',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Locally-tracked "pending → published" video ideas attached to a real
        -- YouTube playlist (by playlist_id). Mirrors plan_items; no CHECK on
        -- production_status (validated in Pydantic, the stage list may grow).
        CREATE TABLE IF NOT EXISTS youtube_playlist_items (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            playlist_id TEXT NOT NULL,           -- the YouTube playlist it's attached to
            playlist_title TEXT,                 -- denormalized for display
            title TEXT NOT NULL,                 -- video title / topic
            description TEXT,                    -- angle / notes (trend rationale on add)
            video_format TEXT DEFAULT 'full',    -- 'short' | 'full'
            scheduled_date TEXT,                 -- ISO date: working slot (optional)
            publish_date TEXT,                   -- ISO date: go-live (optional)
            production_status TEXT NOT NULL DEFAULT 'pending',
            source TEXT DEFAULT 'manual',        -- 'trend_idea' | 'manual'
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS youtube_scripts (
            id TEXT PRIMARY KEY,
            run_id TEXT REFERENCES agent_runs(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            topic TEXT NOT NULL,
            title TEXT,
            script TEXT NOT NULL,           -- full markdown script with cue tags
            word_count INTEGER,
            seo_title TEXT,
            seo_description TEXT,
            seo_tags TEXT,                  -- JSON array string
            approved INTEGER DEFAULT 0,
            niche TEXT,
            deleted_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS google_oauth_tokens (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            token_json_encrypted TEXT NOT NULL,  -- Fernet-encrypted Credentials JSON
            scopes TEXT,
            connected_email TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS youtube_traffic_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            traffic_source TEXT UNIQUE NOT NULL,
            views INTEGER DEFAULT 0,
            watch_time_hours REAL DEFAULT 0.0,
            avg_view_duration TEXT,
            impressions INTEGER,
            impressions_ctr REAL,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS youtube_published_videos (
            video_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            publish_time TEXT,
            duration_seconds INTEGER,
            views INTEGER DEFAULT 0,
            watch_time_hours REAL DEFAULT 0.0,
            subscribers INTEGER DEFAULT 0,
            impressions INTEGER,
            impressions_ctr REAL,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_blog_posts_user ON blog_posts(user_id, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);

        CREATE INDEX IF NOT EXISTS idx_linkedin_posts_user ON linkedin_posts(user_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON plan_items(plan_id, scheduled_date);
        CREATE INDEX IF NOT EXISTS idx_plan_item_content_item ON plan_item_content(item_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_youtube_scripts_user ON youtube_scripts(user_id, created_at DESC);

        -- One saved row per normalized topic per user: re-running auto-research
        -- must not re-save an idea already sitting in the backlog.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_topics_user_norm ON saved_topics(user_id, topic_normalized);
        CREATE INDEX IF NOT EXISTS idx_saved_topics_user_status ON saved_topics(user_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_saved_topic_runs_topic ON saved_topic_runs(saved_topic_id, created_at DESC);

        -- Seed niche_state if empty
        INSERT OR IGNORE INTO niche_state (id, last_niche) VALUES (1, 'ai');
        
        -- Seed dummy user for tokenless WebSocket connections
        INSERT OR IGNORE INTO users (id, email, password_hash) VALUES ('00000000-0000-0000-0000-000000000000', 'dummy@example.com', 'dummy_hash');
        INSERT OR IGNORE INTO usage_limits (user_id, plan, runs_this_month, max_runs_per_month, reset_at) VALUES ('00000000-0000-0000-0000-000000000000', 'free', 0, 100, datetime('now', '+1 month'));
    """)
    
    # Run migration ALTERS to handle existing tables
    try:
        conn.execute("ALTER TABLE usage_limits ADD COLUMN stripe_customer_id TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE usage_limits ADD COLUMN stripe_subscription_id TEXT;")
    except sqlite3.OperationalError:
        pass
    # blog_posts gained approval + soft-delete after the table first shipped.
    try:
        conn.execute("ALTER TABLE blog_posts ADD COLUMN approved INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE blog_posts ADD COLUMN deleted_at TEXT;")
    except sqlite3.OperationalError:
        pass
    # plan_items gained an optional publish_date after the table first shipped.
    try:
        conn.execute("ALTER TABLE plan_items ADD COLUMN publish_date TEXT;")
    except sqlite3.OperationalError:
        pass
    # plan_items gained a short/full video_format after the table first shipped.
    try:
        conn.execute("ALTER TABLE plan_items ADD COLUMN video_format TEXT DEFAULT 'full';")
    except sqlite3.OperationalError:
        pass
    # plan_items gained an optional calendar event_time after the table first shipped.
    try:
        conn.execute("ALTER TABLE plan_items ADD COLUMN event_time TEXT;")
    except sqlite3.OperationalError:
        pass
    # plan_items gained an optional calendar event duration after the table first shipped.
    try:
        conn.execute("ALTER TABLE plan_items ADD COLUMN event_duration_minutes INTEGER;")
    except sqlite3.OperationalError:
        pass
