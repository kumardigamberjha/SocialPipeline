"""Pydantic request models for YouTube prospect audits."""

from typing import Literal

from pydantic import BaseModel, Field

ProspectStatus = Literal["new", "contacted", "replied", "archived"]


class ProspectLookupRequest(BaseModel):
    """Free text, a @handle, a UC… id, or any youtube.com / youtu.be URL."""

    query: str = Field(min_length=1, max_length=500)


class UpdateProspectRequest(BaseModel):
    outreach_status: ProspectStatus
