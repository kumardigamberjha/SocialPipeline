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
        default="ollama",
        description="LLM provider to use. One of: nvidia, groq, ollama, openai, anthropic, google.",
    )


# ── Responses ────────────────────────────────────────────────────────────────


class GenerateResponse(BaseModel):
    """Response returned after a successful pipeline run."""

    status: str = "success"
    topic: str
    provider_used: str
    duration_seconds: float
    result: str = Field(description="Raw output from the CrewAI pipeline.")


class BlogGenerateRequest(BaseModel):
    """Payload for the long-form blog generation endpoint."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["Building Production RAG Systems"],
        description="The topic to write an exhaustive ~20,000-word blog post about.",
    )
    provider: str = Field(
        default="ollama",
        description="LLM provider to use. One of: nvidia, groq, ollama, openai, anthropic, google.",
    )
    niche: str = Field(
        default="AI / Software Development",
        description="Niche label embedded in the post header.",
    )


class BlogGenerateResponse(BaseModel):
    """Returned immediately after a blog generation job is queued."""

    status: str = "queued"
    run_id: str = Field(description="Track progress via /api/ws/blog/{client_id} or poll the run.")
    topic: str
    provider: str


class BlogPostOut(BaseModel):
    """A persisted blog post row."""

    id: str
    run_id: str | None = None
    user_id: str
    topic: str
    title: str | None = None
    content: str
    word_count: int | None = None
    reading_time_minutes: int | None = None
    niche: str | None = None
    approved: bool | None = None
    published_at: str | None = None
    slug: str | None = None


class BlogPostSummary(BaseModel):
    """A blog post without its (large) markdown body — for list views."""

    id: str
    topic: str
    title: str | None = None
    word_count: int | None = None
    reading_time_minutes: int | None = None
    niche: str | None = None
    approved: bool | None = None
    published_at: str | None = None
    slug: str | None = None


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
