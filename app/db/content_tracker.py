"""
SQLite3 Content Tracker — deduplication memory for Wings of AI.

Manages a local SQLite3 database at ./data/content_tracker.db with three tables:
    - published_topics:  every topic researched and content generated
    - research_cache:    cached research results to avoid redundant API calls (6h TTL)
    - niche_state:       niche rotation state (alternates between 'ai' and 'software_dev')

This module is fully synchronous and safe to call from Celery workers,
CrewAI callbacks, and FastAPI route handlers alike.
"""

import difflib
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/content_tracker.db")
DUPLICATE_THRESHOLD = 0.80  # fuzzy similarity above this = duplicate

# Common English stop words stripped during normalization
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out",
    "about", "this", "that", "these", "those", "it", "its", "and", "but",
    "or", "nor", "not", "so", "yet", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "how", "what", "which", "who", "whom", "why",
    "where", "when", "all", "any", "every", "new", "latest", "using",
    "use", "build", "building", "create", "creating", "make", "making",
})

# Thread-local storage for connections
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating one if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _init_tables(_local.conn)
    return _local.conn


def _init_tables(conn: sqlite3.Connection):
    """Create all tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS published_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_normalized TEXT NOT NULL,
            topic_original TEXT NOT NULL,
            niche TEXT NOT NULL,
            content_types_generated TEXT NOT NULL,
            research_sources TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            run_id TEXT
        );

        CREATE TABLE IF NOT EXISTS research_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT UNIQUE NOT NULL,
            results_json TEXT NOT NULL,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS niche_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_niche TEXT DEFAULT 'ai',
            last_run_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_published_topics_normalized
            ON published_topics(topic_normalized);
        CREATE INDEX IF NOT EXISTS idx_published_topics_niche
            ON published_topics(niche);
        CREATE INDEX IF NOT EXISTS idx_research_cache_hash
            ON research_cache(query_hash);
        CREATE INDEX IF NOT EXISTS idx_research_cache_expires
            ON research_cache(expires_at);
    """)
    conn.commit()


# ── Topic normalization ──────────────────────────────────────────────────────

def normalize_topic(topic: str) -> str:
    """
    Normalize a topic string for fuzzy matching:
        1. Lowercase
        2. Strip punctuation
        3. Remove stop words
        4. Sort remaining words alphabetically (order-invariant)
        5. Collapse whitespace
    """
    text = topic.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if w not in _STOP_WORDS and len(w) > 1]
    words.sort()
    return " ".join(words)


# ── Public API ───────────────────────────────────────────────────────────────

def is_duplicate_topic(topic: str) -> tuple[bool, float]:
    """
    Check if a topic has already been covered.

    Normalizes the incoming topic, then checks published_topics using:
        1. Exact match on topic_normalized
        2. Fuzzy similarity (difflib.SequenceMatcher ratio > 0.80) against
           all topics from the last 90 days

    Returns:
        (True, similarity_score) if duplicate, (False, 0.0) otherwise.
    """
    conn = _get_conn()
    normalized = normalize_topic(topic)

    if not normalized:
        return False, 0.0

    # 1. Exact match
    row = conn.execute(
        "SELECT id FROM published_topics WHERE topic_normalized = ?",
        (normalized,),
    ).fetchone()
    if row:
        return True, 1.0

    # 2. Fuzzy match against recent topics (last 90 days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    rows = conn.execute(
        "SELECT topic_normalized FROM published_topics WHERE generated_at > ?",
        (cutoff,),
    ).fetchall()

    best_score = 0.0
    for row in rows:
        existing_normalized = row["topic_normalized"]
        ratio = difflib.SequenceMatcher(None, normalized, existing_normalized).ratio()
        if ratio > best_score:
            best_score = ratio

    if best_score >= DUPLICATE_THRESHOLD:
        return True, round(best_score, 3)

    return False, round(best_score, 3)


