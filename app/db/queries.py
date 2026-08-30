"""
Async query layer — the API path.

Every function takes an :class:`~sqlalchemy.ext.asyncio.AsyncSession` as its
first argument and returns plain dicts (or lists of dicts), matching what the
old ``sqlite3.Row``-based layer returned so callers did not have to change
shape.

Two rules this module enforces that its predecessor did not:

**Ownership is a parameter, not an afterthought.** Every function touching a
tenant-owned table takes ``user_id`` and puts it in the WHERE clause. Thirteen
functions previously keyed on a resource id alone — ``get_run_by_id``,
``update_run_status``, ``update_plan_item_content`` and friends — so anyone who
learned or guessed an id could read or mutate another tenant's row. Reads that
are *deliberately* public say so in their name (``get_public_blog_by_slug``).

**No duplicated logic with the worker path.** The eight functions Celery also
needs are implemented once in :mod:`app.db.sync_queries` and exposed here via
``AsyncSession.run_sync()``, which runs them inside SQLAlchemy's greenlet
context — still fully non-blocking, but with one implementation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, cast, delete, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.planner import PUBLISHED_STATUSES, default_status, status_order

from app.db import sync_queries
from app.db._util import (
    UNSET,
    generate_uuid,
    row_to_dict,
    rows_to_dicts,
    slugify,  # noqa: F401  (re-exported; callers import it from here)
)
from app.provider_tiers import UNKNOWN_GRADE
from app.db.tables import (
    AgentRun,
    ApiKey,
    AssistantAction,
    AssistantConversation,
    AssistantMessage,
    BlogPost,
    ContentPlan,
    GeneratedImage,
    GoogleOAuthToken,
    InstagramAiReport,
    LinkedinPost,
    PlanItem,
    PlanItemContent,
    SavedTopic,
    SavedTopicRun,
    TaskStep,
    UsageLimit,
    User,
    UserGoal,
    UserRule,
    YoutubeAnalysis,
    YoutubeCompetitor,
    YoutubeCompetitorDiscoveryRun,
    YoutubeCompetitorVideo,
    YoutubePlaylistItem,
    YoutubeProspect,
    YoutubeProspectReport,
    YoutubeScript,
    YoutubeVideoLive,
)

_UNSET = UNSET  # backwards-compatible alias for callers that imported it


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _one(session: AsyncSession, stmt) -> dict | None:
    return row_to_dict((await session.execute(stmt)).one_or_none())


async def _all(session: AsyncSession, stmt) -> list[dict]:
    return rows_to_dicts(await session.execute(stmt))


async def _touched(session: AsyncSession, stmt) -> bool:
    return (await session.execute(stmt)).rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────


async def create_user(session: AsyncSession, email: str, password_hash: str) -> dict:
    row = (
        await session.execute(
            insert(User)
            .values(id=generate_uuid(), email=email, password_hash=password_hash)
            .returning(User)
        )
    ).one()
    return row_to_dict(row)


async def get_user_by_email(session: AsyncSession, email: str) -> dict | None:
    # Case-insensitive to match the uq_users_email_lower index; otherwise
    # someone who signed up as Bob@x.com could not log in as bob@x.com.
    return await _one(
        session, select(User).where(func.lower(User.email) == (email or "").lower())
    )


async def get_user_by_id(session: AsyncSession, user_id: str) -> dict | None:
    return await _one(session, select(User).where(User.id == user_id))


async def set_user_password(
    session: AsyncSession, user_id: str, password_hash: str
) -> bool:
    return await _touched(
        session,
        update(User)
        .where(User.id == user_id)
        .values(password_hash=password_hash, updated_at=_now()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agent runs
# ─────────────────────────────────────────────────────────────────────────────


async def create_run(
    session: AsyncSession, user_id: str, topic: str, provider: str
) -> dict:
    row = (
        await session.execute(
            insert(AgentRun)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                topic=topic,
                provider_used=provider,
                status="pending",
            )
            .returning(AgentRun)
        )
    ).one()
    return row_to_dict(row)


async def create_agent_run(
    session: AsyncSession, run_id: str, user_id: str, topic: str, provider: str
) -> None:
    await session.execute(
        insert(AgentRun).values(
            id=run_id,
            user_id=user_id,
            topic=topic,
            provider_used=provider,
            status="pending",
        )
    )


async def update_run_status(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    status: str,
    final_result: str | None = None,
    duration: float | None = None,
    topic: str | None = None,
    image_url: str | None = None,
) -> bool:
    return await session.run_sync(
        lambda s: sync_queries.update_run_status(
            s, run_id, user_id, status, final_result, duration, topic, image_url
        )
    )


async def update_agent_run(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    final_result: str,
    duration: float,
    status: str,
    image_url: str | None = None,
    topic: str | None = None,
) -> bool:
    values: dict[str, Any] = {
        "status": status,
        "final_result": final_result,
        "duration_seconds": duration,
    }
    if status in ("completed", "failed"):
        values["completed_at"] = _now()
    if image_url is not None:
        values["image_url"] = image_url
    if topic is not None:
        values["topic"] = topic

    return await _touched(
        session,
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .values(**values),
    )


async def update_run_image(
    session: AsyncSession, run_id: str, user_id: str, image_url: str
) -> bool:
    return await _touched(
        session,
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .values(image_url=image_url),
    )


async def get_run_by_id(
    session: AsyncSession, run_id: str, user_id: str
) -> dict | None:
    """Fetch one run, scoped to its owner.

    ``user_id`` is required: the previous signature took only ``run_id``, so a
    guessed id leaked another tenant's run and its full generated output.
    """
    return await _one(
        session,
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id),
    )


def _build_runs_where(
    user_id: str,
    status: str | None = None,
    search: str | None = None,
    provider: str | None = None,
    time_range: str | None = None,
):
    clauses = [AgentRun.user_id == user_id]
    if status and status.lower() != "all":
        if status.lower() in ("succeeded", "completed"):
            clauses.append(AgentRun.status.in_(["completed", "published"]))
        else:
            clauses.append(AgentRun.status == status.lower())
    if search and search.strip():
        term = f"%{search.strip()}%"
        clauses.append(
            or_(
                AgentRun.topic.ilike(term),
                AgentRun.id.ilike(term),
                AgentRun.provider_used.ilike(term),
            )
        )
    if provider and provider.lower() != "all":
        clauses.append(AgentRun.provider_used.ilike(f"%{provider.strip()}%"))
    if time_range and time_range.lower() != "all":
        now = _now()
        tr = time_range.lower()
        if tr == "today":
            start_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            clauses.append(AgentRun.created_at >= start_today)
        elif tr == "24h":
            clauses.append(AgentRun.created_at >= now - timedelta(days=1))
        elif tr == "7d":
            clauses.append(AgentRun.created_at >= now - timedelta(days=7))
        elif tr == "30d":
            clauses.append(AgentRun.created_at >= now - timedelta(days=30))
    return and_(*clauses)


async def get_runs_by_user(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    provider: str | None = None,
    time_range: str | None = None,
    sort_by: str = "created_at_desc",
) -> list[dict]:
    where_clause = _build_runs_where(user_id, status, search, provider, time_range)
    stmt = select(AgentRun).where(where_clause)
    if sort_by == "created_at_asc":
        stmt = stmt.order_by(AgentRun.created_at.asc())
    elif sort_by == "duration_desc":
        stmt = stmt.order_by(AgentRun.duration_seconds.desc().nulls_last())
    elif sort_by == "duration_asc":
        stmt = stmt.order_by(AgentRun.duration_seconds.asc().nulls_last())
    else:
        stmt = stmt.order_by(AgentRun.created_at.desc())

    return await _all(session, stmt.limit(limit).offset(offset))


async def count_runs_by_user(
    session: AsyncSession,
    user_id: str,
    status: str | None = None,
    search: str | None = None,
    provider: str | None = None,
    time_range: str | None = None,
) -> int:
    where_clause = _build_runs_where(user_id, status, search, provider, time_range)
    stmt = select(func.count()).select_from(AgentRun).where(where_clause)
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_runs_stats_by_user(
    session: AsyncSession,
    user_id: str,
) -> dict:
    base_where = AgentRun.user_id == user_id
    total_res = await session.execute(
        select(
            func.count().label("total"),
            func.count().filter(AgentRun.status.in_(["completed", "published"])).label("completed"),
            func.count().filter(AgentRun.status == "failed").label("failed"),
            func.count().filter(AgentRun.status == "running").label("running"),
            func.count().filter(AgentRun.status == "pending").label("pending"),
            func.avg(AgentRun.duration_seconds).filter(AgentRun.duration_seconds.is_not(None)).label("avg_duration"),
        ).where(base_where)
    )
    row = total_res.mappings().first() or {}
    total = row.get("total") or 0
    completed = row.get("completed") or 0
    failed = row.get("failed") or 0
    running = row.get("running") or 0
    pending = row.get("pending") or 0
    avg_duration = round(float(row.get("avg_duration") or 0), 1)
    success_rate = round((completed / total * 100), 1) if total > 0 else 0.0

    prov_res = await session.execute(
        select(AgentRun.provider_used).where(base_where, AgentRun.provider_used.is_not(None)).distinct()
    )
    providers = [p for (p,) in prov_res.all() if p]

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "avg_duration": avg_duration,
        "success_rate": success_rate,
        "providers": providers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Task steps
# ─────────────────────────────────────────────────────────────────────────────


async def insert_task_step(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    agent_name: str,
    task_name: str,
    output: str | None,
    status: str = "done",
) -> dict:
    return await session.run_sync(
        lambda s: sync_queries.insert_task_step(
            s, run_id, user_id, agent_name, task_name, output, status
        )
    )


# Historical alias.
save_task_step = insert_task_step


async def get_steps_by_run(
    session: AsyncSession, run_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(TaskStep)
        .where(TaskStep.run_id == run_id, TaskStep.user_id == user_id)
        .order_by(TaskStep.id.asc()),
    )


async def get_new_steps_since(
    session: AsyncSession, run_id: str, user_id: str, last_step_id: int
) -> list[dict]:
    return await _all(
        session,
        select(TaskStep)
        .where(
            TaskStep.run_id == run_id,
            TaskStep.user_id == user_id,
            TaskStep.id > last_step_id,
        )
        .order_by(TaskStep.id.asc()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Usage limits
# ─────────────────────────────────────────────────────────────────────────────


async def get_usage(session: AsyncSession, user_id: str) -> dict | None:
    return await session.run_sync(lambda s: sync_queries.get_usage(s, user_id))


async def init_usage(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        pg_insert(UsageLimit)
        .values(
            user_id=user_id,
            plan="enterprise",
            runs_this_month=0,
            max_runs_per_month=999999,
            reset_at=_now() + timedelta(days=30),
        )
        .on_conflict_do_nothing(index_elements=[UsageLimit.user_id])
    )


async def increment_usage(session: AsyncSession, user_id: str) -> None:
    await session.run_sync(lambda s: sync_queries.increment_usage(s, user_id))


async def reset_usage_if_expired(session: AsyncSession, user_id: str) -> None:
    await session.run_sync(lambda s: sync_queries.reset_usage_if_expired(s, user_id))


async def update_plan(
    session: AsyncSession, user_id: str, plan: str, max_runs: int
) -> None:
    await session.execute(
        update(UsageLimit)
        .where(UsageLimit.user_id == user_id)
        .values(plan=plan, max_runs_per_month=max_runs)
    )


# ─────────────────────────────────────────────────────────────────────────────
# API keys
# ─────────────────────────────────────────────────────────────────────────────


async def save_api_key(
    session: AsyncSession, user_id: str, provider: str, encrypted_key: str
) -> None:
    await session.execute(
        insert(ApiKey).values(
            user_id=user_id, provider=provider, api_key_encrypted=encrypted_key
        )
    )


async def get_api_key(
    session: AsyncSession, user_id: str, provider: str
) -> str | None:
    return (
        await session.execute(
            select(ApiKey.api_key_encrypted)
            .where(ApiKey.user_id == user_id, ApiKey.provider == provider)
            .order_by(ApiKey.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Blog posts
# ─────────────────────────────────────────────────────────────────────────────


async def save_blog_post(
    session: AsyncSession,
    run_id: str | None,
    user_id: str,
    topic: str,
    title: str | None,
    content: str,
    niche: str | None,
    approved: bool = False,
    word_count: int | None = None,
) -> dict:
    return await session.run_sync(
        lambda s: sync_queries.save_blog_post(
            s, run_id, user_id, topic, title, content, niche, approved, word_count
        )
    )


async def get_blog_posts(
    session: AsyncSession, user_id: str, limit: int = 20
) -> list[dict]:
    return await _all(
        session,
        select(BlogPost)
        .where(BlogPost.user_id == user_id, BlogPost.deleted_at.is_(None))
        .order_by(BlogPost.published_at.desc())
        .limit(limit),
    )


async def get_blog_by_id(
    session: AsyncSession, blog_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(BlogPost).where(
            BlogPost.id == blog_id,
            BlogPost.user_id == user_id,
            BlogPost.deleted_at.is_(None),
        ),
    )


async def get_public_blog_by_slug(session: AsyncSession, slug: str) -> dict | None:
    """Fetch a post by slug with **no ownership check**.

    Deliberately public — this backs the shareable blog reader. The name says so
    out loud so it is not mistaken for an accidentally-unscoped query and
    "fixed" into the tenant-scoped shape, or copied as a template for one.
    """
    return await _one(
        session,
        select(BlogPost).where(BlogPost.slug == slug, BlogPost.deleted_at.is_(None)),
    )


async def soft_delete_blog(
    session: AsyncSession, blog_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        update(BlogPost)
        .where(
            BlogPost.id == blog_id,
            BlogPost.user_id == user_id,
            BlogPost.deleted_at.is_(None),
        )
        .values(deleted_at=_now()),
    )


async def get_blog_posts_by_run_id(
    session: AsyncSession, run_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(BlogPost).where(
            BlogPost.run_id == run_id, BlogPost.user_id == user_id
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LinkedIn posts
# ─────────────────────────────────────────────────────────────────────────────


async def save_linkedin_post(
    session: AsyncSession,
    run_id: str | None,
    user_id: str,
    topic: str,
    post_text: str,
    hook: str | None,
    angle_type: str | None,
    word_count: int | None,
    approved: bool,
    niche: str | None,
) -> dict:
    return await session.run_sync(
        lambda s: sync_queries.save_linkedin_post(
            s, run_id, user_id, topic, post_text, hook, angle_type,
            word_count, approved, niche,
        )
    )


async def get_linkedin_posts(
    session: AsyncSession, user_id: str, limit: int = 20
) -> list[dict]:
    # post_text is deliberately omitted: the list view never renders it and it
    # is the largest column in the row.
    return await _all(
        session,
        select(
            LinkedinPost.id,
            LinkedinPost.run_id,
            LinkedinPost.user_id,
            LinkedinPost.topic,
            LinkedinPost.hook,
            LinkedinPost.angle_type,
            LinkedinPost.word_count,
            LinkedinPost.hashtag_count,
            LinkedinPost.approved,
            LinkedinPost.niche,
            LinkedinPost.created_at,
            LinkedinPost.deleted_at,
        )
        .where(LinkedinPost.user_id == user_id, LinkedinPost.deleted_at.is_(None))
        .order_by(LinkedinPost.created_at.desc())
        .limit(limit),
    )


async def get_linkedin_post_by_id(
    session: AsyncSession, post_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(LinkedinPost).where(
            LinkedinPost.id == post_id,
            LinkedinPost.user_id == user_id,
            LinkedinPost.deleted_at.is_(None),
        ),
    )


async def get_linkedin_posts_by_run_id(
    session: AsyncSession, run_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(LinkedinPost).where(
            LinkedinPost.run_id == run_id, LinkedinPost.user_id == user_id
        ),
    )


async def soft_delete_linkedin_post(
    session: AsyncSession, post_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        update(LinkedinPost)
        .where(
            LinkedinPost.id == post_id,
            LinkedinPost.user_id == user_id,
            LinkedinPost.deleted_at.is_(None),
        )
        .values(deleted_at=_now()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# YouTube scripts
# ─────────────────────────────────────────────────────────────────────────────


async def save_youtube_script(
    session: AsyncSession,
    run_id: str | None,
    user_id: str,
    topic: str,
    title: str | None,
    script: str,
    word_count: int | None,
    seo_title: str | None,
    seo_description: str | None,
    seo_tags: list | str | None,
    approved: bool,
    niche: str | None,
) -> dict:
    return await session.run_sync(
        lambda s: sync_queries.save_youtube_script(
            s, run_id, user_id, topic, title, script, word_count,
            seo_title, seo_description, seo_tags, approved, niche,
        )
    )


async def get_youtube_scripts(
    session: AsyncSession, user_id: str, limit: int = 20
) -> list[dict]:
    return await _all(
        session,
        select(
            YoutubeScript.id,
            YoutubeScript.run_id,
            YoutubeScript.user_id,
            YoutubeScript.topic,
            YoutubeScript.title,
            YoutubeScript.word_count,
            YoutubeScript.seo_title,
            YoutubeScript.approved,
            YoutubeScript.niche,
            YoutubeScript.created_at,
        )
        .where(YoutubeScript.user_id == user_id, YoutubeScript.deleted_at.is_(None))
        .order_by(YoutubeScript.created_at.desc())
        .limit(limit),
    )


async def get_youtube_script_by_id(
    session: AsyncSession, script_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(YoutubeScript).where(
            YoutubeScript.id == script_id,
            YoutubeScript.user_id == user_id,
            YoutubeScript.deleted_at.is_(None),
        ),
    )


async def get_youtube_scripts_by_run_id(
    session: AsyncSession, run_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(YoutubeScript).where(
            YoutubeScript.run_id == run_id, YoutubeScript.user_id == user_id
        ),
    )


async def soft_delete_youtube_script(
    session: AsyncSession, script_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        update(YoutubeScript)
        .where(
            YoutubeScript.id == script_id,
            YoutubeScript.user_id == user_id,
            YoutubeScript.deleted_at.is_(None),
        )
        .values(deleted_at=_now()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Content plans
# ─────────────────────────────────────────────────────────────────────────────


async def create_content_plan(
    session: AsyncSession,
    user_id: str,
    name: str,
    plan_type: str,
    niche: str,
    start_date: str,
    end_date: str,
    platform: str = "youtube",
) -> dict:
    row = (
        await session.execute(
            insert(ContentPlan)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                name=name,
                plan_type=plan_type,
                niche=niche,
                start_date=start_date,
                end_date=end_date,
                platform=platform,
            )
            .returning(ContentPlan)
        )
    ).one()
    return row_to_dict(row)


async def get_content_plans(
    session: AsyncSession, user_id: str, platform: str | None = None
) -> list[dict]:
    """Plans with their item counts. ``platform=None`` returns every platform."""
    item_count = (
        select(func.count())
        .select_from(PlanItem)
        .where(PlanItem.plan_id == ContentPlan.id)
        .scalar_subquery()
    )
    published_count = (
        select(func.count())
        .select_from(PlanItem)
        .where(
            PlanItem.plan_id == ContentPlan.id,
            # Both status vocabularies: 'video_published' is the YouTube
            # pipeline's terminal stage, 'published' every other platform's.
            PlanItem.production_status.in_(PUBLISHED_STATUSES),
        )
        .scalar_subquery()
    )
    stmt = select(
        ContentPlan,
        item_count.label("item_count"),
        published_count.label("published_count"),
    ).where(ContentPlan.user_id == user_id)
    if platform is not None:
        stmt = stmt.where(ContentPlan.platform == platform)
    return await _all(session, stmt.order_by(ContentPlan.start_date.desc()))


async def get_or_create_board_plan(
    session: AsyncSession, user_id: str, platform: str
) -> dict:
    """The user's open-ended Kanban plan for a platform, created on first use.

    Uses ON CONFLICT rather than try/except: in asyncio a failed statement
    aborts the whole transaction, so catching IntegrityError would poison every
    later write in the same request. The partial unique index
    ``uq_content_plans_user_platform_board`` is what makes this race-free.
    """
    today = date.today().isoformat()
    await session.execute(
        pg_insert(ContentPlan)
        .values(
            id=generate_uuid(),
            user_id=user_id,
            name=f"{platform.title()} Board",
            plan_type="board",
            niche=platform,
            start_date=today,
            end_date=today,
            platform=platform,
        )
        .on_conflict_do_nothing(
            index_elements=[ContentPlan.user_id, ContentPlan.platform],
            index_where=text("plan_type = 'board'"),
        )
    )
    return await _one(
        session,
        select(ContentPlan).where(
            ContentPlan.user_id == user_id,
            ContentPlan.platform == platform,
            ContentPlan.plan_type == "board",
        ),
    )


async def get_content_plan_by_id(
    session: AsyncSession, plan_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(ContentPlan).where(
            ContentPlan.id == plan_id, ContentPlan.user_id == user_id
        ),
    )


async def update_content_plan(
    session: AsyncSession,
    plan_id: str,
    user_id: str,
    name: str | None = None,
    status: str | None = None,
    end_date: str | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if status is not None:
        values["status"] = status
    # Extended when an import schedules items past the plan's current window.
    if end_date is not None:
        values["end_date"] = end_date
    if not values:
        return False

    return await _touched(
        session,
        update(ContentPlan)
        .where(ContentPlan.id == plan_id, ContentPlan.user_id == user_id)
        .values(**values),
    )


async def delete_content_plan(
    session: AsyncSession, plan_id: str, user_id: str
) -> bool:
    """Hard delete; plan_items and plan_item_content cascade."""
    return await _touched(
        session,
        delete(ContentPlan).where(
            ContentPlan.id == plan_id, ContentPlan.user_id == user_id
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plan items
# ─────────────────────────────────────────────────────────────────────────────


async def create_plan_item(
    session: AsyncSession,
    plan_id: str,
    user_id: str,
    topic: str,
    scheduled_date: str | None = None,
    notes: str | None = None,
    topic_source: str = "manual",
    publish_date: str | None = None,
    video_format: str = "full",
    event_time: str | None = None,
    event_duration_minutes: int | None = None,
    platform: str | None = None,
    meta: dict | None = None,
    production_status: str | None = None,
) -> dict:
    """Create one scheduled slot.

    ``platform`` is resolved from the parent plan when not given. This is the
    single place the plan/item platform invariant is enforced — nothing else
    writes ``plan_items``, and no endpoint moves an item between plans.
    """
    if platform is None:
        platform = (
            await session.execute(
                select(ContentPlan.platform).where(
                    ContentPlan.id == plan_id, ContentPlan.user_id == user_id
                )
            )
        ).scalar_one_or_none() or "youtube"
    row = (
        await session.execute(
            insert(PlanItem)
            .values(
                id=generate_uuid(),
                plan_id=plan_id,
                user_id=user_id,
                topic=topic,
                scheduled_date=scheduled_date,
                publish_date=publish_date,
                notes=notes,
                topic_source=topic_source,
                video_format=video_format,
                event_time=event_time,
                event_duration_minutes=event_duration_minutes,
                platform=platform,
                meta=meta or {},
                production_status=production_status or default_status(platform),
            )
            .returning(PlanItem)
        )
    ).one()
    return row_to_dict(row)


async def get_plan_items(
    session: AsyncSession, plan_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(PlanItem)
        .where(PlanItem.plan_id == plan_id, PlanItem.user_id == user_id)
        # NULLS LAST: Postgres sorts NULLs first on ASC, which would float every
        # undated backlog idea to the top of the list.
        .order_by(
            PlanItem.scheduled_date.asc().nulls_last(), PlanItem.created_at.asc()
        ),
    )


async def get_plan_items_by_platform(
    session: AsyncSession,
    user_id: str,
    platform: str,
    statuses: list[str] | None = None,
    plan_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    order: str = "created_desc",
) -> list[dict]:
    """Every item on a platform, across plans — the Kanban and calendar read.

    Deliberately not routed through ``plan_service.get_plan_detail``, which
    issues a content query per item; a 200-card board would be 200+ queries.
    Index-backed by ix_plan_items_user_platform_status / _scheduled.
    """
    stmt = select(PlanItem).where(
        PlanItem.user_id == user_id, PlanItem.platform == platform
    )
    if statuses:
        stmt = stmt.where(PlanItem.production_status.in_(statuses))
    if plan_id is not None:
        stmt = stmt.where(PlanItem.plan_id == plan_id)
    if date_from is not None:
        stmt = stmt.where(PlanItem.scheduled_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(PlanItem.scheduled_date <= date_to)

    if order == "scheduled":
        stmt = stmt.order_by(
            PlanItem.scheduled_date.asc().nulls_last(), PlanItem.created_at.asc()
        )
    else:
        # Reproduces the old list_board_items ordering exactly.
        stmt = stmt.order_by(PlanItem.created_at.desc())
    return await _all(session, stmt)


async def get_plan_items_across_platforms(
    session: AsyncSession,
    user_id: str,
    platforms: list[str] | None = None,
    statuses: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_undated: bool = False,
    order: str = "scheduled",
    limit: int = 60,
) -> list[dict]:
    """Items across every platform at once — the assistant's schedule read.

    ``get_plan_items_by_platform`` takes a single platform, which for a
    cross-channel question ("aaj kya post karna hai?") means one round trip per
    platform *and* an unenforceable row cap: capping per-platform then merging in
    Python can drop the only YouTube item of the day. This caps in SQL instead.

    ``platforms=None`` means every channel. ``include_undated`` widens the date
    predicate to also admit backlog cards, which have no ``scheduled_date`` —
    off by default, since an undated idea is not part of "today".

    Index-backed by ix_plan_items_user_platform_scheduled; with an explicit
    platform list Postgres drives it as an array scan, and with none the leading
    user_id column still carries it.
    """
    stmt = select(PlanItem).where(PlanItem.user_id == user_id)
    if platforms:
        stmt = stmt.where(PlanItem.platform.in_(platforms))
    if statuses:
        stmt = stmt.where(PlanItem.production_status.in_(statuses))

    date_clauses = []
    if date_from is not None:
        date_clauses.append(PlanItem.scheduled_date >= date_from)
    if date_to is not None:
        date_clauses.append(PlanItem.scheduled_date <= date_to)
    if date_clauses:
        ranged = and_(*date_clauses)
        stmt = stmt.where(
            or_(PlanItem.scheduled_date.is_(None), ranged) if include_undated else ranged
        )

    if order == "scheduled":
        stmt = stmt.order_by(
            PlanItem.scheduled_date.asc().nulls_last(),
            PlanItem.event_time.asc().nulls_last(),
            PlanItem.created_at.asc(),
        )
    else:
        stmt = stmt.order_by(PlanItem.created_at.desc())
    return await _all(session, stmt.limit(limit))


def _overdue_clause(
    user_id: str, today: str | date | None = None, platforms: list[str] | None = None
):
    """Past its scheduled date and not yet out the door.

    The single definition of "overdue" in this codebase. The analytics count, the
    assistant's list and its grouped summary all resolve to this, so the stat card
    and the chat answer cannot disagree — which they did: the assistant listed one
    day's items against a count spanning every past day.

    ``today`` omitted falls back to Postgres ``current_date``; see the note in
    ``get_planner_analytics`` for why that is a day off in a UTC container. An ISO
    string is parsed to a ``date`` because asyncpg binds a DATE parameter from a
    ``date`` and rejects a ``str`` outright.

    An undated backlog idea is never overdue, hence the explicit NOT NULL.
    """
    if today is None:
        day = func.current_date()
    elif isinstance(today, str):
        day = date.fromisoformat(today)
    else:
        day = today

    clauses = [
        PlanItem.user_id == user_id,
        PlanItem.production_status.not_in(PUBLISHED_STATUSES),
        PlanItem.scheduled_date.is_not(None),
        PlanItem.scheduled_date < day,
    ]
    if platforms:
        clauses.append(PlanItem.platform.in_(platforms))
    return and_(*clauses)


async def count_overdue_plan_items(
    session: AsyncSession,
    user_id: str,
    today: str | date | None = None,
    platforms: list[str] | None = None,
) -> int:
    """How many items are overdue — the number the assistant quotes.

    Cheap enough to call before deciding whether to list the rows or summarize
    them, which is the point: a count query is one index scan, not a fetch.
    """
    return (
        await session.execute(
            select(func.count())
            .select_from(PlanItem)
            .where(_overdue_clause(user_id, today, platforms))
        )
    ).scalar_one()


async def get_overdue_plan_items(
    session: AsyncSession,
    user_id: str,
    today: str | date | None = None,
    platforms: list[str] | None = None,
    limit: int = 60,
) -> list[dict]:
    """The overdue items themselves, most overdue first.

    ``get_plan_items_across_platforms`` cannot express this: its date filter is a
    closed range, and it applies no status predicate — so asking it for
    "everything before today" also returns rows that already went out.

    Index-backed by ix_plan_items_user_platform_scheduled.
    """
    stmt = (
        select(PlanItem)
        .where(_overdue_clause(user_id, today, platforms))
        .order_by(
            PlanItem.scheduled_date.asc(),
            PlanItem.event_time.asc().nulls_last(),
            PlanItem.created_at.asc(),
        )
        .limit(limit)
    )
    return await _all(session, stmt)


async def summarize_overdue_plan_items(
    session: AsyncSession,
    user_id: str,
    today: str | date | None = None,
    platforms: list[str] | None = None,
) -> list[dict]:
    """Overdue counts grouped by platform and calendar month, oldest month first.

    What the assistant answers with when there are too many items to list. One
    GROUP BY, so the breakdown costs the same for 40 overdue items as for 4,000.
    """
    month = func.to_char(PlanItem.scheduled_date, "YYYY-MM").label("month")
    return await _all(
        session,
        select(
            PlanItem.platform,
            month,
            func.count().label("count"),
            func.min(PlanItem.scheduled_date).label("oldest"),
        )
        .where(_overdue_clause(user_id, today, platforms))
        .group_by(PlanItem.platform, month)
        .order_by(month, PlanItem.platform),
    )


async def get_pending_review_contents(
    session: AsyncSession,
    user_id: str,
    review_statuses: tuple[str, ...] = ("ready", "generating"),
    platforms: list[str] | None = None,
    limit: int = 25,
) -> list[dict]:
    """The user-wide review queue: every draft awaiting a decision.

    ``get_plan_item_contents`` answers "what belongs to this item"; nothing
    answered "what is waiting on me". ``plan_item_content`` carries no platform
    of its own (see the note in get_planner_analytics), so the parent item is
    joined for topic and platform.

    The ``user_id`` predicate is applied to *both* sides of the join. Scoping
    only the content row would still be correct today, but the redundancy is the
    point: this is the first query in the codebase to read this table
    user-wide, and it must stay obviously tenant-safe as it is edited.

    Index-backed by ix_plan_item_content_user_review (added in 0008).
    """
    stmt = (
        select(
            PlanItemContent,
            PlanItem.topic.label("topic"),
            PlanItem.platform.label("platform"),
            PlanItem.plan_id.label("plan_id"),
        )
        .join(PlanItem, PlanItemContent.item_id == PlanItem.id)
        .where(
            PlanItemContent.user_id == user_id,
            PlanItem.user_id == user_id,
            PlanItemContent.review_status.in_(review_statuses),
        )
        .order_by(PlanItemContent.created_at.desc(), PlanItemContent.id.desc())
        .limit(limit)
    )
    # _all flattens the mixed entity+label row: the PlanItemContent columns are
    # expanded and the three joined labels merged alongside them.
    return await _all(session, stmt)


async def count_plan_items_by_status(
    session: AsyncSession, user_id: str, platform: str
) -> dict[str, int]:
    """Kanban column counts without shipping every row."""
    return await _group_count(
        session,
        PlanItem.production_status,
        PlanItem.user_id == user_id,
        PlanItem.platform == platform,
    )


async def get_plan_item_by_id(
    session: AsyncSession, item_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(PlanItem).where(PlanItem.id == item_id, PlanItem.user_id == user_id),
    )


async def update_plan_item(
    session: AsyncSession,
    item_id: str,
    user_id: str,
    topic: str | None = None,
    scheduled_date: str | None = None,
    notes: str | None = None,
    production_status: str | None = None,
    publish_date: Any = UNSET,
    video_format: str | None = None,
    event_time: Any = UNSET,
    event_duration_minutes: int | None = None,
    meta_patch: dict | None = None,
    scheduled_date_unset: Any = UNSET,
) -> bool:
    values: dict[str, Any] = {}
    if meta_patch:
        # Shallow merge, so a caller touching one key leaves the rest alone.
        # This is why meta is NOT NULL with a '{}' default and why its keys are
        # flat: `NULL || x` is NULL, and `||` replaces nested objects wholesale.
        values["meta"] = PlanItem.meta.op("||")(cast(meta_patch, JSONB))
    if scheduled_date_unset is not UNSET:
        values["scheduled_date"] = scheduled_date_unset  # None clears it
    if topic is not None:
        values["topic"] = topic
    if scheduled_date is not None:
        values["scheduled_date"] = scheduled_date
    if publish_date is not UNSET:
        values["publish_date"] = publish_date  # None clears it
    if event_time is not UNSET:
        values["event_time"] = event_time  # None clears it
    if event_duration_minutes is not None:
        values["event_duration_minutes"] = event_duration_minutes
    if video_format is not None:
        values["video_format"] = video_format
    if notes is not None:
        values["notes"] = notes
    if production_status is not None:
        values["production_status"] = production_status
    if not values:
        return False
    values["updated_at"] = _now()

    return await _touched(
        session,
        update(PlanItem)
        .where(PlanItem.id == item_id, PlanItem.user_id == user_id)
        .values(**values),
    )


async def set_plan_item_calendar_event(
    session: AsyncSession,
    item_id: str,
    user_id: str,
    event_id: str,
    event_link: str,
    event_time: str | None = None,
    event_duration_minutes: int | None = None,
) -> bool:
    values: dict[str, Any] = {
        "gcal_event_id": event_id,
        "gcal_event_link": event_link,
        "updated_at": _now(),
    }
    if event_time is not None:
        values["event_time"] = event_time
    if event_duration_minutes is not None:
        values["event_duration_minutes"] = event_duration_minutes

    return await _touched(
        session,
        update(PlanItem)
        .where(PlanItem.id == item_id, PlanItem.user_id == user_id)
        .values(**values),
    )


async def clear_plan_item_calendar_event(
    session: AsyncSession, item_id: str, user_id: str
) -> bool:
    """Forget the linked calendar event (e.g. it was deleted in Google Calendar)
    so the UI offers 'Add to Calendar' again."""
    return await _touched(
        session,
        update(PlanItem)
        .where(PlanItem.id == item_id, PlanItem.user_id == user_id)
        .values(gcal_event_id=None, gcal_event_link=None, updated_at=_now()),
    )


async def delete_plan_item(
    session: AsyncSession, item_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(PlanItem).where(PlanItem.id == item_id, PlanItem.user_id == user_id),
    )


async def get_recent_plan_topics(
    session: AsyncSession, user_id: str, days: int = 90, platform: str | None = None
) -> list[str]:
    """Topics already placed in any plan recently — dedup context for the suggester.

    Pass ``platform`` to keep the vocabularies apart: unfiltered, YouTube topic
    suggestion would start deduping against Instagram carousel titles.
    """
    cutoff = _now() - timedelta(days=days)
    stmt = select(PlanItem.topic).where(
        PlanItem.user_id == user_id, PlanItem.created_at > cutoff
    )
    if platform is not None:
        stmt = stmt.where(PlanItem.platform == platform)
    result = await session.execute(stmt)
    return [r[0] for r in result]


async def get_recent_youtube_titles(
    session: AsyncSession, user_id: str, limit: int = 12
) -> list[dict]:
    """This channel's actual synced videos (title/description/tags), best-performing first.

    Grounding context for the topic suggester — real content, not a guess from
    the free-text niche field.
    """
    result = await session.execute(
        select(
            YoutubeVideoLive.title,
            YoutubeVideoLive.description,
            YoutubeVideoLive.tags,
        )
        .where(YoutubeVideoLive.user_id == user_id)
        .order_by(YoutubeVideoLive.views.desc())
        .limit(limit)
    )
    return [
        {"title": title, "description": description, "tags": tags}
        for title, description, tags in result
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Instagram board items
# ─────────────────────────────────────────────────────────────────────────────
#
# Gone. Migration 0006 made the board plan_items rows with platform='instagram',
# and 0007 dropped the orphaned table once the dashboard cut over. Use the
# generic plan-item helpers above with platform="instagram"; there is no longer
# a separate Instagram board API, model or translation shim.


# ─────────────────────────────────────────────────────────────────────────────
# Instagram AI reports (strategy brief / content roadmap)
# ─────────────────────────────────────────────────────────────────────────────


async def save_instagram_ai_report(
    session: AsyncSession, user_id: str, report_type: str, payload: dict
) -> dict:
    row = (
        await session.execute(
            insert(InstagramAiReport)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                report_type=report_type,
                payload=payload,
            )
            .returning(InstagramAiReport)
        )
    ).one()
    return row_to_dict(row)


async def get_latest_instagram_ai_report(
    session: AsyncSession, user_id: str, report_type: str
) -> dict | None:
    return await _one(
        session,
        select(InstagramAiReport)
        .where(
            InstagramAiReport.user_id == user_id,
            InstagramAiReport.report_type == report_type,
        )
        .order_by(InstagramAiReport.created_at.desc())
        .limit(1),
    )


async def list_instagram_ai_reports(
    session: AsyncSession, user_id: str, report_type: str | None = None, limit: int = 20
) -> list[dict]:
    """History list: metadata only, no payload (keeps the dropdown response small).

    Mirrors :func:`get_youtube_analyses` so both platforms' history pickers can
    be driven by the same component.
    """
    stmt = select(
        InstagramAiReport.id,
        InstagramAiReport.report_type,
        InstagramAiReport.created_at,
    ).where(InstagramAiReport.user_id == user_id)
    if report_type is not None:
        stmt = stmt.where(InstagramAiReport.report_type == report_type)
    return await _all(
        session, stmt.order_by(InstagramAiReport.created_at.desc()).limit(limit)
    )


async def get_instagram_ai_report_by_id(
    session: AsyncSession, report_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(InstagramAiReport).where(
            InstagramAiReport.id == report_id,
            InstagramAiReport.user_id == user_id,
        ),
    )


async def delete_instagram_ai_report(
    session: AsyncSession, report_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(InstagramAiReport).where(
            InstagramAiReport.id == report_id,
            InstagramAiReport.user_id == user_id,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plan item content
# ─────────────────────────────────────────────────────────────────────────────


async def create_plan_item_content(
    session: AsyncSession, item_id: str, user_id: str, content_type: str, run_id: str
) -> dict:
    row = (
        await session.execute(
            insert(PlanItemContent)
            .values(
                id=generate_uuid(),
                item_id=item_id,
                user_id=user_id,
                content_type=content_type,
                run_id=run_id,
            )
            .returning(PlanItemContent)
        )
    ).one()
    return row_to_dict(row)


async def get_plan_item_contents(
    session: AsyncSession, item_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(PlanItemContent)
        .where(
            PlanItemContent.item_id == item_id, PlanItemContent.user_id == user_id
        )
        .order_by(PlanItemContent.created_at.desc(), PlanItemContent.id.desc()),
    )


async def get_plan_item_content_by_id(
    session: AsyncSession, content_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(PlanItemContent).where(
            PlanItemContent.id == content_id, PlanItemContent.user_id == user_id
        ),
    )


async def update_plan_item_content(
    session: AsyncSession,
    content_id: str,
    user_id: str,
    content_ref_id: str | None = None,
    review_status: str | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if content_ref_id is not None:
        values["content_ref_id"] = content_ref_id
    if review_status is not None:
        values["review_status"] = review_status
        if review_status in ("approved", "rejected"):
            values["reviewed_at"] = _now()
    if not values:
        return False

    return await _touched(
        session,
        update(PlanItemContent)
        .where(PlanItemContent.id == content_id, PlanItemContent.user_id == user_id)
        .values(**values),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Saved topics
# ─────────────────────────────────────────────────────────────────────────────


async def create_saved_topic(
    session: AsyncSession,
    user_id: str,
    topic: str,
    rationale: str | None = None,
    niche: str = "ai",
    source: str = "auto_research",
    source_run_id: str | None = None,
) -> dict | None:
    """Save one candidate topic as 'uncovered'.

    Returns None when the user already has a topic with the same normalized
    form, so re-running auto-research quietly skips ideas already in the backlog.
    """
    # Imported here: this module does not otherwise depend on content_tracker.
    from app.db.content_tracker import normalize_topic

    row = (
        await session.execute(
            pg_insert(SavedTopic)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                topic=topic,
                topic_normalized=normalize_topic(topic),
                rationale=rationale,
                niche=niche,
                source=source,
                source_run_id=source_run_id,
            )
            .on_conflict_do_nothing(
                index_elements=[SavedTopic.user_id, SavedTopic.topic_normalized]
            )
            .returning(SavedTopic)
        )
    ).one_or_none()
    return row_to_dict(row)


async def get_saved_topics(
    session: AsyncSession,
    user_id: str,
    status: str | None = None,
    include_dismissed: bool = False,
) -> list[dict]:
    stmt = select(SavedTopic).where(SavedTopic.user_id == user_id)
    if status:
        stmt = stmt.where(SavedTopic.status == status)
    if not include_dismissed:
        stmt = stmt.where(SavedTopic.dismissed_at.is_(None))
    return await _all(
        session, stmt.order_by(SavedTopic.created_at.desc(), SavedTopic.id.desc())
    )


async def get_saved_topic_by_id(
    session: AsyncSession, topic_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(SavedTopic).where(
            SavedTopic.id == topic_id, SavedTopic.user_id == user_id
        ),
    )


async def count_uncovered_topics(session: AsyncSession, user_id: str) -> int:
    """Backlog size — the only query the banner needs."""
    return (
        await session.execute(
            select(func.count())
            .select_from(SavedTopic)
            .where(
                SavedTopic.user_id == user_id,
                SavedTopic.status == "uncovered",
                SavedTopic.dismissed_at.is_(None),
            )
        )
    ).scalar_one()


async def get_latest_saved_topic_at(
    session: AsyncSession, user_id: str
) -> str | None:
    """Newest backlog entry, as an ISO string (the model field is Optional[str])."""
    latest = (
        await session.execute(
            select(func.max(SavedTopic.created_at)).where(
                SavedTopic.user_id == user_id,
                SavedTopic.status == "uncovered",
                SavedTopic.dismissed_at.is_(None),
            )
        )
    ).scalar()
    return latest.isoformat() if latest is not None else None


async def update_saved_topic(
    session: AsyncSession,
    topic_id: str,
    user_id: str,
    status: str | None = None,
    dismissed_at: Any = UNSET,
    topic: str | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
        if status == "generated":
            # First success wins; regenerating must not move the timestamp.
            values["generated_at"] = func.coalesce(SavedTopic.generated_at, _now())
    if dismissed_at is not UNSET:
        values["dismissed_at"] = dismissed_at
    if topic is not None:
        from app.db.content_tracker import normalize_topic

        values["topic"] = topic
        values["topic_normalized"] = normalize_topic(topic)
    if not values:
        return False
    values["updated_at"] = _now()

    return await _touched(
        session,
        update(SavedTopic)
        .where(SavedTopic.id == topic_id, SavedTopic.user_id == user_id)
        .values(**values),
    )


async def delete_saved_topic(
    session: AsyncSession, topic_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(SavedTopic).where(
            SavedTopic.id == topic_id, SavedTopic.user_id == user_id
        ),
    )


async def get_uncovered_topic_titles(
    session: AsyncSession, user_id: str
) -> list[str]:
    """Titles still awaiting generation — extra DO-NOT-REPEAT context for the
    suggester, so it stops re-proposing what is already in the backlog."""
    result = await session.execute(
        select(SavedTopic.topic)
        .where(SavedTopic.user_id == user_id, SavedTopic.status != "generated")
        .order_by(SavedTopic.created_at.desc())
        .limit(40)
    )
    return [r[0] for r in result]


# ─────────────────────────────────────────────────────────────────────────────
# Saved topic runs
# ─────────────────────────────────────────────────────────────────────────────


async def create_saved_topic_run(
    session: AsyncSession,
    saved_topic_id: str,
    user_id: str,
    content_type: str,
    run_id: str,
) -> dict:
    row = (
        await session.execute(
            insert(SavedTopicRun)
            .values(
                id=generate_uuid(),
                saved_topic_id=saved_topic_id,
                user_id=user_id,
                content_type=content_type,
                run_id=run_id,
            )
            .returning(SavedTopicRun)
        )
    ).one()
    return row_to_dict(row)


async def get_saved_topic_runs(
    session: AsyncSession, saved_topic_id: str, user_id: str
) -> list[dict]:
    return await _all(
        session,
        select(SavedTopicRun)
        .where(
            SavedTopicRun.saved_topic_id == saved_topic_id,
            SavedTopicRun.user_id == user_id,
        )
        .order_by(SavedTopicRun.created_at.desc(), SavedTopicRun.id.desc()),
    )


async def get_saved_topic_run_by_id(
    session: AsyncSession, row_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(SavedTopicRun).where(
            SavedTopicRun.id == row_id, SavedTopicRun.user_id == user_id
        ),
    )


async def update_saved_topic_run(
    session: AsyncSession,
    row_id: str,
    user_id: str,
    content_ref_id: str | None = None,
    review_status: str | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if content_ref_id is not None:
        values["content_ref_id"] = content_ref_id
    if review_status is not None:
        values["review_status"] = review_status
    if not values:
        return False

    return await _touched(
        session,
        update(SavedTopicRun)
        .where(SavedTopicRun.id == row_id, SavedTopicRun.user_id == user_id)
        .values(**values),
    )


# ─────────────────────────────────────────────────────────────────────────────
# YouTube playlist items
# ─────────────────────────────────────────────────────────────────────────────


async def create_youtube_playlist_item(
    session: AsyncSession,
    user_id: str,
    playlist_id: str,
    title: str,
    playlist_title: str | None = None,
    description: str | None = None,
    video_format: str = "full",
    scheduled_date: str | None = None,
    publish_date: str | None = None,
    source: str = "manual",
) -> dict:
    row = (
        await session.execute(
            insert(YoutubePlaylistItem)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                playlist_id=playlist_id,
                playlist_title=playlist_title,
                title=title,
                description=description,
                video_format=video_format,
                scheduled_date=scheduled_date,
                publish_date=publish_date,
                source=source,
            )
            .returning(YoutubePlaylistItem)
        )
    ).one()
    return row_to_dict(row)


async def get_youtube_playlist_items(
    session: AsyncSession, user_id: str, playlist_id: str | None = None
) -> list[dict]:
    stmt = select(YoutubePlaylistItem).where(YoutubePlaylistItem.user_id == user_id)
    if playlist_id is not None:
        stmt = stmt.where(YoutubePlaylistItem.playlist_id == playlist_id)
    return await _all(
        session,
        stmt.order_by(
            YoutubePlaylistItem.production_status.asc(),
            YoutubePlaylistItem.scheduled_date.asc(),
            YoutubePlaylistItem.created_at.asc(),
        ),
    )


async def get_youtube_playlist_item_by_id(
    session: AsyncSession, item_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(YoutubePlaylistItem).where(
            YoutubePlaylistItem.id == item_id, YoutubePlaylistItem.user_id == user_id
        ),
    )


async def update_youtube_playlist_item(
    session: AsyncSession,
    item_id: str,
    user_id: str,
    title: str | None = None,
    description: Any = UNSET,
    video_format: str | None = None,
    scheduled_date: Any = UNSET,
    publish_date: Any = UNSET,
    production_status: str | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if title is not None:
        values["title"] = title
    if description is not UNSET:
        values["description"] = description  # None clears it
    if video_format is not None:
        values["video_format"] = video_format
    if scheduled_date is not UNSET:
        values["scheduled_date"] = scheduled_date  # None clears it
    if publish_date is not UNSET:
        values["publish_date"] = publish_date  # None clears it
    if production_status is not None:
        values["production_status"] = production_status
    if not values:
        return False
    values["updated_at"] = _now()

    return await _touched(
        session,
        update(YoutubePlaylistItem)
        .where(
            YoutubePlaylistItem.id == item_id, YoutubePlaylistItem.user_id == user_id
        )
        .values(**values),
    )


async def delete_youtube_playlist_item(
    session: AsyncSession, item_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(YoutubePlaylistItem).where(
            YoutubePlaylistItem.id == item_id, YoutubePlaylistItem.user_id == user_id
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# YouTube analyses (saved strategy / roadmap runs)
# ─────────────────────────────────────────────────────────────────────────────


def _analysis_row(row) -> dict | None:
    """Row → dict, renaming the JSONB column to ``payload``.

    No json.loads: ``payload_json`` is JSONB, so the driver already hands back a
    Python object.
    """
    record = row_to_dict(row)
    if record is None:
        return None
    record["payload"] = record.pop("payload_json", None)
    return record


async def create_youtube_analysis(
    session: AsyncSession,
    user_id: str,
    kind: str,
    time_range: str,
    payload: dict,
    weeks: int | None = None,
    model: str | None = None,
) -> dict:
    row = (
        await session.execute(
            insert(YoutubeAnalysis)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                kind=kind,
                time_range=time_range,
                weeks=weeks,
                model=model,
                payload_json=payload,
            )
            .returning(YoutubeAnalysis)
        )
    ).one()
    return _analysis_row(row)


async def get_youtube_analyses(
    session: AsyncSession, user_id: str, kind: str | None = None, limit: int = 20
) -> list[dict]:
    """History list: metadata only, no payload (keeps the dropdown response small)."""
    stmt = select(
        YoutubeAnalysis.id,
        YoutubeAnalysis.kind,
        YoutubeAnalysis.time_range,
        YoutubeAnalysis.weeks,
        YoutubeAnalysis.model,
        YoutubeAnalysis.created_at,
    ).where(YoutubeAnalysis.user_id == user_id)
    if kind is not None:
        stmt = stmt.where(YoutubeAnalysis.kind == kind)
    return await _all(
        session, stmt.order_by(YoutubeAnalysis.created_at.desc()).limit(limit)
    )


async def get_latest_youtube_analysis(
    session: AsyncSession, user_id: str, kind: str, time_range: str | None = None
) -> dict | None:
    stmt = select(YoutubeAnalysis).where(
        YoutubeAnalysis.user_id == user_id, YoutubeAnalysis.kind == kind
    )
    if time_range is not None:
        stmt = stmt.where(YoutubeAnalysis.time_range == time_range)
    row = (
        await session.execute(stmt.order_by(YoutubeAnalysis.created_at.desc()).limit(1))
    ).one_or_none()
    return _analysis_row(row)


async def get_youtube_analysis_by_id(
    session: AsyncSession, analysis_id: str, user_id: str
) -> dict | None:
    row = (
        await session.execute(
            select(YoutubeAnalysis).where(
                YoutubeAnalysis.id == analysis_id, YoutubeAnalysis.user_id == user_id
            )
        )
    ).one_or_none()
    return _analysis_row(row)


async def delete_youtube_analysis(
    session: AsyncSession, analysis_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(YoutubeAnalysis).where(
            YoutubeAnalysis.id == analysis_id, YoutubeAnalysis.user_id == user_id
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth tokens
# ─────────────────────────────────────────────────────────────────────────────


async def save_google_tokens(
    session: AsyncSession,
    user_id: str,
    token_json_encrypted: str,
    scopes: str | None = None,
    connected_email: str | None = None,
) -> None:
    await session.run_sync(
        lambda s: sync_queries.save_google_tokens(
            s, user_id, token_json_encrypted, scopes, connected_email
        )
    )


async def get_google_tokens(session: AsyncSession, user_id: str) -> dict | None:
    return await session.run_sync(lambda s: sync_queries.get_google_tokens(s, user_id))


async def delete_google_tokens(session: AsyncSession, user_id: str) -> bool:
    return await session.run_sync(
        lambda s: sync_queries.delete_google_tokens(s, user_id)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Planner analytics
# ─────────────────────────────────────────────────────────────────────────────

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


def _count_map(rows: list[dict], key: str) -> dict[str, int]:
    """Turn [{key: 'x', 'n': 3}, ...] rows into {'x': 3}."""
    return {row[key]: row["n"] for row in rows}


async def _group_count(session: AsyncSession, column, *where) -> dict[str, int]:
    rows = await _all(
        session,
        select(column, func.count().label("n")).where(*where).group_by(column),
    )
    return _count_map(rows, column.key)


async def get_planner_analytics(
    session: AsyncSession,
    user_id: str,
    platform: str | None = None,
    today: str | None = None,
) -> dict:
    """Aggregate planner metrics for the analytics dashboard, scoped to a user.

    Status breakdowns, content mix, generation reliability, schedule adherence,
    per-platform word metrics and top-line KPIs in a single dict. All
    sub-queries are index-backed GROUP BYs over the planner tables.

    ``platform`` scopes every figure to one channel. Without it the numbers are
    cross-platform totals, which is correct for an "all platforms" view but
    means the funnel rows will not sum to ``total_items`` — the funnel lists one
    vocabulary's stages, and items may be in the other's.

    ``today`` ('YYYY-MM-DD') anchors the overdue/upcoming split. Omitted, it
    falls back to Postgres ``current_date`` — the *database session's* timezone,
    which in a UTC container is a full day off between 00:00 and 05:30 IST, so
    an item scheduled for today reads as overdue. Every pre-existing caller
    omits it and is unaffected; callers that care (the assistant) pass
    ``app.core.clock.user_today_iso()``.
    """
    owned_plan = and_(ContentPlan.user_id == user_id)
    owned_item = and_(PlanItem.user_id == user_id)
    owned_content = and_(PlanItemContent.user_id == user_id)
    if platform is not None:
        owned_plan = and_(owned_plan, ContentPlan.platform == platform)
        owned_item = and_(owned_item, PlanItem.platform == platform)
        # plan_item_content has no platform column (only generating platforms
        # produce rows there), so scope it through its parent item instead.
        owned_content = and_(
            owned_content,
            PlanItemContent.item_id.in_(select(PlanItem.id).where(owned_item)),
        )

    # -- Plans --
    total_plans = (
        await session.execute(
            select(func.count()).select_from(ContentPlan).where(owned_plan)
        )
    ).scalar_one()
    plans_by_status = await _group_count(session, ContentPlan.status, owned_plan)
    plans_by_type = await _group_count(session, ContentPlan.plan_type, owned_plan)
    plans_by_niche = await _group_count(session, ContentPlan.niche, owned_plan)

    # -- Items funnel --
    status_counts = await _group_count(
        session, PlanItem.production_status, owned_item
    )
    funnel_stages = (
        status_order(platform) if platform is not None else PRODUCTION_STATUS_ORDER
    )
    items_funnel = [
        {"status": s, "count": status_counts.get(s, 0)} for s in funnel_stages
    ]
    total_items = sum(status_counts.values())
    # Both vocabularies' terminal stages, so an Instagram 'published' card is
    # not invisible here.
    published_items = sum(status_counts.get(s, 0) for s in PUBLISHED_STATUSES)
    items_by_format = await _group_count(session, PlanItem.video_format, owned_item)
    items_by_source = await _group_count(session, PlanItem.topic_source, owned_item)

    # -- Content mix (type x review status) --
    mix_rows = await _all(
        session,
        select(
            PlanItemContent.content_type,
            PlanItemContent.review_status,
            func.count().label("n"),
        )
        .where(owned_content)
        .group_by(PlanItemContent.content_type, PlanItemContent.review_status),
    )
    content_by_type = {t: 0 for t in CONTENT_TYPES}
    content_by_review = {s: 0 for s in REVIEW_STATUSES}
    for r in mix_rows:
        content_by_type[r["content_type"]] = (
            content_by_type.get(r["content_type"], 0) + r["n"]
        )
        content_by_review[r["review_status"]] = (
            content_by_review.get(r["review_status"], 0) + r["n"]
        )
    total_content = sum(content_by_type.values())

    # -- Volume over time (content pieces generated per day) --
    day = func.date(PlanItemContent.created_at).label("day")
    volume_over_time = await _all(
        session,
        select(day, func.count().label("n"))
        .where(owned_content)
        .group_by(day)
        .order_by(day),
    )

    # -- Schedule adherence --
    # A real date object, not cast(str): asyncpg binds a DATE parameter from a
    # date and rejects a string outright ("'str' object has no attribute
    # 'toordinal'"), so the ISO string callers pass is parsed here.
    if today is None:
        today_expr = func.current_date()
    else:
        today_expr = date.fromisoformat(today) if isinstance(today, str) else today
    unpublished = PlanItem.production_status.not_in(PUBLISHED_STATUSES)
    # An undated backlog idea is neither overdue nor upcoming.
    dated = PlanItem.scheduled_date.is_not(None)
    # Deliberately not inlined: this figure is the stat card, and the assistant
    # lists the rows behind it. Both go through _overdue_clause so they cannot
    # drift apart.
    overdue = await count_overdue_plan_items(
        session, user_id, today=today, platforms=[platform] if platform else None
    )
    upcoming = (
        await session.execute(
            select(func.count())
            .select_from(PlanItem)
            .where(owned_item, unpublished, dated, PlanItem.scheduled_date >= today_expr)
        )
    ).scalar_one()
    schedule = {
        "published": published_items,
        "overdue": overdue,
        "upcoming": upcoming,
    }

    # -- Generation reliability (runs behind planner content) --
    gen_rows = await _all(
        session,
        select(
            AgentRun.status,
            func.count().label("n"),
            func.avg(AgentRun.duration_seconds).label("avg_seconds"),
        )
        .join(PlanItemContent, PlanItemContent.run_id == AgentRun.id)
        .where(owned_content)
        .group_by(AgentRun.status),
    )
    generation = {
        r["status"]: {"count": r["n"], "avg_seconds": round(r["avg_seconds"] or 0, 2)}
        for r in gen_rows
    }
    avg_gen_seconds = round(
        (
            await session.execute(
                select(func.avg(AgentRun.duration_seconds))
                .join(PlanItemContent, PlanItemContent.run_id == AgentRun.id)
                .where(owned_content, AgentRun.duration_seconds.is_not(None))
            )
        ).scalar()
        or 0,
        2,
    )

    # -- Per-platform word metrics (join to source tables via content_ref_id) --
    word_metrics = {}
    for content_type, model in (
        ("linkedin", LinkedinPost),
        ("blog", BlogPost),
        ("youtube_script", YoutubeScript),
    ):
        refs = select(PlanItemContent.content_ref_id).where(
            owned_content, PlanItemContent.content_type == content_type
        )
        row = (
            await session.execute(
                select(
                    func.count().label("c"),
                    func.coalesce(func.sum(model.word_count), 0).label("total"),
                    func.coalesce(func.avg(model.word_count), 0).label("avg"),
                ).where(model.id.in_(refs))
            )
        ).one()
        word_metrics[content_type] = {
            "count": row.c,
            "total_words": int(row.total),
            "avg_words": round(float(row.avg), 1),
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


# ─────────────────────────────────────────────────────────────────────────────
# Personal Intelligence — user rules
# ─────────────────────────────────────────────────────────────────────────────


async def list_user_rules(
    session: AsyncSession,
    user_id: str,
    scope: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    stmt = select(UserRule).where(UserRule.user_id == user_id)
    if scope:
        stmt = stmt.where(or_(UserRule.scope == scope, UserRule.scope == "global"))
    if active_only:
        stmt = stmt.where(UserRule.is_active.is_(True))
    return await _all(session, stmt.order_by(UserRule.priority.asc(), UserRule.created_at.asc()))


async def get_user_rule(session: AsyncSession, rule_id: str, user_id: str) -> dict | None:
    return await _one(
        session, select(UserRule).where(UserRule.id == rule_id, UserRule.user_id == user_id)
    )


async def create_user_rule(
    session: AsyncSession,
    user_id: str,
    scope: str,
    category: str,
    rule_text: str,
    priority: int = 100,
    is_active: bool = True,
) -> dict:
    row = (
        await session.execute(
            insert(UserRule)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                scope=scope,
                category=category,
                rule_text=rule_text,
                priority=priority,
                is_active=is_active,
            )
            .returning(UserRule)
        )
    ).one()
    return row_to_dict(row)


async def update_user_rule(
    session: AsyncSession,
    rule_id: str,
    user_id: str,
    scope: str | None = None,
    category: str | None = None,
    rule_text: str | None = None,
    priority: int | None = None,
    is_active: bool | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if scope is not None:
        values["scope"] = scope
    if category is not None:
        values["category"] = category
    if rule_text is not None:
        values["rule_text"] = rule_text
    if priority is not None:
        values["priority"] = priority
    if is_active is not None:
        values["is_active"] = is_active
    if not values:
        return False
    values["updated_at"] = _now()
    return await _touched(
        session,
        update(UserRule).where(UserRule.id == rule_id, UserRule.user_id == user_id).values(**values),
    )


async def delete_user_rule(session: AsyncSession, rule_id: str, user_id: str) -> bool:
    return await _touched(
        session, delete(UserRule).where(UserRule.id == rule_id, UserRule.user_id == user_id)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Personal Intelligence — user goals
# ─────────────────────────────────────────────────────────────────────────────


async def list_user_goals(
    session: AsyncSession, user_id: str, status: str | None = None
) -> list[dict]:
    stmt = select(UserGoal).where(UserGoal.user_id == user_id)
    if status:
        stmt = stmt.where(UserGoal.status == status)
    return await _all(session, stmt.order_by(UserGoal.deadline.asc()))


async def get_user_goal(session: AsyncSession, goal_id: str, user_id: str) -> dict | None:
    return await _one(
        session, select(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id)
    )


async def create_user_goal(
    session: AsyncSession,
    user_id: str,
    title: str,
    metric: str,
    target_value: float,
    deadline,
    platform: str = "youtube",
    description: str | None = None,
    baseline_value: float = 0.0,
) -> dict:
    row = (
        await session.execute(
            insert(UserGoal)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                title=title,
                description=description,
                platform=platform,
                metric=metric,
                target_value=target_value,
                baseline_value=baseline_value,
                baseline_at=_now(),
                deadline=deadline,
                status="active",
            )
            .returning(UserGoal)
        )
    ).one()
    return row_to_dict(row)


async def update_user_goal(
    session: AsyncSession,
    goal_id: str,
    user_id: str,
    title: str | None = None,
    description: Any = UNSET,
    target_value: float | None = None,
    deadline: Any = None,
    status: str | None = None,
    progress: Any = UNSET,
) -> bool:
    values: dict[str, Any] = {}
    if title is not None:
        values["title"] = title
    if description is not UNSET:
        values["description"] = description
    if target_value is not None:
        values["target_value"] = target_value
    if deadline is not None:
        values["deadline"] = deadline
    if status is not None:
        values["status"] = status
    if progress is not UNSET:
        values["progress"] = progress
    if not values:
        return False
    values["updated_at"] = _now()
    return await _touched(
        session,
        update(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id).values(**values),
    )


async def delete_user_goal(session: AsyncSession, goal_id: str, user_id: str) -> bool:
    return await _touched(
        session, delete(UserGoal).where(UserGoal.id == goal_id, UserGoal.user_id == user_id)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Competitors
# ─────────────────────────────────────────────────────────────────────────────


async def create_competitor_discovery_run(
    session: AsyncSession, user_id: str, niche: str
) -> dict:
    row = (
        await session.execute(
            insert(YoutubeCompetitorDiscoveryRun)
            .values(id=generate_uuid(), user_id=user_id, niche=niche, candidates=[])
            .returning(YoutubeCompetitorDiscoveryRun)
        )
    ).one()
    return row_to_dict(row)


async def get_competitor_discovery_run(
    session: AsyncSession, run_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(YoutubeCompetitorDiscoveryRun).where(
            YoutubeCompetitorDiscoveryRun.id == run_id,
            YoutubeCompetitorDiscoveryRun.user_id == user_id,
        ),
    )


async def get_latest_pending_discovery_run(session: AsyncSession, user_id: str) -> dict | None:
    return await _one(
        session,
        select(YoutubeCompetitorDiscoveryRun)
        .where(
            YoutubeCompetitorDiscoveryRun.user_id == user_id,
            YoutubeCompetitorDiscoveryRun.status == "pending",
        )
        .order_by(YoutubeCompetitorDiscoveryRun.created_at.desc())
        .limit(1),
    )


async def complete_discovery_run(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    candidates: list[dict],
    quota_units_spent: int,
) -> bool:
    return await _touched(
        session,
        update(YoutubeCompetitorDiscoveryRun)
        .where(
            YoutubeCompetitorDiscoveryRun.id == run_id,
            YoutubeCompetitorDiscoveryRun.user_id == user_id,
        )
        .values(
            candidates=candidates,
            status="pending",
            quota_units_spent=quota_units_spent,
        ),
    )


async def decide_discovery_run(
    session: AsyncSession,
    run_id: str,
    user_id: str,
    approved_count: int,
    rejected_count: int,
) -> bool:
    return await _touched(
        session,
        update(YoutubeCompetitorDiscoveryRun)
        .where(
            YoutubeCompetitorDiscoveryRun.id == run_id,
            YoutubeCompetitorDiscoveryRun.user_id == user_id,
        )
        .values(
            status="applied",
            approved_count=approved_count,
            rejected_count=rejected_count,
            decided_at=_now(),
        ),
    )


async def filter_known_competitor_ids(
    session: AsyncSession, user_id: str, channel_ids: list[str]
) -> set[str]:
    """Channel ids already present for this user, in ANY status.

    This is the exclusion guarantee: a channel the user approved OR rejected OR
    removed must never be suggested again, so discovery drops every id this
    query returns before it ever reaches the candidate list.
    """
    if not channel_ids:
        return set()
    rows = await _all(
        session,
        select(YoutubeCompetitor.channel_id).where(
            YoutubeCompetitor.user_id == user_id,
            YoutubeCompetitor.channel_id.in_(channel_ids),
        ),
    )
    return {r["channel_id"] for r in rows}


async def bulk_upsert_competitors(
    session: AsyncSession, user_id: str, rows: list[dict]
) -> int:
    """Insert or refresh many competitor rows in one statement.

    Each dict must carry ``channel_id`` plus whatever columns it wants to set;
    ``user_id``/``created_at``/``updated_at`` are added here. Existing rows keep
    their ``status``/``priority``/``notes`` unless the caller explicitly
    supplies them — a stats refresh must never silently un-reject a channel.
    """
    if not rows:
        return 0
    valid_columns = {c.name for c in YoutubeCompetitor.__table__.columns}
    # Callers pass through LLM/verification dicts that may carry extra
    # display-only fields (e.g. a discovery candidate's "tier" hint, kept in
    # the discovery run's JSONB but not a column here) — drop anything the
    # table doesn't define rather than letting the INSERT fail on it.
    values = [{"user_id": user_id, **{k: v for k, v in r.items() if k in valid_columns}} for r in rows]
    stmt = pg_insert(YoutubeCompetitor).values(values)
    settable = {
        c.name
        for c in YoutubeCompetitor.__table__.columns
        if c.name not in ("user_id", "channel_id", "created_at")
    }
    # Only columns present on every row are safe to reference via .excluded;
    # anything omitted keeps the existing row's value via COALESCE.
    update_cols = set()
    for v in values:
        update_cols.update(v.keys())
    update_cols &= settable
    update_cols.discard("user_id")
    set_ = {
        col: func.coalesce(getattr(stmt.excluded, col), getattr(YoutubeCompetitor, col))
        for col in update_cols
    }
    set_["updated_at"] = func.now()
    result = await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[YoutubeCompetitor.user_id, YoutubeCompetitor.channel_id],
            set_=set_,
        )
    )
    return result.rowcount or 0


async def list_competitors(
    session: AsyncSession,
    user_id: str,
    *,
    limit: int = 50,
    cursor: tuple[Any, str] | None = None,
    status: str = "approved",
    q: str = "",
) -> list[dict]:
    """Keyset-paginated competitor list, newest first.

    Thousands of rows per user rules out OFFSET pagination (it degrades
    linearly with depth); the cursor is the last row's ``(created_at,
    channel_id)``, which the ``ix_youtube_competitors_user_status`` index
    serves directly.
    """
    stmt = select(YoutubeCompetitor).where(
        YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.status == status
    )
    if q:
        stmt = stmt.where(YoutubeCompetitor.title.ilike(f"%{q}%"))
    if cursor is not None:
        cursor_created_at, cursor_channel_id = cursor
        stmt = stmt.where(
            or_(
                YoutubeCompetitor.created_at < cursor_created_at,
                (YoutubeCompetitor.created_at == cursor_created_at)
                & (YoutubeCompetitor.channel_id < cursor_channel_id),
            )
        )
    stmt = stmt.order_by(YoutubeCompetitor.created_at.desc(), YoutubeCompetitor.channel_id.desc())
    return await _all(session, stmt.limit(limit))


async def count_competitors(session: AsyncSession, user_id: str, status: str = "approved") -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(YoutubeCompetitor)
            .where(YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.status == status)
        )
    ).scalar_one()


async def get_competitor(session: AsyncSession, user_id: str, channel_id: str) -> dict | None:
    return await _one(
        session,
        select(YoutubeCompetitor).where(
            YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.channel_id == channel_id
        ),
    )


async def update_competitor(
    session: AsyncSession,
    user_id: str,
    channel_id: str,
    status: str | None = None,
    priority: int | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if priority is not None:
        values["priority"] = priority
    if not values:
        return False
    values["updated_at"] = _now()
    return await _touched(
        session,
        update(YoutubeCompetitor)
        .where(YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.channel_id == channel_id)
        .values(**values),
    )


async def get_competitor_videos(
    session: AsyncSession, user_id: str, channel_id: str, limit: int = 20
) -> list[dict]:
    return await _all(
        session,
        select(YoutubeCompetitorVideo)
        .where(
            YoutubeCompetitorVideo.user_id == user_id,
            YoutubeCompetitorVideo.channel_id == channel_id,
        )
        .order_by(YoutubeCompetitorVideo.published_at.desc())
        .limit(limit),
    )


async def get_all_competitor_videos(
    session: AsyncSession,
    user_id: str,
    *,
    limit: int = 30,
    offset: int = 0,
    channel_id: str | None = None,
) -> tuple[list[dict], int]:
    """All competitor videos sorted by views desc with optional channel filter.

    Returns (rows, total_count) for pagination.
    """
    base_where = [
        YoutubeCompetitorVideo.user_id == user_id,
        YoutubeCompetitor.status == "approved",
    ]
    if channel_id:
        base_where.append(YoutubeCompetitorVideo.channel_id == channel_id)

    join_cond = (YoutubeCompetitorVideo.user_id == YoutubeCompetitor.user_id) & (
        YoutubeCompetitorVideo.channel_id == YoutubeCompetitor.channel_id
    )

    rows = await _all(
        session,
        select(
            YoutubeCompetitorVideo,
            YoutubeCompetitor.title.label("channel_title"),
            YoutubeCompetitor.thumbnail_url.label("channel_thumbnail"),
            YoutubeCompetitor.handle.label("channel_handle"),
        )
        .join(YoutubeCompetitor, join_cond)
        .where(*base_where)
        .order_by(YoutubeCompetitorVideo.views.desc())
        .limit(limit)
        .offset(offset),
    )

    count_result = await session.execute(
        select(func.count())
        .select_from(YoutubeCompetitorVideo)
        .join(YoutubeCompetitor, join_cond)
        .where(*base_where)
    )
    total = count_result.scalar() or 0
    return rows, total


async def get_competitor_recent_videos(
    session: AsyncSession, user_id: str, *, days: int = 45, limit: int = 40
) -> list[dict]:
    """Recent videos across every tracked competitor — the context feed."""
    since = _now() - timedelta(days=days)
    return await _all(
        session,
        select(YoutubeCompetitorVideo, YoutubeCompetitor.title.label("channel_title"))
        .join(
            YoutubeCompetitor,
            (YoutubeCompetitorVideo.user_id == YoutubeCompetitor.user_id)
            & (YoutubeCompetitorVideo.channel_id == YoutubeCompetitor.channel_id),
        )
        .where(
            YoutubeCompetitorVideo.user_id == user_id,
            YoutubeCompetitor.status == "approved",
            YoutubeCompetitorVideo.published_at >= since,
        )
        .order_by(YoutubeCompetitorVideo.published_at.desc())
        .limit(limit),
    )


async def bulk_upsert_competitor_videos(
    session: AsyncSession, user_id: str, videos: list[dict]
) -> int:
    """Insert or refresh many competitor-video rows in one statement.

    Each dict needs ``video_id``, ``channel_id`` plus the metric columns; see
    ``app.services.youtube_competitor.sync_competitor_videos`` for the shape.
    """
    if not videos:
        return 0
    values = [{"user_id": user_id, **v} for v in videos]
    stmt = pg_insert(YoutubeCompetitorVideo).values(values)
    result = await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[YoutubeCompetitorVideo.user_id, YoutubeCompetitorVideo.video_id],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "published_at": func.coalesce(
                    stmt.excluded.published_at, YoutubeCompetitorVideo.published_at
                ),
                "duration_seconds": stmt.excluded.duration_seconds,
                "is_short": stmt.excluded.is_short,
                "views": stmt.excluded.views,
                "likes": stmt.excluded.likes,
                "comments": stmt.excluded.comments,
                "tags": stmt.excluded.tags,
                "thumbnail_url": func.coalesce(
                    stmt.excluded.thumbnail_url, YoutubeCompetitorVideo.thumbnail_url
                ),
                "fetched_at": func.now(),
            },
        )
    )
    return result.rowcount or 0


async def list_competitor_names(session: AsyncSession, user_id: str, limit: int = 150) -> list[str]:
    """Titles of every tracked competitor, any status — the discovery prompt's
    exclusion hint. (The authoritative exclusion is filter_known_competitor_ids,
    run on real channel_ids after verification; this is only to stop the LLM
    wasting proposal slots on channels it will just be told no about.)"""
    rows = await _all(
        session,
        select(YoutubeCompetitor.title)
        .where(YoutubeCompetitor.user_id == user_id)
        .order_by(YoutubeCompetitor.created_at.desc())
        .limit(limit),
    )
    return [r["title"] for r in rows]


async def stamp_competitor_synced(
    session: AsyncSession, user_id: str, channel_id: str, error: str | None = None
) -> bool:
    return await _touched(
        session,
        update(YoutubeCompetitor)
        .where(YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.channel_id == channel_id)
        .values(last_synced_at=_now(), sync_error=error, updated_at=_now()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Assistant (chat history + confirmable actions)
# ─────────────────────────────────────────────────────────────────────────────


async def create_assistant_conversation(
    session: AsyncSession, user_id: str, title: str
) -> dict:
    return await _one(
        session,
        insert(AssistantConversation)
        .values(id=generate_uuid(), user_id=user_id, title=title)
        .returning(AssistantConversation),
    )


async def get_assistant_conversation(
    session: AsyncSession, conversation_id: str, user_id: str
) -> dict | None:
    return await _one(
        session,
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        ),
    )


async def list_assistant_conversations(
    session: AsyncSession, user_id: str, limit: int = 30
) -> list[dict]:
    """Sidebar list: threads newest-active first, with their message counts."""
    rows = await _all(
        session,
        select(
            AssistantConversation,
            func.count(AssistantMessage.id).label("message_count"),
        )
        .outerjoin(
            AssistantMessage,
            AssistantMessage.conversation_id == AssistantConversation.id,
        )
        .where(AssistantConversation.user_id == user_id)
        .group_by(AssistantConversation.id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(limit),
    )
    return rows


async def touch_assistant_conversation(
    session: AsyncSession, conversation_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        update(AssistantConversation)
        .where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
        .values(updated_at=_now()),
    )


async def delete_assistant_conversation(
    session: AsyncSession, conversation_id: str, user_id: str
) -> bool:
    """Messages and their actions go with it, via ON DELETE CASCADE."""
    return await _touched(
        session,
        delete(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        ),
    )


async def create_assistant_message(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    meta: dict | None = None,
) -> dict:
    return await _one(
        session,
        insert(AssistantMessage)
        .values(
            id=generate_uuid(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            meta=meta or {},
        )
        .returning(AssistantMessage),
    )


async def get_assistant_messages(
    session: AsyncSession, conversation_id: str, user_id: str, limit: int = 50
) -> list[dict]:
    """Transcript in order. Scoped by conversation *and* user, never one alone."""
    return await _all(
        session,
        select(AssistantMessage)
        .where(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.user_id == user_id,
        )
        .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        .limit(limit),
    )


async def get_recent_assistant_messages(
    session: AsyncSession, conversation_id: str, user_id: str, limit: int = 6
) -> list[dict]:
    """The last N turns, oldest-first — the prompt's conversation window.

    Ordered DESC in SQL so the LIMIT takes the *newest* rows, then reversed, so
    a long thread does not have to be fully materialised to read its tail.
    """
    rows = await _all(
        session,
        select(AssistantMessage)
        .where(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.user_id == user_id,
        )
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .limit(limit),
    )
    return list(reversed(rows))


async def create_assistant_action(
    session: AsyncSession,
    message_id: str,
    user_id: str,
    item_id: str,
    verb: str,
    label: str,
    params: dict,
    expires_at: datetime,
    content_id: str | None = None,
) -> dict:
    return await _one(
        session,
        insert(AssistantAction)
        .values(
            id=generate_uuid(),
            message_id=message_id,
            user_id=user_id,
            item_id=item_id,
            content_id=content_id,
            verb=verb,
            label=label,
            params=params or {},
            expires_at=expires_at,
        )
        .returning(AssistantAction),
    )


async def get_assistant_action(
    session: AsyncSession, action_id: str, user_id: str, for_update: bool = False
) -> dict | None:
    """Fetch one action, tenant-scoped in SQL.

    ``for_update`` takes a row lock, which is what makes confirm single-use: two
    concurrent confirms serialise, and the second sees the status the first
    already advanced past.
    """
    stmt = select(AssistantAction).where(
        AssistantAction.id == action_id, AssistantAction.user_id == user_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await _one(session, stmt)


async def update_assistant_action(
    session: AsyncSession,
    action_id: str,
    user_id: str,
    status: str | None = None,
    result: dict | None = None,
    executed_at: datetime | None = None,
) -> bool:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if result is not None:
        values["result"] = result
    if executed_at is not None:
        values["executed_at"] = executed_at
    if not values:
        return False
    return await _touched(
        session,
        update(AssistantAction)
        .where(
            AssistantAction.id == action_id, AssistantAction.user_id == user_id
        )
        .values(**values),
    )


async def get_assistant_actions_for_messages(
    session: AsyncSession, message_ids: list[str], user_id: str
) -> list[dict]:
    """Every action attached to a batch of messages — one query for a replayed
    transcript, rather than one per assistant bubble."""
    if not message_ids:
        return []
    return await _all(
        session,
        select(AssistantAction)
        .where(
            AssistantAction.message_id.in_(message_ids),
            AssistantAction.user_id == user_id,
        )
        .order_by(AssistantAction.created_at.asc()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Image studio
# ─────────────────────────────────────────────────────────────────────────────


async def create_generated_image(
    session: AsyncSession,
    user_id: str,
    prompt: str,
    filename: str,
    model: str,
    aspect_ratio: str,
    image_size: str,
    negative_prompt: str | None = None,
    seed: int | None = None,
    duration_s: float | None = None,
) -> dict:
    """Record one render. The row is what later proves the file is this user's."""
    row = (
        await session.execute(
            insert(GeneratedImage)
            .values(
                id=generate_uuid(),
                user_id=user_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                seed=seed,
                filename=filename,
                duration_s=duration_s,
            )
            .returning(GeneratedImage)
        )
    ).one()
    return row_to_dict(row)


