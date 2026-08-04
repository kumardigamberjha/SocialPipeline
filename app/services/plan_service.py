"""
Content-plan domain logic: generation dispatch and lazy status reconciliation.

Reconciliation design
---------------------
plan_item_content rows are created with review_status='generating' and a run_id.
The pipelines themselves (Celery tasks / BackgroundTasks fallbacks) know nothing
about plans — they just write their content row and flip the agent_run status.
Whenever plan data is read, reconcile_plan_item_content() checks each
'generating' row against its run: on 'completed' it links the produced content
row (content_ref_id) and marks 'ready'; on 'failed' it marks 'failed'. A
completed youtube_script also auto-advances the owning item's production_status
from 'pending' to 'script_generated'.
"""

import logging

from fastapi import BackgroundTasks, HTTPException

from app.db import queries
from app.services.dispatch import (
    BLOG_QUEUE,
    LINKEDIN_QUEUE,
    YOUTUBE_QUEUE,
    run_blog_fallback,
    run_linkedin_fallback,
    run_youtube_fallback,
    should_use_celery,
)

logger = logging.getLogger(__name__)

CONTENT_TYPES = ("linkedin", "blog", "youtube_script")

# content_type -> lookup for the produced row by run_id
_CONTENT_LOOKUP = {
    "linkedin": queries.get_linkedin_posts_by_run_id,
    "blog": queries.get_blog_posts_by_run_id,
    "youtube_script": queries.get_youtube_scripts_by_run_id,
}


# ── Reconciliation ───────────────────────────────────────────────────────────


def reconcile_plan_item_content(content: dict) -> dict:
    """Advance a 'generating' content row from its run's terminal state.
    Returns the (possibly updated) row."""
    if content["review_status"] != "generating" or not content.get("run_id"):
        return content

    run = queries.get_run_by_id(content["run_id"])
    if not run or run["status"] in ("pending", "running"):
        return content

    if run["status"] == "failed":
        queries.update_plan_item_content(content["id"], review_status="failed")
        content["review_status"] = "failed"
        return content

    # run completed — link the produced content row
    rows = _CONTENT_LOOKUP[content["content_type"]](content["run_id"])
    if not rows:
        # Completed run but no saved row (should not happen) — surface as failed.
        queries.update_plan_item_content(content["id"], review_status="failed")
        content["review_status"] = "failed"
        return content

    ref_id = rows[-1]["id"]
    queries.update_plan_item_content(content["id"], content_ref_id=ref_id, review_status="ready")
    content["content_ref_id"] = ref_id
    content["review_status"] = "ready"

    if content["content_type"] == "youtube_script":
        item = queries.get_plan_item_by_id(content["item_id"], content["user_id"])
        if item and item["production_status"] == "pending":
            queries.update_plan_item(item["id"], content["user_id"], production_status="script_generated")

    return content


def get_item_contents_reconciled(item_id: str, user_id: str) -> list[dict]:
    return [reconcile_plan_item_content(c) for c in queries.get_plan_item_contents(item_id, user_id)]


def get_plan_detail(plan_id: str, user_id: str) -> dict | None:
    """Plan + items + reconciled content summaries — the planner UI's main read."""
    plan = queries.get_content_plan_by_id(plan_id, user_id)
    if not plan:
        return None
    items = queries.get_plan_items(plan_id, user_id)
    for item in items:
        item["contents"] = get_item_contents_reconciled(item["id"], user_id)
        # Reconciliation may have advanced production_status — re-read cheaply.
        if any(c["content_type"] == "youtube_script" and c["review_status"] == "ready" for c in item["contents"]):
            fresh = queries.get_plan_item_by_id(item["id"], user_id)
            if fresh:
                item["production_status"] = fresh["production_status"]
    plan["items"] = items
    return plan


# ── Content hydration (review modal) ─────────────────────────────────────────


