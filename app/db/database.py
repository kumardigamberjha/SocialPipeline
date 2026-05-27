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

