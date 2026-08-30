"""
Synchronous query layer — the Celery worker path.

Only the functions workers actually call live here (eight of them). Everything
else is async-only and lives in :mod:`app.db.queries`.

These are *not* duplicates of the async versions. ``app.db.queries`` re-exposes
each of them through ``AsyncSession.run_sync()``, which runs this same code
inside SQLAlchemy's greenlet context — so the async path gets real non-blocking
I/O without a second implementation to keep in step. Change the logic here and
both callers change together.

Every function takes an explicit ``user_id`` and scopes its statement by it.
The previous versions keyed writes on ``run_id`` alone, which meant any caller
holding a run id could mutate another tenant's run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db._util import (
    generate_uuid,
    hashtag_count,
    reading_time_minutes,
    row_to_dict,
    rows_to_dicts,
    slugify,
)
from app.db.tables import (
    AgentRun,
    BlogPost,
    GoogleOAuthToken,
    InstagramOAuthToken,
    LinkedinPost,
    TaskStep,
    UsageLimit,
    UserGoal,
    UserRule,
    YoutubeScript,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Runs ─────────────────────────────────────────────────────────────────────


def update_run_status(
    session: Session,
    run_id: str,
    user_id: str,
    status: str,
    final_result: str | None = None,
    duration: float | None = None,
    topic: str | None = None,
    image_url: str | None = None,
) -> bool:
    """Move a run to a new status. Returns False if the run isn't the user's."""
    values: dict = {
        "status": status,
        "final_result": final_result,
        "duration_seconds": duration,
    }
    if status in ("completed", "failed"):
        values["completed_at"] = _now()
    if topic is not None:
        values["topic"] = topic
    if image_url is not None:
        values["image_url"] = image_url

    result = session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .values(**values)
    )
    return result.rowcount > 0


# ── Task steps ───────────────────────────────────────────────────────────────


def insert_task_step(
    session: Session,
    run_id: str,
    user_id: str,
    agent_name: str,
    task_name: str,
    output: str | None,
    status: str = "done",
) -> dict:
    row = session.execute(
        insert(TaskStep)
        .values(
            run_id=run_id,
            user_id=user_id,
            agent_name=agent_name,
            task_name=task_name,
            output=output,
            status=status,
        )
        .returning(TaskStep)
    ).one()
    return row_to_dict(row)


# ── Usage limits ─────────────────────────────────────────────────────────────


def get_usage(session: Session, user_id: str) -> dict | None:
    return row_to_dict(
        session.execute(
            select(UsageLimit).where(UsageLimit.user_id == user_id)
        ).one_or_none()
    )


def increment_usage(session: Session, user_id: str) -> None:
    session.execute(
        update(UsageLimit)
        .where(UsageLimit.user_id == user_id)
        .values(runs_this_month=UsageLimit.runs_this_month + 1)
    )


def reset_usage_if_expired(session: Session, user_id: str) -> None:
    """Roll the monthly counter over once ``reset_at`` has passed.

    Expressed as a single conditional UPDATE rather than the previous
    read-then-write: two workers finishing a run at the same moment could both
    observe an expired window and both reset, losing one increment.
    """
    session.execute(
        update(UsageLimit)
        .where(
            UsageLimit.user_id == user_id,
            UsageLimit.reset_at.is_not(None),
            UsageLimit.reset_at < func.now(),
        )
        .values(runs_this_month=0, reset_at=_now() + timedelta(days=30))
    )


# ── Generated content ────────────────────────────────────────────────────────


def save_blog_post(
    session: Session,
    run_id: str | None,
    user_id: str,
    topic: str,
    title: str | None,
    content: str,
    niche: str | None,
    approved: bool = False,
    word_count: int | None = None,
) -> dict:
    """Persist a long-form blog post and return the full row.

    ``word_count`` may come from the pipeline or be counted here; reading time
    and a unique URL-safe slug are always derived.
    """
    blog_id = generate_uuid()
    if word_count is None:
        word_count = len(content.split())

    base_slug = slugify(title or topic)
    # The slug column is globally UNIQUE (it addresses the public reader), so
    # disambiguate a collision with a short id suffix.
    taken = session.execute(
        select(BlogPost.id).where(BlogPost.slug == base_slug).limit(1)
    ).first()
    slug = f"{base_slug}-{blog_id[:8]}" if taken else base_slug

    row = session.execute(
        insert(BlogPost)
        .values(
            id=blog_id,
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            title=title,
            content=content,
            word_count=word_count,
            reading_time_minutes=reading_time_minutes(word_count),
            niche=niche,
            approved=bool(approved),
            slug=slug,
        )
        .returning(BlogPost)
    ).one()
    return row_to_dict(row)


def save_linkedin_post(
    session: Session,
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
    row = session.execute(
        insert(LinkedinPost)
        .values(
            id=generate_uuid(),
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            post_text=post_text,
            hook=hook,
            angle_type=angle_type,
            word_count=word_count,
            hashtag_count=hashtag_count(post_text),
            approved=bool(approved),
            niche=niche,
        )
        .returning(LinkedinPost)
    ).one()
    return row_to_dict(row)


def save_youtube_script(
    session: Session,
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
    # seo_tags is JSONB now; callers historically passed a JSON *string*.
    if isinstance(seo_tags, str):
        import json

        try:
            seo_tags = json.loads(seo_tags)
        except (ValueError, TypeError):
            seo_tags = [seo_tags] if seo_tags else None

    row = session.execute(
        insert(YoutubeScript)
        .values(
            id=generate_uuid(),
            run_id=run_id,
            user_id=user_id,
            topic=topic,
            title=title,
            script=script,
            word_count=word_count,
            seo_title=seo_title,
            seo_description=seo_description,
            seo_tags=seo_tags,
            approved=bool(approved),
            niche=niche,
        )
        .returning(YoutubeScript)
    ).one()
    return row_to_dict(row)


# ── Google OAuth tokens ──────────────────────────────────────────────────────
# Implemented on the sync side because the credential path is inherently
# blocking: loading a credential may trigger a token refresh over HTTPS. The
# whole operation therefore belongs off the event loop, and async callers reach
# it through asyncio.to_thread rather than through the session.


def save_google_tokens(
    session: Session,
    user_id: str,
    token_json_encrypted: str,
    scopes: str | None = None,
    connected_email: str | None = None,
) -> None:
    stmt = pg_insert(GoogleOAuthToken).values(
        user_id=user_id,
        token_json_encrypted=token_json_encrypted,
        scopes=scopes,
        connected_email=connected_email,
        updated_at=_now(),
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[GoogleOAuthToken.user_id],
            set_={
                "token_json_encrypted": stmt.excluded.token_json_encrypted,
                # A refresh re-persists the credential without re-sending the
                # scope list or email; COALESCE keeps the known values.
                "scopes": func.coalesce(stmt.excluded.scopes, GoogleOAuthToken.scopes),
                "connected_email": func.coalesce(
                    stmt.excluded.connected_email, GoogleOAuthToken.connected_email
                ),
                "updated_at": _now(),
            },
        )
    )


def get_google_tokens(session: Session, user_id: str) -> dict | None:
    return row_to_dict(
        session.execute(
            select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
        ).one_or_none()
    )


def delete_google_tokens(session: Session, user_id: str) -> bool:
    result = session.execute(
        delete(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
    )
    return result.rowcount > 0


# ── Instagram OAuth tokens ───────────────────────────────────────────────────


def save_instagram_tokens(
    session: Session,
    user_id: str,
    ig_user_id: str,
    username: str | None,
    access_token_enc: str,
    token_expires_at: datetime,
    scopes: str | None = None,
) -> None:
    stmt = pg_insert(InstagramOAuthToken).values(
        user_id=user_id,
        ig_user_id=ig_user_id,
        username=username,
        access_token_enc=access_token_enc,
        token_expires_at=token_expires_at,
        scopes=scopes,
        updated_at=_now(),
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[InstagramOAuthToken.user_id],
            set_={
                "ig_user_id": stmt.excluded.ig_user_id,
                "username": stmt.excluded.username,
                "access_token_enc": stmt.excluded.access_token_enc,
                "token_expires_at": stmt.excluded.token_expires_at,
                "scopes": func.coalesce(stmt.excluded.scopes, InstagramOAuthToken.scopes),
                "updated_at": _now(),
            },
        )
    )


def get_instagram_tokens(session: Session, user_id: str) -> dict | None:
    return row_to_dict(
        session.execute(
            select(InstagramOAuthToken).where(InstagramOAuthToken.user_id == user_id)
        ).one_or_none()
    )


def delete_instagram_tokens(session: Session, user_id: str) -> bool:
    result = session.execute(
        delete(InstagramOAuthToken).where(InstagramOAuthToken.user_id == user_id)
    )
    return result.rowcount > 0


def list_instagram_connected_user_ids(session: Session) -> list[str]:
    return list(session.execute(select(InstagramOAuthToken.user_id)).scalars())


# ── Personal Intelligence (read path for pipeline Celery tasks) ──────────────


def list_user_rules(
    session: Session, user_id: str, scope: str | None = None, active_only: bool = False
) -> list[dict]:
    from sqlalchemy import or_

    stmt = select(UserRule).where(UserRule.user_id == user_id)
    if scope:
        stmt = stmt.where(or_(UserRule.scope == scope, UserRule.scope == "global"))
    if active_only:
        stmt = stmt.where(UserRule.is_active.is_(True))
    return rows_to_dicts(
        session.execute(stmt.order_by(UserRule.priority.asc(), UserRule.created_at.asc()))
    )


def list_user_goals(session: Session, user_id: str, status: str | None = None) -> list[dict]:
    stmt = select(UserGoal).where(UserGoal.user_id == user_id)
    if status:
        stmt = stmt.where(UserGoal.status == status)
    return rows_to_dicts(session.execute(stmt.order_by(UserGoal.deadline.asc())))


# ── Competitors (Celery weekly sync path) ─────────────────────────────────────


def select_competitors_for_weekly_sync(session: Session, user_id: str, cap: int) -> list[dict]:
    """Stalest-first, tier-prioritized approved competitors for one user.

    Served by the partial-order index ``ix_youtube_competitors_sync``
    (user_id, status, priority, last_synced_at ASC NULLS FIRST): never-synced
    channels come first, then the ones it's been longest since touching —
    so the cap rotates through the whole list over successive Sundays instead
    of permanently starving the tail.
    """
    from app.db.tables import YoutubeCompetitor

    return rows_to_dicts(
        session.execute(
            select(YoutubeCompetitor)
            .where(
                YoutubeCompetitor.user_id == user_id,
                YoutubeCompetitor.status == "approved",
            )
            .order_by(
                YoutubeCompetitor.priority.desc(),
                YoutubeCompetitor.last_synced_at.asc().nulls_first(),
            )
            .limit(cap)
        )
    )


def mark_competitor_synced(
    session: Session, user_id: str, channel_id: str, error: str | None = None
) -> None:
    from app.db.tables import YoutubeCompetitor

    session.execute(
        update(YoutubeCompetitor)
        .where(YoutubeCompetitor.user_id == user_id, YoutubeCompetitor.channel_id == channel_id)
        .values(last_synced_at=_now(), sync_error=error, updated_at=_now())
    )


def bulk_upsert_competitor_stats(session: Session, user_id: str, rows: list[dict]) -> int:
    """Refresh subscriber/view/video counts for many EXISTING competitors.

    A plain per-row UPDATE, not an INSERT ... ON CONFLICT: these channel_ids
    always come from ``select_competitors_for_weekly_sync``, i.e. rows that
    already exist. An upsert would still construct a candidate INSERT row for
    each one — and since this refresh only carries the three stat columns,
    that row would be missing ``title`` (NOT NULL, no default) and fail before
    Postgres ever gets to resolve the conflict.
    """
    from app.db.tables import YoutubeCompetitor

    if not rows:
        return 0
    touched = 0
    for r in rows:
        result = session.execute(
            update(YoutubeCompetitor)
            .where(
                YoutubeCompetitor.user_id == user_id,
                YoutubeCompetitor.channel_id == r["channel_id"],
            )
            .values(
                subscriber_count=r["subscriber_count"],
                view_count=r["view_count"],
                video_count=r["video_count"],
                updated_at=func.now(),
            )
        )
        touched += result.rowcount
    return touched


def bulk_upsert_competitor_videos(session: Session, user_id: str, videos: list[dict]) -> int:
    from app.db.tables import YoutubeCompetitorVideo

    if not videos:
        return 0
    values = [{"user_id": user_id, **v} for v in videos]
    stmt = pg_insert(YoutubeCompetitorVideo).values(values)
    result = session.execute(
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
