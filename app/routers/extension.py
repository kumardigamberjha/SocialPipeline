"""
Chrome Extension API Router.

Powers the VidIQ-like Chrome extension for YouTube creators.
Provides:
  - Extension authentication & token issuance
  - Channel profile, niche classification, and keyword clusters from user database
  - Searchable previous video catalogue from `youtube_videos_live`
  - Deep per-video recommendations (high-CTR titles, hook rewrites, thumbnail concepts,
    tag suggestions, and SEO audit) grounded in the creator's personal channel history
  - Metadata updates to YouTube Data API
"""

from __future__ import annotations

import asyncio
import collections
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.core.tokens import create_access_token, new_refresh_token, refresh_expiry
from app.db import queries
from app.db.session import get_session
from app.db.tables import RefreshToken, User
from app.services.personal_intelligence import get_directives
from app.services.youtube_metrics import (
    STOPWORDS,
    analyze_channel_keywords,
    duration_bucket,
    extract_keywords,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extension", tags=["Extension"])

_DUMMY_HASH = bcrypt.hashpw(b"invalid-password-placeholder", bcrypt.gensalt())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "is_active": user.get("is_active", True),
        "email_verified_at": user.get("email_verified_at"),
        "created_at": user.get("created_at"),
    }


# ── Auth Schemas ─────────────────────────────────────────────────────────────


class ExtensionLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ExtensionLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


# ── Recommendation Schemas ───────────────────────────────────────────────────


class VideoRecommendationRequest(BaseModel):
    video_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    tags: Optional[List[str]] = Field(default_factory=list)
    channel_title: Optional[str] = ""
    views: Optional[int] = 0
    likes: Optional[int] = 0
    comments: Optional[int] = 0
    duration_seconds: Optional[int] = 0
    refresh: bool = False


class SeoScoreRubric(BaseModel):
    total_score: int
    title_score: int
    description_score: int
    tag_score: int
    niche_alignment_score: int
    checklist: List[Dict[str, Any]]


class VideoRecommendationsResponse(BaseModel):
    video_id: Optional[str] = None
    title: str
    channel_title: str
    is_own_video: bool
    channel_niche: str
    baseline_views: int
    views_vs_baseline_multiplier: float
    seo_score: SeoScoreRubric
    verdict: str
    title_recommendations: List[str]
    hook_rewrite: str
    thumbnail_ideas: List[str]
    description_fixes: List[str]
    tag_recommendations: List[str]
    existing_tags: List[str]
    priority_actions: List[str]


class MetadataUpdateRequest(BaseModel):
    video_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category_id: Optional[str] = None


# ── Programmatic SEO Score Calculator ────────────────────────────────────────


