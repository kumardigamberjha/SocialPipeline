"""Pydantic request/response models for Personal Intelligence (rules + goals).

Rules and goals are user-authored directives injected into every LLM prompt —
see app.services.personal_intelligence.build_intelligence_block. Scope lets a
rule apply everywhere ("global") or to one content surface only.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

RuleScope = Literal["global", "youtube", "blog", "linkedin", "instagram"]
RuleCategory = Literal["behavior", "content", "style", "constraint"]
GoalMetric = Literal["subscribers", "views", "watch_hours", "videos_published", "custom"]
GoalStatus = Literal["active", "achieved", "missed", "archived"]


# ── Rules ────────────────────────────────────────────────────────────────────


class RuleCreate(BaseModel):
    scope: RuleScope = "global"
    category: RuleCategory = "behavior"
    rule_text: str = Field(min_length=3, max_length=400)
    priority: int = Field(default=100, ge=1, le=1000)
    is_active: bool = True


class RuleUpdate(BaseModel):
    scope: Optional[RuleScope] = None
    category: Optional[RuleCategory] = None
    rule_text: Optional[str] = Field(default=None, min_length=3, max_length=400)
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
    is_active: Optional[bool] = None


# ── Goals ────────────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    platform: str = "youtube"
    metric: GoalMetric = "subscribers"
    target_value: float = Field(gt=0)
    deadline: date


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = None
    target_value: Optional[float] = Field(default=None, gt=0)
    deadline: Optional[date] = None
    status: Optional[GoalStatus] = None
