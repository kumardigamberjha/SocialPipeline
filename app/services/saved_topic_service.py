"""
Saved ("uncovered") topic domain logic.

An auto-research run asks the suggester for a handful of candidate topics,
generates the first one immediately, and parks the rest here as a backlog the
user can come back to.

Reconciliation design
---------------------
Mirrors plan_service: saved_topic_runs rows are created with
review_status='generating' and a run_id, and the pipelines know nothing about
saved topics. Whenever a topic is read, reconcile_saved_topic() checks each
'generating' row against its run — on 'completed' it links the produced content
row and marks 'ready', on 'failed' it marks 'failed' — then derives the owning
topic's status from the aggregate. A topic whose every attempt failed falls back
to 'uncovered' so it can be retried.
"""

import logging
from datetime import date

from fastapi import BackgroundTasks, HTTPException

from app.db import queries
from app.services.dispatch import CONTENT_LOOKUP, CONTENT_TYPES, dispatch_pipeline
from app.services.plan_service import _remaining_quota

logger = logging.getLogger(__name__)

# How many candidates an auto-research run asks for: one to generate now, the
# rest to park as backlog.
CANDIDATE_COUNT = 5


# ── Candidate research ───────────────────────────────────────────────────────


async def research_candidates(user_id: str, provider: str, niche: str) -> list[dict]:
    """Ask the suggester for CANDIDATE_COUNT ideas.

    Returns [{topic, rationale, ...}]. Raises on failure — the caller decides
    whether to fall back, since auto-research must still work without this.
    """
    from app.services.topic_suggester import suggest_topics

    # plan_type/start_date only exist to satisfy the planner-shaped signature;
    # count overrides the weekly default and the returned scheduled_date is
    # discarded — saved topics have no calendar slot.
    candidates = await suggest_topics(
        user_id=user_id,
        plan_type="weekly",
        niche=niche,
        start_date=date.today(),
        count=CANDIDATE_COUNT,
        provider=provider,
        extra_recent=queries.get_uncovered_topic_titles(user_id),
    )
    if not candidates:
        raise RuntimeError("Suggester returned no candidate topics")
    return candidates


def save_candidates(user_id: str, candidates: list[dict], niche: str,
                    source_run_id: str = None) -> int:
    """Persist candidates as 'uncovered'. Returns how many were actually new
    (create_saved_topic returns None for ones already in the backlog)."""
    saved = 0
    for candidate in candidates:
        topic = (candidate.get("topic") or "").strip()
        if not topic:
            continue
        row = queries.create_saved_topic(
            user_id=user_id,
            topic=topic,
            rationale=candidate.get("rationale"),
            niche=niche,
            source="auto_research",
            source_run_id=source_run_id,
        )
        if row:
            saved += 1
    logger.info("Saved %d/%d candidate topics as uncovered", saved, len(candidates))
    return saved


# ── Reconciliation ───────────────────────────────────────────────────────────


def reconcile_saved_topic_run(row: dict) -> dict:
    """Advance a 'generating' saved_topic_runs row from its run's terminal
    state. The saved-topic twin of reconcile_plan_item_content()."""
    if row["review_status"] != "generating" or not row.get("run_id"):
        return row

    run = queries.get_run_by_id(row["run_id"])
    if not run or run["status"] in ("pending", "running"):
        return row

    if run["status"] == "failed":
        queries.update_saved_topic_run(row["id"], review_status="failed")
        row["review_status"] = "failed"
        return row

    rows = CONTENT_LOOKUP[row["content_type"]](row["run_id"])
    if not rows:
        # Completed run but no saved row (should not happen) — surface as failed.
        queries.update_saved_topic_run(row["id"], review_status="failed")
        row["review_status"] = "failed"
        return row

    ref_id = rows[-1]["id"]
    queries.update_saved_topic_run(row["id"], content_ref_id=ref_id, review_status="ready")
    row["content_ref_id"] = ref_id
    row["review_status"] = "ready"
    return row


def _derive_status(runs: list[dict]) -> str:
    """Topic status from the aggregate of its attempts."""
    if not runs:
        return "uncovered"
    statuses = {r["review_status"] for r in runs}
    if "ready" in statuses or "approved" in statuses:
        return "generated"
    if "generating" in statuses:
        return "generating"
    return "uncovered"  # every attempt failed — let the user retry


def reconcile_saved_topic(topic: dict, user_id: str) -> dict:
    """Reconcile a topic's runs and sync its own status. Returns the topic with
    a `runs` key attached."""
    runs = [reconcile_saved_topic_run(r) for r in queries.get_saved_topic_runs(topic["id"], user_id)]
    topic["runs"] = runs

    derived = _derive_status(runs)
    if derived != topic["status"]:
        queries.update_saved_topic(topic["id"], user_id, status=derived)
        topic["status"] = derived
        if derived == "generated" and not topic.get("generated_at"):
            refreshed = queries.get_saved_topic_by_id(topic["id"], user_id)
            if refreshed:
                topic["generated_at"] = refreshed["generated_at"]
    return topic


def list_topics_reconciled(user_id: str, status: str = None,
                           include_dismissed: bool = False) -> list[dict]:
    """List topics with their runs reconciled.

    Reconciles against the unfiltered set first, then applies the status filter,
    so a topic that just finished generating is filtered on its *new* status
    rather than the stale one.
    """
    topics = [
        reconcile_saved_topic(t, user_id)
        for t in queries.get_saved_topics(user_id, status=None, include_dismissed=include_dismissed)
    ]
    if status:
        topics = [t for t in topics if t["status"] == status]
    return topics


# ── Generation dispatch ──────────────────────────────────────────────────────


def dispatch_saved_topic_generation(topic: dict, content_type: str, provider: str,
                                    background_tasks: BackgroundTasks) -> list[dict]:
    """Dispatch one content type or all three for a saved topic.

    Gates on remaining quota upfront using the planner's accounting, so a saved
    topic and a plan item are metered identically.
    """
    types = list(CONTENT_TYPES) if content_type == "all" else [content_type]
    user_id = topic["user_id"]

    remaining = _remaining_quota(user_id)
    if remaining < len(types):
        raise HTTPException(
            status_code=429,
            detail=f"Not enough runs left this month: need {len(types)}, have {remaining}. Nothing was dispatched.",
        )

    dispatched = []
    for ct in types:
        run = queries.create_run(user_id, topic["topic"], provider)
        run_id = run["id"]
        link = queries.create_saved_topic_run(topic["id"], user_id, ct, run_id)
        dispatch_pipeline(
            content_type=ct,
            run_id=run_id,
            topic=topic["topic"],
            niche=topic.get("niche") or "ai",
            user_id=user_id,
            provider=provider,
            video_format="full",
            background_tasks=background_tasks,
        )
        dispatched.append({"content_type": ct, "run_id": run_id, "content_id": link["id"]})

    # Eager, so the topic leaves the backlog banner the moment Generate is
    # clicked rather than on the next reconcile.
    queries.update_saved_topic(topic["id"], user_id, status="generating")
    return dispatched
