"""Pydantic models for the Short-Form & Instagram Reels Prospect Audit Engine."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

ShortFormPlatform = Literal["youtube", "instagram", "tiktok"]
ProspectStatus = Literal["new", "contacted", "replied", "archived"]


class ShortFormLookupRequest(BaseModel):
    """Query to resolve a creator or brand profile."""
    platform: ShortFormPlatform = "youtube"
    query: str = Field(min_length=1, max_length=500, description="Handle, URL, or channel name")


class ShortFormGenerateRequest(BaseModel):
    """Payload to trigger the complete Short-Form / Reels audit."""
    platform: ShortFormPlatform = "youtube"
    identifier: str = Field(min_length=1, max_length=500, description="Channel ID or handle")
    title: Optional[str] = None
    custom_notes: Optional[str] = None


class ShortFormProfile(BaseModel):
    platform: ShortFormPlatform
    identifier: str
    title: str
    handle: str
    avatar_url: Optional[str] = None
    followers_or_subs: int = 0
    total_videos_or_posts: int = 0
    bio: Optional[str] = None
    profile_url: Optional[str] = None


class ShortFormGapMetrics(BaseModel):
    shorts_count: int = 0
    longform_count: int = 0
    shorts_ratio_pct: float = 0.0
    estimated_missed_views: int = 0
    outlier_multiplier: float = 1.0
    shortform_opportunity_score: int = Field(default=85, ge=0, le=100)
    opportunity_verdict: str = "High Short-Form Repurposing Arbitrage"


class ReelConversionBlueprint(BaseModel):
    source_title: str
    source_url: Optional[str] = None
    clip_timestamp_start: str
    clip_timestamp_end: str
    duration_seconds: int = 50
    viral_hook_3s: str
    visual_hook_prompt: str
    pacing_and_sound: str
    caption: str
    estimated_viral_score: int = Field(default=90, ge=1, le=100)


class HookTeardown(BaseModel):
    original_angle: str
    weakness_diagnosis: str
    viral_rewrite_1: str
    viral_rewrite_2: str
    framework_used: str


class ShortFormSprintDay(BaseModel):
    day_number: int
    week_number: int
    pillar: str
    topic: str
    hook: str
    format_style: str
    target_cta: str


class ShortFormOutreachCopy(BaseModel):
    cold_email_subject: str
    cold_email_body: str
    dm_pitch: str
    followup_bump: str


class ShortFormAuditReport(BaseModel):
    report_id: str
    profile: ShortFormProfile
    gap_metrics: ShortFormGapMetrics
    blueprints: List[ReelConversionBlueprint] = Field(default_factory=list)
    hook_teardowns: List[HookTeardown] = Field(default_factory=list)
    sprint_calendar: List[ShortFormSprintDay] = Field(default_factory=list)
    outreach_copy: ShortFormOutreachCopy
    executive_summary: str
    generated_at: str
    model: str
    outreach_status: ProspectStatus = "new"