def hydrate_content(content: dict) -> dict:
    """Attach title/body from the source table to a plan_item_content row."""
    hydrated = dict(content)
    hydrated["title"] = None
    hydrated["body"] = None
    hydrated["meta"] = {}
    ref_id, user_id = content.get("content_ref_id"), content["user_id"]
    if not ref_id:
        return hydrated

    if content["content_type"] == "linkedin":
        row = queries.get_linkedin_post_by_id(ref_id, user_id)
        if row:
            hydrated["title"] = row["hook"]
            hydrated["body"] = row["post_text"]
            hydrated["meta"] = {"word_count": row["word_count"], "hashtag_count": row["hashtag_count"],
                                "angle_type": row["angle_type"], "pipeline_approved": bool(row["approved"])}
    elif content["content_type"] == "blog":
        row = queries.get_blog_by_id(ref_id, user_id)
        if row:
            hydrated["title"] = row["title"]
            hydrated["body"] = row["content"]
            hydrated["meta"] = {"word_count": row["word_count"], "slug": row["slug"],
                                "reading_time_minutes": row["reading_time_minutes"],
                                "pipeline_approved": bool(row["approved"])}
    elif content["content_type"] == "youtube_script":
        row = queries.get_youtube_script_by_id(ref_id, user_id)
        if row:
            hydrated["title"] = row["title"]
            hydrated["body"] = row["script"]
            hydrated["meta"] = {"word_count": row["word_count"], "seo_title": row["seo_title"],
                                "seo_description": row["seo_description"], "seo_tags": row["seo_tags"],
                                "pipeline_approved": bool(row["approved"])}
    return hydrated


def set_source_approved(content: dict, approved: bool) -> None:
    """Persist the human decision on the underlying content table too."""
    ref_id = content.get("content_ref_id")
    if not ref_id:
        return
    table = {"linkedin": "linkedin_posts", "blog": "blog_posts", "youtube_script": "youtube_scripts"}[content["content_type"]]
    db = queries.get_db()
    db.execute(f"UPDATE {table} SET approved = ? WHERE id = ? AND user_id = ?",
               (1 if approved else 0, ref_id, content["user_id"]))
    db.commit()


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _remaining_quota(user_id: str) -> int:
    queries.reset_usage_if_expired(user_id)
    usage = queries.get_usage(user_id)
    if not usage:
        queries.init_usage(user_id)
        usage = queries.get_usage(user_id)
    if not usage:
        return 0
    return max(0, usage["max_runs_per_month"] - usage["runs_this_month"])


def dispatch_item_content(item: dict, content_type: str, provider: str, niche: str,
                          background_tasks: BackgroundTasks) -> dict:
    """Create a run + plan_item_content link and dispatch one pipeline.
    Returns {content_type, run_id, content_id}."""
    # Lazy imports so a broken Celery import can never take the API down.
    from app.tasks.blog_task import run_blog_pipeline
    from app.tasks.linkedin_task import run_linkedin_pipeline
    from app.tasks.youtube_task import run_youtube_pipeline

    user_id = item["user_id"]
    topic = item["topic"]
    video_format = item.get("video_format") or "full"
    run = queries.create_run(user_id, topic, provider)
    run_id = run["id"]
    content = queries.create_plan_item_content(item["id"], user_id, content_type, run_id)

    celery_specs = {
        "linkedin": (run_linkedin_pipeline, LINKEDIN_QUEUE, [run_id, topic, niche, user_id, provider]),
        "blog": (run_blog_pipeline, BLOG_QUEUE, [run_id, topic, topic, user_id, provider]),  # target_keyword = topic
        "youtube_script": (run_youtube_pipeline, YOUTUBE_QUEUE, [run_id, topic, niche, user_id, provider, video_format]),
    }
    fallback_specs = {
        "linkedin": (run_linkedin_fallback, (run_id, topic, niche, user_id, provider)),
        "blog": (run_blog_fallback, (run_id, topic, topic, user_id, provider)),
        "youtube_script": (run_youtube_fallback, (run_id, topic, niche, user_id, provider, video_format)),
    }

    task, queue, args = celery_specs[content_type]
    fb_fn, fb_args = fallback_specs[content_type]

    dispatched_to_celery = False
    if should_use_celery(queue):
        try:
            task.apply_async(args=args, queue=queue, ignore_result=True)
            dispatched_to_celery = True
        except Exception as exc:
            logger.warning("Celery dispatch failed for %s, using BackgroundTasks: %s", content_type, exc)

    if not dispatched_to_celery:
        logger.info("Running %s pipeline in-process (no Celery worker) ▸ run_id=%s", content_type, run_id)
        background_tasks.add_task(fb_fn, *fb_args)

    return {"content_type": content_type, "run_id": run_id, "content_id": content["id"]}


def dispatch_generation(item: dict, content_type: str, provider: str, niche: str,
                        background_tasks: BackgroundTasks) -> list[dict]:
    """Dispatch one content type or all three, gating on remaining quota upfront."""
    types = list(CONTENT_TYPES) if content_type == "all" else [content_type]
    remaining = _remaining_quota(item["user_id"])
    if remaining < len(types):
        raise HTTPException(
            status_code=429,
            detail=f"Not enough runs left this month: need {len(types)}, have {remaining}. Nothing was dispatched.",
        )
    return [dispatch_item_content(item, t, provider, niche, background_tasks) for t in types]
