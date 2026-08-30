"""
/api/health – System health check.
"""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.llm import active_tier, describe_chain
from app.provider_tiers import CLIENT_GRADE
from app.schemas import HealthResponse, LlmTierStatus

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Return application status, version, and the live LLM cascade state.

    Deliberately does not touch the database or Redis: this endpoint is polled
    every 30s by the frontend and every load balancer / orchestrator health
    check, and a slow dependency here should not make the whole app look down.
    ``describe_chain`` honours that — it reads configuration and an in-process
    cooldown map, and makes no network calls.

    ``providers`` used to be the hardcoded literal ``["nvidia", "groq", "ollama"]``,
    which did not include Gemini — the actual primary — and told an operator
    nothing about what was really answering. It is now derived, and kept in the
    payload only because the sidebar has rendered it since before ``llm_tiers``
    existed.
    """
    tiers = describe_chain(settings)
    active = active_tier(settings)
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        providers=[t["key"] for t in tiers if t["configured"]],
        agents_available=10,
        llm_tiers=[LlmTierStatus(**t) for t in tiers],
        active_tier_index=(active or {}).get("index"),
        active_tier_name=(active or {}).get("name"),
        active_tier_grade=(active or {}).get("grade"),
        client_grade_available=any(
            t["grade"] == CLIENT_GRADE and t["available"] for t in tiers
        ),
    )


@router.get("/status")
@router.options("/status")
async def get_status():
    """Return 200 OK for status polls."""
    return {"status": "online", "message": "System operational"}


@router.get("/today")
@router.options("/today")
async def get_today():
    """Return 200 OK for today polls."""
    from datetime import date
    return {"status": "ok", "date": str(date.today()), "items": []}

