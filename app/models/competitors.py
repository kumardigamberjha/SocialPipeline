"""Pydantic request/response models for YouTube competitor tracking."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

CompetitorStatus = Literal["approved", "rejected", "archived"]


class ApproveDiscoveryRequest(BaseModel):
    approved: list[str] = Field(default_factory=list)  # channel_ids
    rejected: list[str] = Field(default_factory=list)   # channel_ids


class AddCompetitorRequest(BaseModel):
    channel_id: Optional[str] = None
    handle: Optional[str] = None


class UpdateCompetitorRequest(BaseModel):
    status: Optional[CompetitorStatus] = None
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
