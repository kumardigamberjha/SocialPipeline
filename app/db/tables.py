"""
The complete database schema.

This is a transcription of the raw-SQL schema that used to live in
``app/db/database.py:init_db()``, ported to SQLAlchemy and Postgres, with three
deliberate changes:

1. **Every tenant-owned table carries ``user_id``.** The SQLite schema keyed
   ``youtube_videos_live`` and ``youtube_published_videos`` on ``video_id``
   alone and ``youtube_traffic_sources`` on ``traffic_source`` alone, so two
   users syncing the same channel — or simply the same public video — would
   overwrite each other's rows. Those are now composite. Because the legacy
   data is being discarded rather than migrated, the correct shape is defined
   here from the start instead of being retrofitted by a later migration.

2. **Real types.** SQLite stored booleans as 0/1 integers, timestamps as
   ``TEXT`` via ``datetime('now')`` (naive, no zone) and JSON as ``TEXT``.
   Those become ``BOOLEAN``, ``TIMESTAMPTZ`` and ``JSONB``.

3. **``ON DELETE CASCADE`` throughout.** Deleting a user must actually empty
   their data; the old schema left most references unqualified.

``research_cache`` is intentionally *not* tenant-scoped — see its docstring.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import IsoDate, IsoDateTime

# Python sees plain strings, matching the existing str(uuid4()) call sites.
UUIDStr = UUID(as_uuid=False)
TZDateTime = IsoDateTime()


def _uuid() -> str:
    return str(uuid.uuid4())


def _pk_uuid() -> Mapped[str]:
    return mapped_column(UUIDStr, primary_key=True, default=_uuid)


def _owner_fk(**kwargs) -> Mapped[str]:
    """``user_id`` FK that cascades. The spine of tenant isolation."""
    kwargs.setdefault("nullable", False)
    kwargs.setdefault("index", True)
    return mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), **kwargs
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(TZDateTime, nullable=False, server_default=text("now()"))


# ─────────────────────────────────────────────────────────────────────────────
# Identity
# ─────────────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _pk_uuid()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        # Case-insensitive uniqueness. The SQLite schema used a plain
        # `email TEXT UNIQUE`, under which Bob@x.com and bob@x.com were two
        # separate accounts — an account-takeover vector at signup.
        Index(
            "uq_users_email_lower",
            text("lower(email)"),
            unique=True,
        ),
    )


class RefreshToken(Base):
    """One row per issued refresh token; a login starts a *family*.

    Rotation inserts a child row and stamps ``used_at`` on the parent. Seeing a
    token that already has ``used_at`` set means the same token was presented
    twice — either a race or a theft — and the whole family is revoked.

    Only ``sha256(secret)`` is stored, so a database leak does not yield usable
    refresh tokens.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = _pk_uuid()
    family_id: Mapped[str] = mapped_column(UUIDStr, nullable=False, index=True)
    user_id: Mapped[str] = _owner_fk()
    token_hash: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    issued_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)


class UsageLimit(Base):
    __tablename__ = "usage_limits"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'free'"))
    runs_this_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    max_runs_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    reset_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = _owner_fk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runs and jobs
# ─────────────────────────────────────────────────────────────────────────────


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    provider_used: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    final_result: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Double)
    image_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="status_valid",
        ),
        Index("ix_agent_runs_user_created", "user_id", text("created_at DESC")),
    )


class TaskStep(Base):
    """Per-agent telemetry for a run.

    ``user_id`` is denormalized from ``agent_runs`` deliberately: the progress
    WebSocket reads this table on every tick, and carrying the owner here turns
    the ownership check into a predicate instead of a join.
    """

    __tablename__ = "task_steps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = _owner_fk()
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'done'"))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_task_steps_run_id_id", "run_id", "id"),)


