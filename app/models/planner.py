"""Pydantic request/response models for the content planner."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

PlanType = Literal["weekly", "monthly"]
ContentType = Literal["linkedin", "blog", "youtube_script"]
GenerateType = Literal["linkedin", "blog", "youtube_script", "all"]
VideoFormat = Literal["short", "full"]

# 24-hour 'HH:MM' local time for the calendar reminder.
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# Video production pipeline stages. 'script_generated' is set automatically when
# a youtube_script generation completes; the rest are advanced manually.
ProductionStatus = Literal[
    "pending",
    "script_generated",
    "presentation_created",
    "video_created",
    "video_edited",
    "video_published",
]

ReviewStatus = Literal["generating", "ready", "approved", "rejected", "failed"]


# ── Requests ─────────────────────────────────────────────────────────────────


class PlanItemIn(BaseModel):
    topic: str
    scheduled_date: date
    publish_date: Optional[date] = None
    event_time: Optional[str] = Field(default=None, pattern=TIME_PATTERN)
    event_duration_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    notes: Optional[str] = None
    topic_source: Literal["ai", "manual"] = "manual"
    video_format: VideoFormat = "full"


class PlanCreateRequest(BaseModel):
    name: str
    plan_type: PlanType
    niche: str = "ai"
    start_date: date
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


class SuggestTopicsRequest(BaseModel):
    plan_type: PlanType
    niche: str = "ai"
    start_date: date
    count: Optional[int] = Field(default=None, ge=1, le=31)
    provider: Optional[str] = None


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


class SuggestTopicsResponse(BaseModel):
    topics: list[SuggestedTopic]