def calculate_seo_score(
    title: str,
    description: str,
    tags: List[str],
    niche_keywords: List[str],
) -> SeoScoreRubric:
    """Calculates a comprehensive 0-100 SEO score with actionable checklist."""
    title = (title or "").strip()
    desc = (description or "").strip()
    tag_list = tags or []
    words_in_desc = len(desc.split()) if desc else 0

    checklist: List[Dict[str, Any]] = []

    # 1. Title Score (Max 25 pts)
    title_pts = 0
    title_len = len(title)
    if 35 <= title_len <= 70:
        title_pts += 12
        checklist.append({"category": "Title", "item": "Optimal title length (35-70 chars)", "passed": True, "score": 12})
    elif 20 <= title_len < 35 or 70 < title_len <= 90:
        title_pts += 7
        checklist.append({"category": "Title", "item": "Title length acceptable but could be tighter", "passed": True, "score": 7})
    else:
        checklist.append({"category": "Title", "item": "Title is too short or exceeds recommended length", "passed": False, "score": 2})
        title_pts += 2

    # Title power / question / number hook
    has_power = bool(re.search(r"(how to|why|best|guide|tutorial|review|step by step|\d+)", title, re.IGNORECASE))
    if has_power:
        title_pts += 8
        checklist.append({"category": "Title", "item": "Contains strong hook or curiosity keyword", "passed": True, "score": 8})
    else:
        checklist.append({"category": "Title", "item": "Add hook words (How-to, Why, Numbers, or Guide)", "passed": False, "score": 0})

    # Title capitalization
    if any(c.isupper() for c in title):
        title_pts += 5
        checklist.append({"category": "Title", "item": "Proper capitalization", "passed": True, "score": 5})

    # 2. Description Score (Max 25 pts)
    desc_pts = 0
    if words_in_desc >= 150:
        desc_pts += 10
        checklist.append({"category": "Description", "item": f"Rich description ({words_in_desc} words)", "passed": True, "score": 10})
    elif words_in_desc >= 50:
        desc_pts += 6
        checklist.append({"category": "Description", "item": f"Moderate description length ({words_in_desc} words)", "passed": True, "score": 6})
    else:
        checklist.append({"category": "Description", "item": "Description too short (<50 words)", "passed": False, "score": 2})
        desc_pts += 2

    has_links = bool(re.search(r"https?://", desc))
    if has_links:
        desc_pts += 5
        checklist.append({"category": "Description", "item": "Includes relevant links/resources", "passed": True, "score": 5})
    else:
        checklist.append({"category": "Description", "item": "No links or calls to action detected", "passed": False, "score": 0})

    has_timestamps = bool(re.search(r"\b\d{1,2}:\d{2}\b", desc))
    if has_timestamps:
        desc_pts += 6
        checklist.append({"category": "Description", "item": "Includes video timestamps/chapters", "passed": True, "score": 6})
    else:
        checklist.append({"category": "Description", "item": "Add timestamps (00:00) for viewer retention", "passed": False, "score": 0})

    # First lines contain title words
    first_lines = desc[:200].lower()
    title_tokens = [t.lower() for t in re.findall(r"\w+", title) if len(t) > 3 and t.lower() not in STOPWORDS]
    if any(t in first_lines for t in title_tokens):
        desc_pts += 4
        checklist.append({"category": "Description", "item": "Core keywords appear in opening lines", "passed": True, "score": 4})

    # 3. Tag Score (Max 25 pts)
    tag_pts = 0
    tag_count = len(tag_list)
    if 10 <= tag_count <= 35:
        tag_pts += 15
        checklist.append({"category": "Tags", "item": f"Good tag volume ({tag_count} tags)", "passed": True, "score": 15})
    elif 4 <= tag_count < 10:
        tag_pts += 8
        checklist.append({"category": "Tags", "item": f"Acceptable tag count ({tag_count} tags)", "passed": True, "score": 8})
    else:
        checklist.append({"category": "Tags", "item": f"Too few tags ({tag_count} tags)", "passed": False, "score": 2})
        tag_pts += 2

    long_tail_tags = [t for t in tag_list if " " in t.strip()]
    if len(long_tail_tags) >= 3:
        tag_pts += 10
        checklist.append({"category": "Tags", "item": "Includes long-tail keyword tags", "passed": True, "score": 10})
    else:
        checklist.append({"category": "Tags", "item": "Add more 2-3 word long-tail tags", "passed": False, "score": 2})
        tag_pts += 2

    # 4. Channel Niche Alignment (Max 25 pts)
    niche_pts = 0
    content_text = f"{title.lower()} {desc.lower()} {' '.join(tag_list).lower()}"
    matched_niche = [kw for kw in niche_keywords if kw.lower() in content_text]

    if len(matched_niche) >= 3:
        niche_pts += 25
        checklist.append({"category": "Niche", "item": f"Strong alignment with channel niche ({len(matched_niche)} matching keywords)", "passed": True, "score": 25})
    elif len(matched_niche) >= 1:
        niche_pts += 16
        checklist.append({"category": "Niche", "item": f"Moderate niche overlap ({len(matched_niche)} matching keywords)", "passed": True, "score": 16})
    else:
        niche_pts += 6
        checklist.append({"category": "Niche", "item": "Low overlap with your channel's core niche keywords", "passed": False, "score": 6})

    total = min(100, title_pts + desc_pts + tag_pts + niche_pts)

    return SeoScoreRubric(
        total_score=total,
        title_score=min(25, title_pts),
        description_score=min(25, desc_pts),
        tag_score=min(25, tag_pts),
        niche_alignment_score=min(25, niche_pts),
        checklist=checklist,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/auth/login", response_model=ExtensionLoginResponse, summary="Extension login")
async def extension_login(
    creds: ExtensionLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Authenticates extension with email & password, returning bearer access token."""
    user = await queries.get_user_by_email(session, creds.email.lower())

    stored_hash = user["password_hash"] if user else _DUMMY_HASH
    valid = await asyncio.to_thread(_verify_password, creds.password, stored_hash)

    if not user or not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="This account is disabled")

    # Issue token family
    cookie_value, family, token_hash = new_refresh_token(None)
    expiry = refresh_expiry()

    await session.execute(
        RefreshToken.__table__.insert().values(
            family_id=family,
            user_id=user["id"],
            token_hash=token_hash,
            parent_id=None,
            expires_at=expiry,
            user_agent="Chrome-Extension-VidIQ",
            ip=None,
        )
    )

    access_token, _, access_ttl = create_access_token(user["id"], family)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": access_ttl,
        "user": _public_user(user),
    }


@router.get("/auth/me", summary="Check authenticated user profile")
async def extension_me(
    current_user: dict = Depends(get_current_user),
) -> dict:
    return {"user": _public_user(current_user)}


@router.get("/channel-profile", summary="Get channel niche, stats, and baseline from database")
async def get_channel_profile(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Returns the logged-in user's channel summary, niche keywords, and baseline metrics."""
    user_id = current_user["id"]

    # Query all user videos from youtube_videos_live
    rows = (
        await session.execute(
            text(
                """
                SELECT video_id, title, views, likes, comments, duration_seconds,
                       published_at, thumbnail_url, channel_title, channel_id,
                       seo_title_score, tags, description, watch_time_hours,
                       subscribers_gained, average_view_percentage, impressions_ctr
                FROM youtube_videos_live
                WHERE user_id = :user_id
                ORDER BY views DESC
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()

    videos = [dict(r) for r in rows]
    total_videos = len(videos)

    if not videos:
        # Check if legacy published videos exist
        legacy_rows = (
            await session.execute(
                text(
                    """
                    SELECT video_id, title, views, duration_seconds,
                           publish_time as published_at, tags, channel_title
                    FROM youtube_published_videos
                    WHERE user_id = :user_id
                    ORDER BY views DESC
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().all()
        videos = [dict(r) for r in legacy_rows]
        total_videos = len(videos)

    total_views = sum(int(v.get("views") or 0) for v in videos)
    total_watch_hours = sum(float(v.get("watch_time_hours") or 0.0) for v in videos)
    total_subs = sum(int(v.get("subscribers_gained") or 0) for v in videos)
    baseline_views = int(total_views / max(1, total_videos))

    channel_title = next((v.get("channel_title") for v in videos if v.get("channel_title")), "My Channel")
    channel_id = next((v.get("channel_id") for v in videos if v.get("channel_id")), "")

    titles = [v.get("title", "") for v in videos if v.get("title")]
    top_keywords = extract_keywords(titles, n=12, channel_title=channel_title)
    keyword_analysis = analyze_channel_keywords(videos, float(baseline_views), channel_title)

    # Derive channel niche
    niche_label = "General / Multi-topic"
    if top_keywords:
        niche_label = " / ".join([kw.title() for kw in top_keywords[:3]])

    # Fetch creator directives
    directives_text = await get_directives(session, user_id, scope="youtube")

    # Format top benchmark videos
    top_benchmarks = [
        {
            "video_id": v.get("video_id"),
            "title": v.get("title"),
            "views": v.get("views"),
            "published_at": str(v.get("published_at")),
            "thumbnail_url": v.get("thumbnail_url"),
            "seo_title_score": v.get("seo_title_score", 0),
        }
        for v in videos[:5]
    ]

    return {
        "channel_title": channel_title,
        "channel_id": channel_id,
        "niche": niche_label,
        "total_videos": total_videos,
        "total_views": total_views,
        "total_watch_hours": round(total_watch_hours, 1),
        "total_subscribers_gained": total_subs,
        "baseline_views": baseline_views,
        "top_keywords": top_keywords,
        "keyword_clusters": keyword_analysis.get("top_keywords", [])[:8],
        "directives": directives_text,
        "top_benchmarks": top_benchmarks,
    }


@router.get("/videos", summary="Browse synced previous videos from user database")
async def list_channel_videos(
    limit: int = 30,
    offset: int = 0,
    search: str = "",
    sort_by: str = "views",
    order: str = "desc",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lists previous videos from user database with performance metrics and SEO scores."""
    user_id = current_user["id"]
    valid_sorts = {"views", "published_at", "likes", "comments", "seo_title_score", "duration_seconds"}
    if sort_by not in valid_sorts:
        sort_by = "views"
    order_sql = "ASC" if order.lower() == "asc" else "DESC"

    where_clauses = ["user_id = :user_id"]
    params: dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}

    if search.strip():
        where_clauses.append("(title ILIKE :search OR tags::text ILIKE :search)")
        params["search"] = f"%{search.strip()}%"

    where_sql = "WHERE " + " AND ".join(where_clauses)

    count_row = (
        await session.execute(
            text(f"SELECT COUNT(*) AS cnt FROM youtube_videos_live {where_sql}"), params
        )
    ).mappings().first()
    total = count_row["cnt"] if count_row else 0

    rows = (
        await session.execute(
            text(
                f"""
                SELECT video_id, title, description, tags, category_id,
                       duration_seconds, published_at, thumbnail_url,
                       views, likes, comments, channel_id, channel_title,
                       seo_title_score, seo_tag_count, seo_desc_words,
                       privacy_status, impressions, impressions_ctr,
                       average_view_percentage, watch_time_hours
                FROM youtube_videos_live
                {where_sql}
                ORDER BY {sort_by} {order_sql}
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    videos = [dict(r) for r in rows]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "videos": videos,
    }


@router.post("/video-recommendations", response_model=VideoRecommendationsResponse, summary="Per-video recommendations")
async def get_video_recommendations(
    payload: VideoRecommendationRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Computes SEO score and AI recommendations for ANY video (watched or owned).
    Grounded in the logged-in creator's channel niche, top keywords, and previous video database.
    """
    user_id = current_user["id"]

    # 1. Fetch channel context and previous video history
    channel_res = await get_channel_profile(current_user=current_user, session=session)
    niche = channel_res.get("niche") or "General"
    top_keywords = channel_res.get("top_keywords") or []
    baseline_views = channel_res.get("baseline_views") or 1000

    # 2. Check if video exists in user's database
    is_own_video = False
    existing_video = None
    if payload.video_id:
        row = (
            await session.execute(
                text(
                    "SELECT * FROM youtube_videos_live WHERE user_id = :user_id AND video_id = :video_id"
                ),
                {"user_id": user_id, "video_id": payload.video_id},
            )
        ).mappings().first()
        if row:
            is_own_video = True
            existing_video = dict(row)

    title = (existing_video.get("title") if existing_video else payload.title) or "Untitled Video"
    description = (existing_video.get("description") if existing_video else payload.description) or ""
    tags = (existing_video.get("tags") if existing_video and existing_video.get("tags") else payload.tags) or []
    if isinstance(tags, str):
        import json
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [t.strip() for t in tags.split(",") if t.strip()]

    views = existing_video.get("views", payload.views or 0) if existing_video else (payload.views or 0)
    channel_name = existing_video.get("channel_title", payload.channel_title) if existing_video else (payload.channel_title or channel_res.get("channel_title", ""))

    multiplier = round(float(views) / max(1.0, float(baseline_views)), 2)

    # 3. Calculate Programmatic SEO Score
    seo_score = calculate_seo_score(title, description, tags, top_keywords)

    # 4. Generate AI Recommendations grounded in channel database
    from app.services.youtube_ai_analysis import analyze_video_growth

    video_context = (
        f"TITLE: {title}\n"
        f"CHANNEL: {channel_name} (Logged-in Channel: {channel_res.get('channel_title')})\n"
        f"IS_CREATOR_OWN_VIDEO: {is_own_video}\n"
        f"CHANNEL_NICHE: {niche}\n"
        f"CHANNEL_TOP_KEYWORDS: {', '.join(top_keywords)}\n"
        f"CHANNEL_BASELINE_VIEWS: {baseline_views:,}\n"
        f"THIS_VIDEO_VIEWS: {views:,} ({multiplier}x channel average)\n"
        f"SEO_SCORE: {seo_score.total_score}/100 (Title: {seo_score.title_score}/25, Desc: {seo_score.description_score}/25, Tags: {seo_score.tag_score}/25, Niche: {seo_score.niche_alignment_score}/25)\n"
        f"TAGS: {', '.join(tags) if tags else '(none)'}\n"
        f"DESCRIPTION: {description[:500]}"
    )

    directives = channel_res.get("directives", "")

    try:
        growth_result = await analyze_video_growth(
            video_context=video_context,
            web_context="",
            directives=directives,
        )
    except Exception as exc:
        logger.warning("AI video growth analysis fallback: %s", exc)
        # Graceful fallback if LLM has high latency/offline
        growth_result = {
            "verdict": f"Video scored {seo_score.total_score}/100 with {multiplier}x channel baseline views. Title and niche alignment provide the highest immediate growth opportunity.",
            "title_options": [
                f"{title.split('|')[0].strip()}: Complete {niche.split('/')[0].strip()} Guide",
                f"How I Mastered {top_keywords[0].title() if top_keywords else 'This'} (Step-by-Step)",
                f"The Truth About {title.split(':')[0].strip()} in 2026",
            ],
            "thumbnail_ideas": [
                "Split screen showing before/after contrast with high-visibility bold yellow text hook (2-3 words)",
                "Close-up expressive reaction pointing to key UI/code chart with clean drop shadow",
                "Minimalist high-contrast dark theme graphic with bright accent neon element",
            ],
            "hook_rewrite": f"In this video, you're going to learn the exact method to solve {top_keywords[0] if top_keywords else 'this challenge'} without making the common mistake 90% of creators make.",
            "description_fixes": [
                "Place your primary keyword and a 2-sentence summary in the first 2 lines before the fold",
                "Add timestamp chapters (00:00 Intro, 01:30 Core Strategy, 05:00 Practical Walkthrough)",
                "Add 2-3 links to relevant playlists and resources to increase watch session time",
            ],
            "tag_fixes": [
                f"Add primary niche tag: {top_keywords[0] if top_keywords else 'tutorial'}",
                f"Add long-tail tag: {title.lower()[:30]}",
                "Remove redundant single-word tags that dilute search relevance",
            ],
            "priority_actions": [
                "Rewrite title to stay within 45-65 characters with an active curiosity hook",
                "Update thumbnail text overlay to 3 words maximum with 80%+ contrast ratio",
                "Paste recommended tag cluster into video metadata",
            ],
        }

    # Format recommended tags by combining AI fixes + channel niche keywords
    suggested_tags = list(dict.fromkeys(
        [t for t in tags] +
        [kw for kw in top_keywords[:6]] +
        [f"{niche.split('/')[0].strip().lower()} tutorial", f"{top_keywords[0] if top_keywords else 'youtube'} 2026"]
    ))[:25]

    return VideoRecommendationsResponse(
        video_id=payload.video_id,
        title=title,
        channel_title=channel_name,
        is_own_video=is_own_video,
        channel_niche=niche,
        baseline_views=baseline_views,
        views_vs_baseline_multiplier=multiplier,
        seo_score=seo_score,
        verdict=growth_result.get("verdict", ""),
        title_recommendations=growth_result.get("title_options", []),
        hook_rewrite=growth_result.get("hook_rewrite", ""),
        thumbnail_ideas=growth_result.get("thumbnail_ideas", []),
        description_fixes=growth_result.get("description_fixes", []),
        tag_recommendations=suggested_tags,
        existing_tags=tags,
        priority_actions=growth_result.get("priority_actions", []),
    )


@router.post("/update-metadata", summary="1-click update video title, description, or tags on YouTube")
async def update_metadata(
    payload: MetadataUpdateRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Updates video title/description/tags on YouTube Data API if connected."""
    from app.services.google_calendar import NotConnectedError
    from app.services.youtube_sync_service import (
        YoutubeApiDisabled,
        YoutubeScopeMissing,
        YoutubeSyncError,
        update_video_metadata,
    )

    user_id = current_user["id"]
    try:
        result = await asyncio.to_thread(
            update_video_metadata,
            user_id=user_id,
            video_id=payload.video_id,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            category_id=payload.category_id,
        )
    except NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=f"Google account not connected: {exc}")
    except YoutubeScopeMissing as exc:
        raise HTTPException(status_code=403, detail=f"YouTube permissions missing: {exc}")
    except YoutubeApiDisabled as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YoutubeSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return result
