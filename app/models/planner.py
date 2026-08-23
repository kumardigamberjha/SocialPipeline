"""Pydantic request/response models for the content planner."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# 'board' is the open-ended Kanban plan a platform gets by default; it has no
# weekly/monthly date arithmetic. Kept as a CHECK in the DB because the routers
# branch on it, unlike Platform below.
PlanType = Literal["weekly", "monthly", "board"]

# The channel a plan and its items belong to. Deliberately NOT a DB CHECK
# constraint (see ContentPlan.platform): adding a platform should cost one entry
# here and one dropdown entry in the UI, never a migration.
Platform = Literal["youtube", "instagram", "linkedin", "blog", "x", "tiktok"]
ContentType = Literal["linkedin", "blog", "youtube_script"]
GenerateType = Literal["linkedin", "blog", "youtube_script", "all"]
VideoFormat = Literal["short", "full"]

# 24-hour 'HH:MM' local time for the calendar reminder.
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# Video production pipeline stages. 'script_generated' is set automatically when
# a youtube_script generation completes; the rest are advanced manually.
VIDEO_PRODUCTION_STATUSES = (
    "pending",
    "script_generated",
    "presentation_created",
    "video_created",
    "video_edited",
    "video_published",
)

# Every other platform runs a plain four-column board. These are stored verbatim
# rather than mapped onto the video stages: 'in_production' is not
# 'video_created', and pretending otherwise would make the analytics funnel lie.
GENERIC_PRODUCTION_STATUSES = ("idea", "in_production", "scheduled", "published")

ProductionStatus = Literal[
    "pending",
    "script_generated",
    "presentation_created",
    "video_created",
    "video_edited",
    "video_published",
    "idea",
    "in_production",
    "scheduled",
    "published",
]

# Platforms that run the full video pipeline. The single switch point for
# "which status vocabulary does this platform use".
VIDEO_PLATFORMS = frozenset({"youtube"})

# Platforms the content-generation pipeline can actually produce for. An
# Instagram item has no valid ContentType, so generating for one would burn a
# quota unit writing a YouTube script for a carousel.
GENERATION_PLATFORMS = frozenset({"youtube", "linkedin", "blog"})

# Platforms whose items can have a graphic rendered for them. Deliberately
# separate from GENERATION_PLATFORMS: an image is a Gemini render, not a
# ContentType, so it has no run, no quota unit and no review flow.
IMAGE_PLATFORMS = frozenset({"instagram"})


def status_order(platform: str) -> tuple[str, ...]:
    """The Kanban column order for a platform."""
    return (
        VIDEO_PRODUCTION_STATUSES
        if platform in VIDEO_PLATFORMS
        else GENERIC_PRODUCTION_STATUSES
    )


def default_status(platform: str) -> str:
    """The status a newly created item starts in."""
    return "pending" if platform in VIDEO_PLATFORMS else "idea"


# Statuses that mean "this is out the door", across both vocabularies.
PUBLISHED_STATUSES = ("video_published", "published")

ReviewStatus = Literal["generating", "ready", "approved", "rejected", "failed"]


# ── Requests ─────────────────────────────────────────────────────────────────


class PlanItemIn(BaseModel):
    topic: str
    # Optional: a backlog idea is legitimately undated.
    scheduled_date: Optional[date] = None
    publish_date: Optional[date] = None
    event_time: Optional[str] = Field(default=None, pattern=TIME_PATTERN)
    event_duration_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    notes: Optional[str] = None
    topic_source: Literal["ai", "manual"] = "manual"
    video_format: VideoFormat = "full"
    production_status: Optional[ProductionStatus] = None
    # Platform-specific fields (caption, image_prompt, slides_count, metrics …).
    meta: dict = Field(default_factory=dict)


class PlanCreateRequest(BaseModel):
    name: str
    plan_type: PlanType
    niche: str = "ai"
    start_date: date
    platform: Platform = "youtube"
    items: list[PlanItemIn] = Field(default_factory=list)


class PlanUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[Literal["active", "archived"]] = None


class PlanItemUpdate(BaseModel):
    topic: Optional[str] = None
    scheduled_date: Optional[date] = None
    publish_date: Optional[date] = None
    event_time: Optional[str] = Field(default=None, pattern=TIME_PATTERN)
    event_duration_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    notes: Optional[str] = None
    production_status: Optional[ProductionStatus] = None
    video_format: Optional[VideoFormat] = None
    # Shallow-merged into the stored meta; omitted keys are left alone.
    meta: Optional[dict] = None


class SuggestTopicsRequest(BaseModel):
    plan_type: PlanType
    niche: str = "ai"
    start_date: date
    count: Optional[int] = Field(default=None, ge=1, le=31)
    provider: Optional[str] = None
    # Picks the grounding and the prompt: YouTube's channel-history suggester,
    # or Instagram's account-data idea generator.
    platform: Platform = "youtube"


class GenerateImageRequest(BaseModel):
    """Overrides for one render; every field falls back to the item's own meta."""

    prompt: Optional[str] = None
    palette: str = "void_purple"
    layout: str = "bottom_hero"
    # Gemini image model alias. Not a raw model id on purpose: the field is
    # user-supplied, and an open string would let a caller bill us against any
    # model on the account. None falls back to settings.gemini_image_model.
    model: Optional[Literal["gemini_flash", "gemini_flash_lite", "gemini_pro"]] = None


class GenerateContentRequest(BaseModel):
    content_type: GenerateType
    provider: str = "nvidia"


class ReviewActionRequest(BaseModel):
    action: Literal["approve", "reject"]
    regenerate: bool = False
    provider: Optional[str] = None


class CalendarAddRequest(BaseModel):
    reminders_minutes: list[int] = Field(default_factory=lambda: [1440, 60])
    # Time of day for the event; falls back to the item's stored time, then 09:00.
    event_time: Optional[str] = Field(default=None, pattern=TIME_PATTERN)
    # Event length in minutes; falls back to the item's stored duration, then 60.
    event_duration_minutes: Optional[int] = Field(default=None, ge=5, le=1440)


# ── Responses (dicts from queries.py pass through FastAPI's jsonable encoder;
#    these models document the shapes the frontend relies on) ─────────────────


class SuggestedTopic(BaseModel):
    topic: str
    rationale: str = ""
    scheduled_date: str
    # Platform-specific extras to carry into plan_items.meta (Instagram's
    # type / caption / image_prompt); empty for YouTube.
    meta: dict = Field(default_factory=dict)


class SuggestTopicsResponse(BaseModel):
    topics: list[SuggestedTopic]