async def get_generated_images(
    session: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
) -> list[dict]:
    """The user's gallery, newest first. Index-backed by ix_generated_images_user_created."""
    return await _all(
        session,
        select(GeneratedImage)
        .where(GeneratedImage.user_id == user_id)
        .order_by(GeneratedImage.created_at.desc(), GeneratedImage.id.desc())
        .limit(limit)
        .offset(offset),
    )


async def count_generated_images(session: AsyncSession, user_id: str) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(GeneratedImage).where(
                GeneratedImage.user_id == user_id
            )
        )
    ).scalar_one()


async def get_generated_image(
    session: AsyncSession, image_id: str, user_id: str
) -> dict | None:
    """One render, owner-scoped. The user_id predicate is the authorization."""
    return await _one(
        session,
        select(GeneratedImage).where(
            GeneratedImage.id == image_id, GeneratedImage.user_id == user_id
        ),
    )


async def delete_generated_image(
    session: AsyncSession, image_id: str, user_id: str
) -> bool:
    return await _touched(
        session,
        delete(GeneratedImage).where(
            GeneratedImage.id == image_id, GeneratedImage.user_id == user_id
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# YouTube prospects — third-party channel audits for outreach
# ─────────────────────────────────────────────────────────────────────────────


async def upsert_prospect(session: AsyncSession, user_id: str, row: dict) -> dict:
    """Insert or refresh one prospect, keyed on ``(user_id, channel_id)``.

    ``outreach_status`` is never overwritten by a refresh — re-running the audit
    on someone already marked "contacted" must not reset them to "new".
    """
    valid = {c.name for c in YoutubeProspect.__table__.columns}
    values = {"user_id": user_id, **{k: v for k, v in row.items() if k in valid}}
    values.pop("id", None)
    stmt = pg_insert(YoutubeProspect).values(values)
    set_ = {
        k: getattr(stmt.excluded, k)
        for k in values
        if k not in ("user_id", "channel_id", "created_at", "outreach_status")
    }
    set_["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=[YoutubeProspect.user_id, YoutubeProspect.channel_id],
        set_=set_,
    ).returning(YoutubeProspect)
    return row_to_dict((await session.execute(stmt)).one())


async def list_prospects(session: AsyncSession, user_id: str, limit: int = 100) -> list[dict]:
    return await _all(
        session,
        select(YoutubeProspect)
        .where(YoutubeProspect.user_id == user_id)
        .order_by(YoutubeProspect.created_at.desc())
        .limit(limit),
    )


async def get_prospect(session: AsyncSession, user_id: str, channel_id: str) -> dict | None:
    """One prospect, owner-scoped. The user_id predicate is the authorization."""
    return await _one(
        session,
        select(YoutubeProspect).where(
            YoutubeProspect.user_id == user_id, YoutubeProspect.channel_id == channel_id
        ),
    )


async def update_prospect_status(
    session: AsyncSession, user_id: str, channel_id: str, status: str
) -> dict | None:
    return await _one(
        session,
        update(YoutubeProspect)
        .where(YoutubeProspect.user_id == user_id, YoutubeProspect.channel_id == channel_id)
        .values(outreach_status=status, updated_at=func.now())
        .returning(YoutubeProspect),
    )


async def delete_prospect(session: AsyncSession, user_id: str, channel_id: str) -> bool:
    """Reports cascade via the FK on ``youtube_prospect_reports.prospect_id``."""
    return await _touched(
        session,
        delete(YoutubeProspect).where(
            YoutubeProspect.user_id == user_id, YoutubeProspect.channel_id == channel_id
        ),
    )


async def create_prospect_report(
    session: AsyncSession,
    user_id: str,
    prospect_id: str,
    kind: str,
    payload: dict,
    weeks: int | None = None,
    model: str | None = None,
    tier: dict | None = None,
) -> dict:
    """Insert one report half, recording which cascade tier produced it.

    ``tier`` comes from the report's provenance block. It is defaulted rather
    than required so that a caller which forgets it writes an ``internal_only``
    row — blocked from export — instead of an unmarked one that would sail
    through the gate.
    """
    tier = tier or {}
    return await _one(
        session,
        insert(YoutubeProspectReport)
        .values(
            id=generate_uuid(),
            prospect_id=prospect_id,
            user_id=user_id,
            kind=kind,
            weeks=weeks,
            model=model,
            tier_index=tier.get("index"),
            tier_name=tier.get("name"),
            tier_grade=tier.get("grade") or UNKNOWN_GRADE,
            resolved_model=tier.get("model"),
            payload_json=payload,
        )
        .returning(YoutubeProspectReport),
    )


async def get_latest_prospect_report(
    session: AsyncSession, user_id: str, prospect_id: str, kind: str
) -> dict | None:
    return await _one(
        session,
        select(YoutubeProspectReport)
        .where(
            YoutubeProspectReport.user_id == user_id,
            YoutubeProspectReport.prospect_id == prospect_id,
            YoutubeProspectReport.kind == kind,
        )
        .order_by(YoutubeProspectReport.created_at.desc())
        .limit(1),
    )
