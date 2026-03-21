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
    """Return application status, version, and available providers."""
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        providers=["nvidia", "groq"],
        agents_available=10,
    )
