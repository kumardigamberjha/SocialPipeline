"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import setup_logging
from app.routers import generate, health, instagram

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  %s  v%s", settings.app_name, settings.app_version)
    logger.info("  Default LLM provider : %s", settings.default_provider)
    logger.info("  Redis                : %s", settings.redis_url)
    logger.info("  Log level            : %s", settings.log_level)
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Initialize SQLite tables
    from app.db.database import init_db
    init_db()

    yield  # ── application is running ──

    logger.info("Shutting down %s", settings.app_name)


# ── App factory ──────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    is_production = settings.environment == "production"

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production API for the Wings of AI autonomous content pipeline. "
            "Researches, writes, and deploys multi-platform developer content."
        ),
        lifespan=lifespan,
        # Interactive docs publish the full endpoint surface. Keep them in
        # development, withhold them in production.
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    # ── Rate Limiting ────────────────────────────────────────────────────
    from app.middleware.rate_limit import setup_rate_limiter
    setup_rate_limiter(application)

    # ── CORS ─────────────────────────────────────────────────────────────
    # settings.cors_origins is the source of truth. The localhost origins are
    # a development convenience only — appending them unconditionally (as this
    # previously did) both discarded the configured value, since the default is
    # "*", and left production permanently trusting localhost with credentials.
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip() and o.strip() != "*"]

    if not is_production:
        for origin in (
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ):
            if origin not in origins:
                origins.append(origin)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────────────────────
    from app.routers import ws, auth, rag, memory, runs, billing, linkedin, blog, youtube, planner, google_auth, youtube_analytics, youtube_playlist_items, instagram_analytics
    application.include_router(health.router)
    application.include_router(generate.router)
    application.include_router(ws.router)
    application.include_router(auth.router)
    application.include_router(rag.router)
    application.include_router(memory.router)
    application.include_router(runs.router)
    application.include_router(instagram.router)
    application.include_router(instagram_analytics.router)
    application.include_router(billing.router)
    application.include_router(linkedin.router)
    application.include_router(linkedin.ws_router)
    application.include_router(blog.router)
    application.include_router(blog.ws_router)
    application.include_router(youtube.router)
    application.include_router(youtube.ws_router)
    application.include_router(planner.router)
    application.include_router(google_auth.router)
    application.include_router(youtube_analytics.router)
    application.include_router(youtube_playlist_items.router)

    return application


app = create_app()