def mark_topic_published(
    topic: str,
    niche: str,
    content_types: list[str],
    sources: list[str],
    run_id: str,
):
    """
    Record a topic as published in the content tracker.

    Args:
        topic:          The original topic string.
        niche:          'ai' or 'software_dev'.
        content_types:  List of content types generated, e.g. ["youtube", "linkedin"].
        sources:        List of research source URLs used.
        run_id:         UUID linking back to agent_runs.
    """
    conn = _get_conn()
    normalized = normalize_topic(topic)

    conn.execute(
        """INSERT INTO published_topics
           (topic_normalized, topic_original, niche, content_types_generated, research_sources, run_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            normalized,
            topic,
            niche,
            json.dumps(content_types),
            json.dumps(sources),
            run_id,
        ),
    )
    conn.commit()
    logger.info("Marked topic as published: %r (niche=%s, run_id=%s)", topic[:60], niche, run_id)


def get_published_count(niche: Optional[str] = None, days: int = 30) -> int:
    """Return the number of topics published in the last N days, optionally filtered by niche."""
    conn = _get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if niche:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM published_topics WHERE niche = ? AND generated_at > ?",
            (niche, cutoff),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM published_topics WHERE generated_at > ?",
            (cutoff,),
        ).fetchone()

    return row["cnt"] if row else 0


# ── Research Cache ───────────────────────────────────────────────────────────

def _hash_query(query: str) -> str:
    """Generate a stable hash for a search query."""
    normalized = normalize_topic(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def get_cache(query_hash: str) -> Optional[list]:
    """
    Return cached research results if they exist and haven't expired.
    Returns None if no valid cache exists.
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        "SELECT results_json FROM research_cache WHERE query_hash = ? AND expires_at > ?",
        (query_hash, now),
    ).fetchone()

    if row:
        try:
            return json.loads(row["results_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    return None


def set_cache(query_hash: str, results: list, ttl_hours: int = 6):
    """
    Save research results to cache with a TTL.

    Args:
        query_hash:  SHA256 hash of the normalized query.
        results:     List of dicts (serialized ResearchResult objects).
        ttl_hours:   Hours until cache entry expires (default: 6).
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)

    results_json = json.dumps(results, default=str)

    conn.execute(
        """INSERT INTO research_cache (query_hash, results_json, cached_at, expires_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(query_hash) DO UPDATE SET
               results_json = excluded.results_json,
               cached_at = excluded.cached_at,
               expires_at = excluded.expires_at""",
        (query_hash, results_json, now.isoformat(), expires.isoformat()),
    )
    conn.commit()


def clear_expired_cache():
    """Delete all expired cache entries."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    deleted = conn.execute(
        "DELETE FROM research_cache WHERE expires_at < ?", (now,)
    ).rowcount
    conn.commit()
    if deleted:
        logger.info("Cleared %d expired research cache entries", deleted)


# ── Niche Rotation ───────────────────────────────────────────────────────────

def get_niche_state() -> str:
    """Return the last used niche ('ai' or 'software_dev')."""
    conn = _get_conn()
    row = conn.execute("SELECT last_niche FROM niche_state WHERE id = 1").fetchone()
    if row:
        return row["last_niche"]

    # Initialize if no state exists
    conn.execute(
        "INSERT OR IGNORE INTO niche_state (id, last_niche, last_run_at) VALUES (1, 'ai', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    return "ai"


def rotate_niche() -> str:
    """
    Alternate between 'ai' and 'software_dev', save state, return the NEW niche.
    """
    conn = _get_conn()
    current = get_niche_state()
    new_niche = "software_dev" if current == "ai" else "ai"
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO niche_state (id, last_niche, last_run_at) VALUES (1, ?, ?)
           ON CONFLICT(id) DO UPDATE SET last_niche = excluded.last_niche, last_run_at = excluded.last_run_at""",
        (new_niche, now),
    )
    conn.commit()
    logger.info("Niche rotated: %s → %s", current, new_niche)
    return new_niche


# ── Convenience ──────────────────────────────────────────────────────────────

def get_recent_topics(limit: int = 20) -> list[dict]:
    """Return the most recent published topics for debugging/display."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT topic_original, niche, content_types_generated, generated_at, run_id "
        "FROM published_topics ORDER BY generated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
