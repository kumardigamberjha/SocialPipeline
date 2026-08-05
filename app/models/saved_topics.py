"""Pydantic request/response models for saved ("uncovered") topics."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Reused rather than redeclared — the generate contract is identical to the
# planner's, and the two must not be able to drift.
from app.models.planner import ContentType, GenerateType, ReviewStatus

# Lifecycle. No CHECK constraint backs this in SQLite (the stage list may grow);
# this Literal is the validation. 'generating' is written eagerly at dispatch;
# 'generated' and the fallback to 'uncovered' are derived on read.
SavedTopicStatus = Literal["uncovered", "generating", "generated"]
SavedTopicSource = Literal["auto_research", "manual"]


# ── Requests ─────────────────────────────────────────────────────────────────


class SavedTopicCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    rationale: Optional[str] = None
    niche: str = "ai"


class GenerateSavedTopicRequest(BaseModel):
    content_type: GenerateType = "all"
    provider: str = "ollama"


# ── Responses ────────────────────────────────────────────────────────────────


class SavedTopicRun(BaseModel):
    id: str
    content_type: ContentType
    run_id: Optional[str] = None
    content_ref_id: Optional[str] = None
    review_status: ReviewStatus
    created_at: Optional[str] = None


class SavedTopic(BaseModel):
    id: str
    topic: str
    rationale: Optional[str] = None
    niche: Optional[str] = None
    source: Optional[str] = None
    source_run_id: Optional[str] = None
    status: SavedTopicStatus
    dismissed_at: Optional[str] = None
    generated_at: Optional[str] = None
    created_at: Optional[str] = None
    runs: List[SavedTopicRun] = []


class SavedTopicSummary(BaseModel):
    """Everything the backlog banner needs, in one cheap call."""
    uncovered_count: int
    latest_created_at: Optional[str] = None
