"""
/api/health – System health check.
"""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Return application status, version, and available providers.

    Deliberately does not touch the database or Redis: this endpoint is polled
    every 30s by the frontend and every load balancer / orchestrator health
    check, and a slow dependency here should not make the whole app look down.
    """
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        providers=["nvidia", "groq", "ollama"],
        agents_available=10,
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