class Job(Base):
    """Async work the API handed to Celery.

    This exists so the frontend never has to hold a Celery task id. A task id is
    an unauthenticated bearer capability — anyone who learns one can read the
    result — whereas ``jobs`` rows are ownership-checked like everything else.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'queued'")
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    step_label: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="state_valid",
        ),
        Index("ix_jobs_user_created", "user_id", text("created_at DESC")),
        # Partial index: the scheduler only ever scans unfinished work.
        Index(
            "ix_jobs_active",
            "state",
            postgresql_where=text("state IN ('queued', 'running')"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Generated content
# ─────────────────────────────────────────────────────────────────────────────


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[str] = _pk_uuid()
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int | None] = mapped_column(Integer)
    reading_time_minutes: Mapped[int | None] = mapped_column(Integer)
    niche: Mapped[str | None] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    published_at: Mapped[datetime] = _created_at()
    # Slugs address the public blog reader, so they stay globally unique.
    slug: Mapped[str | None] = mapped_column(Text, unique=True)

    __table_args__ = (
        Index("ix_blog_posts_user_published", "user_id", text("published_at DESC")),
    )


class LinkedinPost(Base):
    __tablename__ = "linkedin_posts"

    id: Mapped[str] = _pk_uuid()
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    post_text: Mapped[str] = mapped_column(Text, nullable=False)
    hook: Mapped[str | None] = mapped_column(Text)
    angle_type: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int | None] = mapped_column(Integer)
    hashtag_count: Mapped[int | None] = mapped_column(Integer)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    niche: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_linkedin_posts_user_created", "user_id", text("created_at DESC")),
    )


class YoutubeScript(Base):
    __tablename__ = "youtube_scripts"

    id: Mapped[str] = _pk_uuid()
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int | None] = mapped_column(Integer)
    seo_title: Mapped[str | None] = mapped_column(Text)
    seo_description: Mapped[str | None] = mapped_column(Text)
    seo_tags: Mapped[list | None] = mapped_column(JSONB)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    niche: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_youtube_scripts_user_created", "user_id", text("created_at DESC")),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Planner
# ─────────────────────────────────────────────────────────────────────────────


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[str] = _pk_uuid()
    user_id: Mapped[str] = _owner_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_type: Mapped[str] = mapped_column(Text, nullable=False)
    niche: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ai'"))
    start_date: Mapped[str] = mapped_column(IsoDate, nullable=False)
    end_date: Mapped[str] = mapped_column(IsoDate, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    # The channel this plan belongs to. Deliberately no CHECK constraint: unlike
    # plan_type, no code branches on the value — it selects a filter and a label.
    # Adding a platform is a Literal edit in app/models/planner.py plus a
    # dropdown entry, never a migration. Same choice as user_goals.platform.
    platform: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'youtube'")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        # 'board' is the open-ended Kanban plan; it skips the weekly/monthly
        # end_date arithmetic in the router. Kept as a CHECK because the router
        # does branch on this one.
        CheckConstraint(
            "plan_type IN ('weekly', 'monthly', 'board')", name="plan_type_valid"
        ),
        Index(
            "ix_content_plans_user_platform",
            "user_id",
            "platform",
            text("start_date DESC"),
        ),
        # Makes get_or_create_board_plan race-free: two concurrent writes cannot
        # leave a user with two boards for one platform.
        Index(
            "uq_content_plans_user_platform_board",
            "user_id",
            "platform",
            unique=True,
            postgresql_where=text("plan_type = 'board'"),
        ),
    )


class PlanItem(Base):
    """A scheduled slot in a content plan.

    ``production_status`` deliberately has no CHECK constraint: the stage list
    grows, and it is validated in Pydantic (``app/models/``) instead.
    """

    __tablename__ = "plan_items"

    id: Mapped[str] = _pk_uuid()
    plan_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False
    )
    # Covered by the composite indexes below, including the cascade lookup.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: a backlog "idea" card has no date yet. Backfilling a placeholder
    # would make every undated idea count as overdue in get_planner_analytics.
    scheduled_date: Mapped[str | None] = mapped_column(IsoDate)
    publish_date: Mapped[str | None] = mapped_column(IsoDate)
    event_time: Mapped[str | None] = mapped_column(String(5))  # 'HH:MM', local
    event_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    topic_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'")
    )
    video_format: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'full'")
    )
    production_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    gcal_event_id: Mapped[str | None] = mapped_column(Text)
    gcal_event_link: Mapped[str | None] = mapped_column(Text)
    # Denormalized from the parent plan, not joined: the board reads and the
    # analytics GROUP BYs hit this table with no plan in scope, and a join would
    # make the composite indexes below impossible. create_plan_item resolves it
    # from the plan, which is the one place the invariant is enforced.
    platform: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'youtube'")
    )
    # Platform-specific fields that do not deserve a column on every row —
    # instagram: type, slides_count, caption, image_prompt, source, likes,
    # shares, saves, reach. Keys are FLAT because updates shallow-merge with
    # `meta || patch`: a nested object would be replaced wholesale, so patching
    # one metric would zero the others. NOT NULL for the same reason —
    # `NULL || '{...}'` is NULL, which would silently wipe the row.
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_plan_items_plan_scheduled", "plan_id", "scheduled_date"),
        # The Kanban / board read: replaces ix_instagram_board_items_user_status.
        Index(
            "ix_plan_items_user_platform_status",
            "user_id",
            "platform",
            "production_status",
            text("created_at DESC"),
        ),
        # Cross-plan calendar and list views.
        Index(
            "ix_plan_items_user_platform_scheduled",
            "user_id",
            "platform",
            "scheduled_date",
        ),
    )


class PlanItemContent(Base):
    """One row per (plan item × content type) generation attempt.

    Only the link and the human-review state live here; bodies stay in
    ``blog_posts`` / ``linkedin_posts`` / ``youtube_scripts``.
    """

    __tablename__ = "plan_item_content"

    id: Mapped[str] = _pk_uuid()
    item_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("plan_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = _owner_fk()
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    content_ref_id: Mapped[str | None] = mapped_column(UUIDStr)
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'generating'")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_plan_item_content_item_created", "item_id", text("created_at DESC")),
        # Serves the assistant's user-wide review-queue read
        # (queries.get_pending_review_contents); ix_plan_item_content_item_created
        # leads with item_id and cannot. Created in 0008 but never declared here,
        # so `alembic revision --autogenerate` saw an index with no model behind
        # it and emitted a drop (b139d561a452). Declared now so that cannot recur.
        Index(
            "ix_plan_item_content_user_review",
            "user_id",
            "review_status",
            text("created_at DESC"),
        ),
    )


class SavedTopic(Base):
    """Backlog of candidate topics surfaced but not yet generated."""

    __tablename__ = "saved_topics"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    topic_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    niche: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ai'"))
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'auto_research'")
    )
    source_run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'uncovered'")
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    generated_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        # Re-running auto-research must not re-save an idea already in the
        # backlog — but only within one user's backlog.
        UniqueConstraint("user_id", "topic_normalized", name="uq_saved_topics_user_norm"),
        Index(
            "ix_saved_topics_user_status",
            "user_id",
            "status",
            text("created_at DESC"),
        ),
    )


class SavedTopicRun(Base):
    """Mirrors ``plan_item_content`` but owned by a saved topic.

    They cannot share a table: ``plan_item_content.item_id`` is a hard FK to
    ``plan_items``, and reusing it would mean inventing a fake plan.
    """

    __tablename__ = "saved_topic_runs"

    id: Mapped[str] = _pk_uuid()
    saved_topic_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("saved_topics.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = _owner_fk()
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    content_ref_id: Mapped[str | None] = mapped_column(UUIDStr)
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'generating'")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index(
            "ix_saved_topic_runs_topic_created",
            "saved_topic_id",
            text("created_at DESC"),
        ),
    )


class NicheState(Base):
    """Per-user cursor for the auto-research niche rotation.

    Was a global singleton row (``id = 1``) in SQLite.
    """

    __tablename__ = "niche_state"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_niche: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ai'")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class PublishedTopic(Base):
    """Dedup ledger of topics already generated, per user."""

    __tablename__ = "published_topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    topic_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    topic_original: Mapped[str] = mapped_column(Text, nullable=False)
    niche: Mapped[str] = mapped_column(Text, nullable=False)
    content_types_generated: Mapped[list] = mapped_column(JSONB, nullable=False)
    research_sources: Mapped[list | None] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = _created_at()
    run_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("agent_runs.id", ondelete="SET NULL")
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "topic_normalized", name="uq_published_topics_user_norm"
        ),
    )


class ResearchCache(Base):
    """Cached web-research results, keyed by query hash.

    **Deliberately global, not tenant-scoped.** The contents are a pure function
    of the query — public web results, nothing user-derived. Scoping it per user
    would multiply outbound search calls by the user count and buy no isolation.
    Anything user-specific must not be cached here.
    """

    __tablename__ = "research_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    results_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cached_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False, index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Connected accounts (OAuth)
# ─────────────────────────────────────────────────────────────────────────────


class GoogleOAuthToken(Base):
    """Fernet-encrypted Google credentials JSON. Covers Calendar *and* YouTube."""

    __tablename__ = "google_oauth_tokens"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_json_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    scopes: Mapped[str | None] = mapped_column(Text)
    connected_email: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _created_at()


class InstagramOAuthToken(Base):
    """Per-user Instagram Business token, Fernet-encrypted.

    Replaces the previous design, which wrote a single plaintext token into
    ``os.environ`` and rewrote ``app/.env`` on disk — invisible to other
    workers, lost on restart, and inherently single-account.
    """

    __tablename__ = "instagram_oauth_tokens"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    ig_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    token_expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    scopes: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────


class InstagramSnapshot(Base):
    """Nightly Instagram analytics snapshot; the fallback behind the Redis cache.

    The cache service prunes to the last 7 rows *per user*.
    """

    __tablename__ = "instagram_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    profile_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # The default range's stats, kept for readers that want just one block.
    stats_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Every supported time_range -> its own stats block. Without this the
    # dashboard's range dropdown was decorative: one blob answered all four.
    stats_by_range_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # What the sync could actually see (posts paginated vs. the account's total,
    # how many carry insights). Achievements reads it to decide whether a sum is
    # a lifetime total or a partial sample.
    coverage_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    posts_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    hashtags_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    synced_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_instagram_snapshots_user_synced", "user_id", text("synced_at DESC")),
    )


class InstagramAiReport(Base):
    """A generated AI Strategy Brief or Content Roadmap for an Instagram account.

    Both were previously ephemeral — computed on request and handed straight
    to the frontend with no DB write, so a page refresh lost them. This keeps
    the most recent one of each ``report_type`` so the UI can reload it.
    """

    __tablename__ = "instagram_ai_reports"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint(
            "report_type IN ('strategy', 'roadmap')", name="instagram_ai_report_type_valid"
        ),
        Index(
            "ix_instagram_ai_reports_user_type_created",
            "user_id",
            "report_type",
            text("created_at DESC"),
        ),
    )


class YoutubeVideoLive(Base):
    """Full video metadata pulled from the YouTube Data API, upserted per sync.

    Primary key is ``(user_id, video_id)``. Under the old ``video_id``-only key,
    two users syncing overwrote each other — including two users who merely had
    the same public video in view.
    """

    __tablename__ = "youtube_videos_live"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    category_id: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    likes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    comments: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    channel_id: Mapped[str | None] = mapped_column(Text)
    channel_title: Mapped[str | None] = mapped_column(Text)
    seo_title_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    seo_tag_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    seo_desc_words: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    privacy_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'public'")
    )
    is_scheduled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    publish_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    fetched_at: Mapped[datetime] = _created_at()

    # YouTube Analytics API fields (separate from the Data API fields above) —
    # populated by a distinct sync (POST /sync-analytics) that requires the
    # yt-analytics.readonly scope. analytics_synced_at is NULL until that sync
    # has run at least once; the UI/AI-prompt code treats NULL as "no real CTR
    # data available yet" rather than trusting a zero as a true value.
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    impressions_ctr: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    average_view_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    average_view_percentage: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    # Real total watch time in hours from the Analytics API
    # (estimatedMinutesWatched / 60). NULL until sync-analytics has run.
    watch_time_hours: Mapped[float | None] = mapped_column(Double, nullable=True)
    # Net subscribers gained from this video (subscribersGained metric).
    # NULL until sync-analytics has run.
    subscribers_gained: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    analytics_synced_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "video_id", name="pk_youtube_videos_live"),
        Index("ix_yt_live_user_published", "user_id", text("published_at DESC")),
        Index("ix_yt_live_user_views", "user_id", text("views DESC")),
        Index("ix_yt_live_user_privacy", "user_id", "privacy_status"),
        Index("ix_yt_live_user_scheduled", "user_id", "is_scheduled"),
    )


class YoutubePublishedVideo(Base):
    """CSV-imported YouTube Studio metrics. PK is ``(user_id, video_id)``."""

    __tablename__ = "youtube_published_videos"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publish_time: Mapped[datetime | None] = mapped_column(TZDateTime)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    watch_time_hours: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    subscribers: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    impressions_ctr: Mapped[float | None] = mapped_column(Double)
    imported_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "video_id", name="pk_youtube_published_videos"),
    )


class YoutubeTrafficSource(Base):
    """CSV-imported traffic-source breakdown.

    The surrogate ``id`` stays the primary key — the Pydantic response model and
    the frontend list keys depend on it — and isolation comes from
    ``UNIQUE (user_id, traffic_source)``, which is also the upsert target.
    """

    __tablename__ = "youtube_traffic_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    traffic_source: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    watch_time_hours: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    avg_view_duration: Mapped[str | None] = mapped_column(Text)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    impressions_ctr: Mapped[float | None] = mapped_column(Double)
    imported_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint(
            "user_id", "traffic_source", name="uq_youtube_traffic_sources_user_source"
        ),
    )


class YoutubePlaylistItem(Base):
    """Locally-tracked video ideas attached to a real YouTube playlist."""

    __tablename__ = "youtube_playlist_items"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    playlist_id: Mapped[str] = mapped_column(Text, nullable=False)
    playlist_title: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    video_format: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'full'")
    )
    scheduled_date: Mapped[str | None] = mapped_column(IsoDate)
    publish_date: Mapped[str | None] = mapped_column(IsoDate)
    production_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_youtube_playlist_items_user_playlist", "user_id", "playlist_id"),
    )


class YoutubeAnalysis(Base):
    """Saved output of one AI analysis run (strategy / roadmap / channel)."""

    __tablename__ = "youtube_analyses"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below; a second single-column
    # index on user_id would only cost write throughput.
    user_id: Mapped[str] = _owner_fk(index=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    time_range: Mapped[str] = mapped_column(Text, nullable=False)
    weeks: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index(
            "ix_youtube_analyses_user_kind_created",
            "user_id",
            "kind",
            text("created_at DESC"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Competitor intelligence
# ─────────────────────────────────────────────────────────────────────────────


class YoutubeCompetitorDiscoveryRun(Base):
    """One round of competitor discovery, held for the user's approval.

    Candidates live in JSONB rather than as ``youtube_competitors`` rows so an
    unapproved suggestion never pollutes the list the analysis prompts read.
    Only the approve step promotes them into real rows.
    """

    __tablename__ = "youtube_competitor_discovery_runs"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below.
    user_id: Mapped[str] = _owner_fk(index=False)
    niche: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )  # pending | applied | discarded
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False)
    approved_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    rejected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # YouTube Data API units this run cost. search.list is 100 units against a
    # 10k/day project quota, so the spend is recorded rather than guessed at.
    quota_units_spent: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        Index(
            "ix_competitor_runs_user_created",
            "user_id",
            text("created_at DESC"),
        ),
    )


class YoutubeCompetitor(Base):
    """A competitor channel tracked for one user. PK is ``(user_id, channel_id)``.

    Rejected candidates are kept as rows with ``status='rejected'`` rather than
    discarded: discovery excludes every channel already present in *any* status,
    so a channel the user turned down is never suggested again.
    """

    __tablename__ = "youtube_competitors"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    uploads_playlist_id: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    subscriber_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    view_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    video_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    niche: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'approved'")
    )  # approved | rejected | archived
    # Lower runs first in the weekly sync; ties broken by staleness.
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    discovered_by: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'llm'")
    )  # llm | manual
    source_run_id: Mapped[str | None] = mapped_column(
        UUIDStr,
        ForeignKey("youtube_competitor_discovery_runs.id", ondelete="SET NULL"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "channel_id", name="pk_youtube_competitors"),
        # Drives the keyset-paginated list: (user_id, status) filter, newest
        # first, with channel_id as the tiebreaker the cursor carries.
        Index(
            "ix_youtube_competitors_user_status",
            "user_id",
            "status",
            text("created_at DESC"),
            "channel_id",
        ),
        # Drives the weekly picker: stalest approved channels first.
        Index(
            "ix_youtube_competitors_sync",
            "user_id",
            "status",
            "priority",
            text("last_synced_at ASC NULLS FIRST"),
        ),
    )


class YoutubeCompetitorVideo(Base):
    """Latest uploads of a tracked competitor. PK is ``(user_id, video_id)``.

    Scoped per user like every other YouTube table: the same public video may be
    tracked by two users, and a single-column ``video_id`` key would let one
    user's sync overwrite the other's row.
    """

    __tablename__ = "youtube_competitor_videos"

    user_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_short: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    likes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    comments: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    tags: Mapped[list | None] = mapped_column(JSONB)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "video_id", name="pk_youtube_competitor_videos"),
        ForeignKeyConstraint(
            ["user_id", "channel_id"],
            ["youtube_competitors.user_id", "youtube_competitors.channel_id"],
            ondelete="CASCADE",
            name="fk_competitor_videos_competitor",
        ),
        Index(
            "ix_competitor_videos_channel",
            "user_id",
            "channel_id",
            text("published_at DESC"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prospect audits — third-party channels analysed for outreach
# ─────────────────────────────────────────────────────────────────────────────


class YoutubeProspect(Base):
    """A third-party channel the user has audited for outreach.

    Deliberately separate from ``youtube_competitors`` rather than reusing it.
    A competitor is a channel the user has chosen to track, feeding the weekly
    sync and every analysis prompt; a prospect is someone they looked up once to
    pitch. Folding prospects into that table would silently poison the user's
    competitive set — and ``youtube_competitor_videos`` has a composite FK that
    would require a competitor row per lookup.
    """

    __tablename__ = "youtube_prospects"

    id: Mapped[str] = _pk_uuid()
    user_id: Mapped[str] = _owner_fk(index=False)
    channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    handle: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    subscriber_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Deterministic, Python-computed figures backing the outreach line. Stored
    # so the copy shown later always matches the numbers it was generated from,
    # even after the channel's real stats have moved on.
    metrics_json: Mapped[dict | None] = mapped_column(JSONB)
    headline_json: Mapped[dict | None] = mapped_column(JSONB)
    outreach_line: Mapped[str | None] = mapped_column(Text)
    outreach_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'new'")
    )  # new | contacted | replied | archived
    duration_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_report_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_youtube_prospects_user_channel"),
        Index("ix_youtube_prospects_user_created", "user_id", text("created_at DESC")),
    )


class YoutubeProspectReport(Base):
    """One generated audit or roadmap for a prospect.

    Kept as history rather than a column on the prospect so a re-run never
    destroys the version the user already pasted into an email.
    """

    __tablename__ = "youtube_prospect_reports"

    id: Mapped[str] = _pk_uuid()
    prospect_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("youtube_prospects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = _owner_fk(index=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # audit | roadmap
    weeks: Mapped[int | None] = mapped_column(Integer)
    # Display name, e.g. "Gemini 3.7 Flash". Kept for backwards compatibility
    # with rows written before tier tracking; resolved_model is the real answer.
    model: Mapped[str | None] = mapped_column(Text)

    # ── Provenance ───────────────────────────────────────────────────────────
    # Which rung of app.provider_tiers actually produced this report. Without
    # these an audit written by a local 7B fallback was indistinguishable — in
    # the database, the API and the exported PDF — from one written by Gemini.
    #
    # tier_grade is the gate: only 'client_grade' may be exported, printed or
    # shared. It defaults to 'internal_only' precisely so that a row whose
    # provenance was never recorded fails closed rather than open.
    tier_index: Mapped[int | None] = mapped_column(Integer)
    tier_name: Mapped[str | None] = mapped_column(Text)
    tier_grade: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'internal_only'")
    )
    # The exact model string that answered, e.g. "gemini/gemini-3.7-flash".
    # Internal-facing only: never rendered into a client export.
    resolved_model: Mapped[str | None] = mapped_column(Text)

    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index(
            "ix_youtube_prospect_reports_prospect_kind",
            "prospect_id",
            "kind",
            text("created_at DESC"),
        ),
        Index("ix_youtube_prospect_reports_user", "user_id", text("created_at DESC")),
    )

# ─────────────────────────────────────────────────────────────────────────────
# Personal intelligence — user-defined rules and tracked goals
# ─────────────────────────────────────────────────────────────────────────────


class UserRule(Base):
    """A directive the user wants every LLM call to obey.

    No CHECK on ``scope``/``category``: both lists will grow, and the Pydantic
    ``Literal`` in app.models.intelligence is the validation boundary — the same
    call made for ``plan_items.production_status``.
    """

    __tablename__ = "user_rules"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below.
    user_id: Mapped[str] = _owner_fk(index=False)
    scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'global'")
    )  # global | youtube | blog | linkedin | instagram
    category: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'behavior'")
    )  # behavior | content | style | constraint
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lower wins when the rendered block has to be truncated to fit the prompt.
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index(
            "ix_user_rules_user_active",
            "user_id",
            "is_active",
            "scope",
            "priority",
        ),
    )


class UserGoal(Base):
    """A measurable target the planner and the analyses steer toward.

    ``baseline_value``/``baseline_at`` are stamped at creation so progress is
    "since you set this goal", not "since the channel began" — the only reading
    that makes "2k subscribers this month" mean anything.
    """

    __tablename__ = "user_goals"

    id: Mapped[str] = _pk_uuid()
    # Covered by the composite index below.
    user_id: Mapped[str] = _owner_fk(index=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'youtube'")
    )
    metric: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'subscribers'")
    )  # subscribers | views | watch_hours | videos_published | custom
    target_value: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    baseline_value: Mapped[float] = mapped_column(
        Double, nullable=False, server_default=text("0")
    )
    baseline_at: Mapped[datetime] = _created_at()
    deadline: Mapped[datetime | None] = mapped_column(IsoDate())
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )  # active | achieved | missed | archived
    # {current_value, pct, on_track, computed_at} — recomputed lazily on read.
    progress: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index("ix_user_goals_user_status", "user_id", "status", "deadline"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Assistant (centralized chatbot)
# ─────────────────────────────────────────────────────────────────────────────


class AssistantConversation(Base):
    """One chat thread between a user and the assistant."""

    __tablename__ = "assistant_conversations"

    id: Mapped[str] = _pk_uuid()
    user_id: Mapped[str] = _owner_fk(index=False)  # covered by the composite below
    # Seeded from the first question; never model-authored prose that could
    # carry markup into the sidebar.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    # Bumped on every message so the sidebar sorts by real activity, not by
    # when the thread happened to be opened.
    updated_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        Index(
            "ix_assistant_conversations_user_updated",
            "user_id",
            text("updated_at DESC"),
        ),
    )


class AssistantMessage(Base):
    """One turn in a conversation.

    ``user_id`` is denormalized from the parent conversation rather than joined,
    for the same reason ``PlanItem.platform`` is: every read of this table is
    tenant-scoped, and requiring a join to prove ownership makes it easy to
    write the one query that forgets to.
    """

    __tablename__ = "assistant_messages"

    id: Mapped[str] = _pk_uuid()
    conversation_id: Mapped[str] = mapped_column(
        UUIDStr,
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = _owner_fk(index=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # Markdown for the assistant, verbatim input for the user.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Telemetry and replay state: intent, resolved range, model, tier,
    # latency_ms, language, last_items. Keys are FLAT and the column is NOT
    # NULL for the same reason as PlanItem.meta — updates shallow-merge with
    # `meta || patch`, and `NULL || '{...}'` is NULL.
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_assistant_messages_role"
        ),
        # `id` is a tiebreaker, not decoration: a question and its answer are
        # written in one transaction and can share now() to the microsecond,
        # which would make the transcript order non-deterministic.
        Index(
            "ix_assistant_messages_conv_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )


class AssistantAction(Base):
    """A write the assistant proposed and the user has not yet confirmed.

    The row **is** the confirmation capability: its id is what the confirm
    endpoint accepts, and it is single-use (``status`` gates re-execution) and
    expiring (``expires_at``). Nothing the assistant proposes can mutate planner
    data until a request arrives naming one of these ids.
    """

    __tablename__ = "assistant_actions"

    id: Mapped[str] = _pk_uuid()
    message_id: Mapped[str] = mapped_column(
        UUIDStr,
        ForeignKey("assistant_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = _owner_fk(index=False)
    # Always present: every plan_item_content row has a non-null item_id, so the
    # "which topic is this about?" join is uniform across all five verbs.
    # CASCADE so deleting an item vaporizes any pending capability against it
    # rather than leaving one pointing at a tombstone.
    item_id: Mapped[str] = mapped_column(
        UUIDStr, ForeignKey("plan_items.id", ondelete="CASCADE"), nullable=False
    )
    # Non-null exactly for the two review verbs; see the CHECK below.
    content_id: Mapped[str | None] = mapped_column(
        UUIDStr, ForeignKey("plan_item_content.id", ondelete="CASCADE")
    )
    verb: Mapped[str] = mapped_column(Text, nullable=False)
    # Server-authored from validated DB values — never the model's own words.
    # A button that authorizes a write must not be phrased by the LLM.
    label: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'proposed'")
    )
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    executed_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (
        # A real CHECK here, unlike production_status, because the set is closed
        # and the executor branches on it exhaustively.
        CheckConstraint(
            "verb IN ('mark_published', 'reschedule', 'generate_content', "
            "'approve_draft', 'reject_draft')",
            name="ck_assistant_actions_verb",
        ),
        CheckConstraint(
            "status IN ('proposed', 'executing', 'executed', 'cancelled', "
            "'failed', 'expired')",
            name="ck_assistant_actions_status",
        ),
        # Ties the target to the verb, so a malformed row is impossible even by
        # direct SQL: review verbs carry a content_id, the others never do.
        CheckConstraint(
            "(verb IN ('approve_draft', 'reject_draft')) = (content_id IS NOT NULL)",
            name="ck_assistant_actions_target_valid",
        ),
        Index(
            "ix_assistant_actions_user_status",
            "user_id",
            "status",
            text("created_at DESC"),
        ),
    )


class GeneratedImage(Base):
    """One prompt-to-image render from the Image Studio.

    The row exists so the file can be served back safely. Rendered images live in
    ``settings.image_output_dir``, which is deliberately *not* a static mount —
    see ``planner.get_item_image``: under docker-compose the dashboard cannot see
    that directory anyway, and mounting it would make every tenant's renders
    public. Ownership is proven by this row, then the file is streamed.
    """

    __tablename__ = "generated_images"

    id: Mapped[str] = _pk_uuid()
    user_id: Mapped[str] = _owner_fk(index=False)  # covered by the composite below

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Gemini has no negative-prompt field; the client folds exclusions into the
    # positive prompt. Stored separately so the UI can show what was asked for.
    negative_prompt: Mapped[str | None] = mapped_column(Text)

    model: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(Text, nullable=False)
    image_size: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int | None] = mapped_column(BigInteger)

    # Basename only, always resolved through _image_path's traversal guard.
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    duration_s: Mapped[float | None] = mapped_column(Double)

    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        # The gallery reads newest-first for one user, which is the only access
        # pattern; a bare user_id index would be redundant with this.
        Index("ix_generated_images_user_created", "user_id", text("created_at DESC")),
    )


# Tables that belong to a single tenant. Used by the isolation tests to assert
# that no query touches one of these without a user_id predicate.
TENANT_TABLES: frozenset[str] = frozenset(
    {
        "agent_runs",
        "api_keys",
        "assistant_actions",
        "assistant_conversations",
        "assistant_messages",
        "blog_posts",
        "content_plans",
        "generated_images",
        "google_oauth_tokens",
        "instagram_oauth_tokens",
        "instagram_snapshots",
        "jobs",
        "linkedin_posts",
        "niche_state",
        "plan_item_content",
        "plan_items",
        "published_topics",
        "refresh_tokens",
        "saved_topic_runs",
        "saved_topics",
        "task_steps",
        "usage_limits",
        "user_goals",
        "user_rules",
        "youtube_analyses",
        "youtube_competitor_discovery_runs",
        "youtube_competitor_videos",
        "youtube_competitors",
        "youtube_playlist_items",
        "youtube_prospect_reports",
        "youtube_prospects",
        "youtube_published_videos",
        "youtube_scripts",
        "youtube_traffic_sources",
        "youtube_videos_live",
    }
)

# Deliberately global. Adding to this set is a security decision.
GLOBAL_TABLES: frozenset[str] = frozenset({"users", "research_cache"})
