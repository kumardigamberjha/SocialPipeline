"""
Instagram Analytics Router for FastAPI.

Data Strategy:
  - Page loads → Redis cache (25h TTL) → Postgres snapshot → empty state
  - The Graph API is NEVER called on page load; only by the nightly Celery
    task or a manual "Sync Now"
  - Manual refresh via POST /api/instagram-analytics/sync

Every endpoint here now requires authentication and reads/writes the caller's
own cached data. Previously **none** of these 11 endpoints declared a
dependency at all — anyone could read the connected account's analytics or
trigger a Graph API sync against Meta's rate limit.

The Instagram token is per-user, Fernet-encrypted in ``instagram_oauth_tokens``
(see ``app.services.instagram_auth``) — each caller's sync/strategy calls only
ever touch their own connected account.
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session
from app.services import instagram_ai_analysis, instagram_auth, roadmap_to_plan
from app.services.instagram_cache import get_cached_instagram_data, refresh_instagram_cache
from app.services.personal_intelligence import get_directives

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram-analytics", tags=["Instagram Analytics"])

# Content planning for this account lives in the unified planner as plan_items
# with this platform; the Kanban that used to sit on this page was a second UI
# over the very same rows (migration 0006, dropped in 0007).
PLATFORM = "instagram"


def _get_cached(user_id: str) -> Dict[str, Any]:
    """Returns this user's cached data, or an empty structure if none exists yet."""
    cached = get_cached_instagram_data(user_id)
    if cached:
        return cached
    return {"profile": None, "stats": None, "posts": [], "hashtags": [], "synced_at": None, "source": "none"}


class RoadmapItemIn(BaseModel):
    """One roadmap card, as the dashboard renders it."""

    title: str
    type: str = "reel"                      # reel | carousel | single | story
    date: Optional[str] = None              # the roadmap's own suggested date
    caption: Optional[str] = ""
    image_prompt: Optional[str] = ""
    rationale: Optional[str] = ""
    week_number: Optional[int] = None


class RoadmapAddToPlanBody(BaseModel):
    items: List[RoadmapItemIn]
    # Append into an existing plan, or create a new one when omitted.
    plan_id: Optional[str] = None
    plan_name: Optional[str] = None


@router.get("/profile")
def get_instagram_profile(user: dict = Depends(get_current_user)):
    """Serves profile from Redis/DB cache. No live API call on page load."""
    data = _get_cached(user["id"])
    if data["profile"]:
        return {**data["profile"], "synced_at": data.get("synced_at"), "source": data.get("source")}

    connected = instagram_auth.connection_status(user["id"])["connected"]
    return {
        "handle": None,
        "brand_name": "Not synced yet" if connected else "Not connected",
        "url": None,
        "bio": (
            "⏳ Instagram data not synced yet. Click 'Sync Now' or wait for tonight's 12:10 AM refresh."
            if connected
            else "Connect your Instagram account to see analytics."
        ),
        "followers": 0,
        "following": 0,
        "total_posts": 0,
        "avg_engagement_rate": 0.0,
        "monthly_reach": 0,
        "monthly_impressions": 0,
        "synced_at": None,
        "source": "none"
    }


@router.get("/stats")
def get_instagram_stats(time_range: str = "30_days", user: dict = Depends(get_current_user)):
    """Serves stats from Redis/DB cache."""
    data = _get_cached(user["id"])
    if data["stats"]:
        return {**data["stats"], "time_range": time_range, "synced_at": data.get("synced_at"), "source": data.get("source")}
    return {
        "time_range": time_range,
        "total_followers": 0,
        "followers_gained": 0,
        "total_reach": 0,
        "total_impressions": 0,
        "accounts_engaged": 0,
        "profile_visits": 0,
        "link_clicks": 0,
        "total_reels_published": 0,
        "total_carousels_published": 0,
        "avg_reel_views": 0,
        "avg_carousel_saves": 0,
        "synced_at": None,
        "source": "none"
    }


@router.get("/posts")
def get_instagram_posts(
    limit: int = 10, format_filter: str = "all", user: dict = Depends(get_current_user)
):
    """Serves posts from Redis/DB cache."""
    data = _get_cached(user["id"])
    all_posts = data.get("posts", [])
    if format_filter != "all":
        all_posts = [p for p in all_posts if p.get("type") == format_filter]
    return all_posts[:limit]


@router.get("/hashtags")
def get_hashtag_analytics(user: dict = Depends(get_current_user)):
    """Serves hashtag data from Redis/DB cache."""
    return _get_cached(user["id"]).get("hashtags", [])


