"""
Shared pipeline dispatch.

Every generation pipeline (LinkedIn / Blog / YouTube) runs on a dedicated Celery
queue. This module centralises the queue names, the task signatures and the
"can we actually reach a worker?" decision so the linkedin/blog/youtube/planner
routers all share one implementation.

Why the worker check matters
----------------------------
Checking only that Redis is reachable is not enough: if Redis is up but no
worker is draining the target queue, ``apply_async`` silently enqueues a task
that never runs and the generation hangs forever.

That check used to run *inline on every request* — a synchronous
``control.inspect()`` broadcast with a 0.75s wait, on a path the user is
blocked on, producing an answer already stale by the time ``apply_async``
returned. It is now served from a short-lived cache (see :class:`_WorkerMap`),
so at most one request per refresh interval pays for it.

In-process fallback
-------------------
When no worker is available the pipeline can run inside the API process via
``BackgroundTasks``. That is a **development** convenience: a multi-minute job
in an API worker blocks a slot and, behind Cloudflare's ~100s proxy timeout,
cannot report success anyway. ``ALLOW_INPROCESS_FALLBACK`` is refused in
production by the settings validator.

The fallback executes the Celery task itself via ``.apply()`` rather than a
parallel re-implementation. Three hand-written fallback functions used to mirror
the tasks' status transitions, telemetry, content save and usage increment —
four chances each for the two copies to drift apart.
"""

from __future__ import annotations

import logging
import threading
import time

from app.config import get_settings
from app.db import queries

logger = logging.getLogger(__name__)

LINKEDIN_QUEUE = "linkedin_queue"
BLOG_QUEUE = "blog_queue"
YOUTUBE_QUEUE = "youtube_queue"

# How long a worker-availability answer stays good.
WORKER_MAP_TTL_SECONDS = 30.0


def is_redis_available() -> bool:
    try:
        from app.core.redis_client import sstate

        return bool(sstate().ping())
    except Exception:
        return False


class _WorkerMap:
    """Cached view of which queues have a live consumer.

    Refreshed at most once per ``WORKER_MAP_TTL_SECONDS``. A stale answer is
    acceptable — being wrong costs one queued-but-unconsumed task, which the
    job row surfaces as ``queued`` — whereas a broadcast per request costs every
    user 0.75s of latency.
    """

    def __init__(self) -> None:
        self._queues: frozenset[str] = frozenset()
        self._checked_at = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        try:
            from app.celery_app import celery_app

            active = celery_app.control.inspect(timeout=0.75).active_queues() or {}
            self._queues = frozenset(
                q.get("name")
                for worker_queues in active.values()
                for q in worker_queues
            )
        except Exception as exc:
            logger.warning("Could not inspect Celery workers: %s", exc)
            self._queues = frozenset()
        finally:
            self._checked_at = time.monotonic()

    def consuming(self, queue: str) -> bool:
        now = time.monotonic()
        if now - self._checked_at > WORKER_MAP_TTL_SECONDS:
            # Only one caller refreshes; the rest use the previous answer rather
            # than piling up concurrent broadcasts.
            if self._lock.acquire(blocking=False):
                try:
                    if time.monotonic() - self._checked_at > WORKER_MAP_TTL_SECONDS:
                        self._refresh()
                finally:
                    self._lock.release()
        return queue in self._queues


_worker_map = _WorkerMap()


def celery_worker_consuming(queue: str) -> bool:
    """True if a live Celery worker is consuming ``queue`` (cached)."""
    return _worker_map.consuming(queue)


def should_use_celery(queue: str) -> bool:
    return is_redis_available() and celery_worker_consuming(queue)


# ── Shared pipeline launcher ─────────────────────────────────────────────────

CONTENT_TYPES = ("linkedin", "blog", "youtube_script")

# content_type -> async lookup for the produced row, by run_id and owner.
CONTENT_LOOKUP = {
    "linkedin": queries.get_linkedin_posts_by_run_id,
    "blog": queries.get_blog_posts_by_run_id,
    "youtube_script": queries.get_youtube_scripts_by_run_id,
}


def _run_inprocess(task, args: list) -> None:
    """Execute a Celery task synchronously in this process.

    ``.apply()`` runs the registered task body locally, so the in-process path
    and the worker path are literally the same code.
    """
    task.apply(args=args, throw=False)


def dispatch_pipeline(content_type: str, run_id: str, topic: str, niche: str, user_id: str,
                      provider: str, video_format: str, background_tasks) -> bool:
    """Launch one content pipeline for an already-created run.

    Returns True when the work went to Celery, False when it was queued
    in-process. Owner-agnostic on purpose: the caller has already created
    whatever link row it needs (plan_item_content, saved_topic_runs, ...), so a
    new owner type never has to copy the queue names or task signatures.
    """
    # Lazy imports so a broken Celery import can never take the API down.
    from app.tasks.blog_task import run_blog_pipeline
    from app.tasks.linkedin_task import run_linkedin_pipeline
    from app.tasks.youtube_task import run_youtube_pipeline

    specs = {
        # target_keyword defaults to the topic for blogs.
        "linkedin": (run_linkedin_pipeline, LINKEDIN_QUEUE,
                     [run_id, topic, niche, user_id, provider]),
        "blog": (run_blog_pipeline, BLOG_QUEUE,
                 [run_id, topic, topic, user_id, provider]),
        "youtube_script": (run_youtube_pipeline, YOUTUBE_QUEUE,
                           [run_id, topic, niche, user_id, provider, video_format]),
    }
    task, queue, args = specs[content_type]

    if should_use_celery(queue):
        try:
            task.apply_async(args=args, queue=queue, ignore_result=True)
            return True
        except Exception as exc:
            logger.warning(
                "Celery dispatch failed for %s: %s", content_type, exc
            )

    if not get_settings().allow_inprocess_fallback:
        # Better a task that waits for a worker than one that silently occupies
        # an API worker for minutes and then times out at the proxy.
        logger.error(
            "No Celery worker for %s and in-process fallback is disabled ▸ run_id=%s",
            queue, run_id,
        )
        raise RuntimeError(
            f"No worker is consuming {queue}. Start a Celery worker for this queue."
        )

    logger.info(
        "Running %s pipeline in-process (no Celery worker) ▸ run_id=%s",
        content_type, run_id,
    )
    background_tasks.add_task(_run_inprocess, task, args)
    return False
