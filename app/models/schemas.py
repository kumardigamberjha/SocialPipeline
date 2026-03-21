"""
Pydantic request / response models for the API.
"""

from pydantic import BaseModel, Field


# ── Requests ─────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Payload for the content generation endpoint."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["Build AI Agents using CrewAI"],
        description="The content topic to generate around.",
    )
    provider: str = Field(
        default="nvidia",
        description="LLM provider to use. One of: nvidia, groq.",
    )


# ── Responses ────────────────────────────────────────────────────────────────


class GenerateResponse(BaseModel):
    """Response returned after a successful pipeline run."""

    status: str = "success"
    topic: str
    provider_used: str
    duration_seconds: float
    result: str = Field(description="Raw output from the CrewAI pipeline.")


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    status: str = "error"
    detail: str


class HealthResponse(BaseModel):
    """Response from the health endpoint."""

    status: str = "healthy"
    app_name: str
    version: str
    providers: list[str]
    agents_available: int