@router.post("/sync")
def manual_sync(user: dict = Depends(get_current_user)):
    """
    Manually triggers a fresh Instagram API fetch and updates the cache.
    Use sparingly — this counts against Meta API rate limits.
    The nightly Celery task at 12:10 AM IST handles this automatically.
    """
    if not instagram_auth.connection_status(user["id"])["connected"]:
        raise HTTPException(
            status_code=400,
            detail="No Instagram token connected. Please complete OAuth first."
        )
    try:
        data = refresh_instagram_cache(user["id"])
        return {
            "status": "success",
            "message": "Instagram data synced.",
            "handle": data.get("profile", {}).get("handle"),
            "posts_count": len(data.get("posts", [])),
            "synced_at": data.get("synced_at"),
        }
    except Exception as e:
        logger.error("Manual Instagram sync failed for %s: %s", user["id"], e)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


# ── Saved AI reports ──────────────────────────────────────────────────────────
#
# Every generated strategy/roadmap is already persisted to instagram_ai_reports.
# These endpoints expose the accumulated history so the UI can show past runs
# instead of only the newest one. Mirrors /api/youtube-analytics/analyses*.


async def _save_report(
    session: AsyncSession, user_id: str, report_type: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Persist a freshly generated report, stamping its id onto the response."""
    try:
        row = await queries.save_instagram_ai_report(session, user_id, report_type, result)
    except Exception:  # never fail a good report because the save broke
        logger.exception("Could not save Instagram %s report", report_type)
        return result
    result["report_id"] = row["id"]
    result["created_at"] = row["created_at"]
    return result


@router.get("/reports")
async def list_ai_reports(
    report_type: str = None, limit: int = 20,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    """Past report runs, newest first — metadata only (no payload)."""
    return await queries.list_instagram_ai_reports(
        session, user["id"], report_type=report_type, limit=max(1, min(limit, 100))
    )


@router.get("/reports/{report_id}")
async def get_ai_report(
    report_id: str, user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    row = await queries.get_instagram_ai_report_by_id(session, report_id, user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return row


@router.delete("/reports/{report_id}")
async def delete_ai_report(
    report_id: str, user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, str]:
    if not await queries.delete_instagram_ai_report(session, report_id, user["id"]):
        raise HTTPException(status_code=404, detail="Report not found")
    return {"message": "Report deleted"}


@router.get("/strategy")
async def get_saved_instagram_strategy(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The most recently generated Strategy Brief, if any — survives a page refresh."""
    saved = await queries.get_latest_instagram_ai_report(session, user["id"], "strategy")
    if not saved:
        return {
            "brand": None,
            "time_range": None,
            "executive_summary": "",
            "top_performing_formats": [],
            "viral_reel_hooks": [],
            "content_pillar_distribution": {},
        }
    return saved["payload"]


@router.post("/strategy")
async def get_instagram_strategy(
    time_range: str = "30_days",
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """AI Content Strategy & Reel Hooks Brief, grounded in this user's real synced Instagram data."""
    cached = _get_cached(user["id"])
    profile = cached.get("profile") or {}
    handle = profile.get("handle") or "your account"

    if not cached.get("profile") and not cached.get("posts"):
        return {
            "brand": handle,
            "time_range": time_range,
            "executive_summary": "No Instagram data synced yet. Click 'Sync Now' above, or connect your account, then generate a strategy brief grounded in your real performance.",
            "top_performing_formats": [],
            "viral_reel_hooks": [],
            "content_pillar_distribution": {},
        }

    existing = await queries.get_plan_items_by_platform(session, user["id"], "instagram")
    context = instagram_ai_analysis.build_account_context(cached, existing)


    directives = await get_directives(session, user["id"], scope="instagram")
    try:
        result = await instagram_ai_analysis.analyze_strategy(
            context, time_range=time_range, directives=directives
        )
    except Exception as exc:
        logger.error("Instagram AI strategy failed for %s: %s", user["id"], exc)
        raise HTTPException(status_code=502, detail=f"AI strategy generation failed: {exc}")

    result["brand"] = handle
    result["time_range"] = time_range
    return await _save_report(session, user["id"], "strategy", result)


@router.get("/roadmap")
async def get_saved_instagram_roadmap(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The most recently generated Content Roadmap, if any — survives a page refresh."""
    saved = await queries.get_latest_instagram_ai_report(session, user["id"], "roadmap")
    if not saved:
        return {"weeks": []}
    return saved["payload"]


@router.post("/roadmap")
async def get_instagram_roadmap(
    weeks: int = 4,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Generates a multi-week Instagram Content Roadmap grounded in this user's real synced data."""
    cached = _get_cached(user["id"])
    if not cached.get("profile") and not cached.get("posts"):
        return {"weeks": []}

    weeks = min(max(weeks, 1), 8)
    existing = await queries.get_plan_items_by_platform(session, user["id"], "instagram")
    context = instagram_ai_analysis.build_account_context(cached, existing)


    directives = await get_directives(session, user["id"], scope="instagram")
    try:
        result = await instagram_ai_analysis.generate_content_roadmap(
            context, weeks=weeks, directives=directives
        )
    except Exception as exc:
        logger.error("Instagram AI roadmap failed for %s: %s", user["id"], exc)
        raise HTTPException(status_code=502, detail=f"AI roadmap generation failed: {exc}")

    start_date = date.today()
    roadmap_weeks = []
    for w, week in enumerate(result.get("weeks", [])[:weeks]):
        w_start = start_date + timedelta(days=w * 7)
        items = []
        for i, item in enumerate(week.get("items", [])):
            item_date = w_start + timedelta(days=i * 3 + 1)
            items.append({
                "date": item_date.isoformat(),
                "title": item.get("title", ""),
                "type": item.get("type", "reel"),
                "tags": item.get("tags", ""),
                "call_to_action": item.get("call_to_action", ""),
                "visual_prompt": item.get("visual_prompt", ""),
            })
        roadmap_weeks.append({
            "week_number": w + 1,
            "start_date": w_start.isoformat(),
            "theme": week.get("theme") or f"Week {w + 1}",
            "items": items,
        })

    payload = {"weeks": roadmap_weeks}
    payload = await _save_report(session, user["id"], "roadmap", payload)
    return payload


@router.post("/roadmap/add-to-plan")
async def add_roadmap_to_plan(
    body: RoadmapAddToPlanBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Schedule roadmap items into the content planner.

    The mirror of YouTube's /roadmap/add-to-plan, and deliberately the same
    machinery: items already planned or already published are skipped rather
    than duplicated, so re-running the roadmap is safe. The previous version of
    this endpoint bulk-inserted with no dedupe at all.

    ``strategic=False`` because roadmap_to_plan's weekday profile is derived
    from YouTube publish history; Instagram keeps the roadmap's own dates and
    gets only collision-avoidance and deduplication.
    """
    if not body.items:
        raise HTTPException(status_code=400, detail="No items to add.")

    user_id = user["id"]

    if body.plan_id:
        plan = await queries.get_content_plan_by_id(session, body.plan_id, user_id)
        if not plan or plan.get("platform") != PLATFORM:
            raise HTTPException(status_code=404, detail="Plan not found")
        existing = await queries.get_plan_items(session, plan["id"], user_id)
    else:
        plan, existing = None, []

    raw_items = [item.model_dump() for item in body.items]

    # schedule_items() reads through a *sync* session, so keep it off the loop.
    scheduled, skipped, profile = await asyncio.to_thread(
        roadmap_to_plan.schedule_items, user_id, raw_items, existing, False,
        None, "Instagram",
    )

    if not scheduled:
        return {
            "plan_id": plan["id"] if plan else None,
            "created": [],
            "skipped": skipped,
            "profile": profile,
        }

    if plan is None:
        dates = sorted(item["publish_date"] for item in scheduled)
        plan = await queries.create_content_plan(
            session,
            user_id,
            body.plan_name or f"Instagram roadmap — {date.today().isoformat()}",
            "monthly",
            "ai",
            min(item["scheduled_date"] for item in scheduled),
            dates[-1],
            platform=PLATFORM,
        )

    # Carry the Instagram-specific fields the scheduler does not know about.
    by_topic = {item["title"]: item for item in raw_items}
    created = []
    for item in scheduled:
        source = by_topic.get(item["topic"], {})
        created.append(
            await queries.create_plan_item(
                session,
                plan["id"],
                user_id,
                platform=PLATFORM,
                meta={
                    "type": source.get("type") or "reel",
                    "caption": source.get("caption") or "",
                    "image_prompt": source.get("image_prompt") or "",
                    "source": "roadmap",
                },
                **{k: v for k, v in item.items() if k != "video_format"},
            )
        )

    return {
        "plan_id": plan["id"],
        "created": created,
        "skipped": skipped,
        "profile": profile,
    }
