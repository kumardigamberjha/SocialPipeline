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
from app.core.csrf import CSRFMiddleware
from app.core.logging_config import setup_logging
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
    logger.info("  Database             : %s", settings.database_url.split("@")[-1])
    logger.info("  Redis cache          : %s", settings.redis_cache_url)
    logger.info("  Redis state          : %s", settings.redis_state_url)
    logger.info("  Log level            : %s", settings.log_level)
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Schema lives entirely in Alembic migrations now (see alembic/versions/).
    # The API does not create or alter tables at runtime — run
    # `alembic upgrade head` before starting it (docker-compose's `migrate`
    # service does this automatically).
    from app.db.session import check_connection

    if not await check_connection():
        logger.error(
            "Database is not reachable at startup. Run `alembic upgrade head` "
            "and confirm DATABASE_URL, or the app will fail on first request."
        )

    from app.core.redis_client import check_connection as check_redis

    redis_status = await check_redis()
    if not all(redis_status.values()):
        logger.warning("Redis not fully reachable at startup: %s", redis_status)

    yield  # ── application is running ──

    logger.info("Shutting down %s", settings.app_name)

    from app.core.redis_client import close_redis
    from app.db.session import dispose_engine

    await dispose_engine()
    await close_redis()


# ── Boot-time auth coverage guard ────────────────────────────────────────────
#
# Every route not explicitly listed here must have get_current_user (or
# get_current_user_ws, for WebSockets) somewhere in its dependency tree, or the
# app refuses to start. This is what actually prevents a future router from
# shipping unauthenticated — a missing Depends() in a code review is easy to
# miss; a boot failure is not.
#
# Each entry is (METHOD, path) exactly as FastAPI sees it (with {param} path
# parameters), or just the path for a WebSocket route.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    # Health / liveness — polled by the frontend and any load balancer.
    ("GET", "/api/health"),
    ("GET", "/api/status"),
    ("OPTIONS", "/api/status"),
    ("GET", "/api/today"),
    ("OPTIONS", "/api/today"),
    # OAuth callbacks — top-level GET navigations from a third-party origin,
    # authenticated by a signed `state` parameter rather than a session cookie.
    ("GET", "/api/google/callback"),
    ("GET", "/api/instagram/oauth/callback"),
    # Stripe cannot send our session cookie or CSRF header; authenticated by
    # webhook signature instead (see app.routers.billing).
    ("POST", "/api/billing/webhook"),
    # No session exists yet at these endpoints.
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/resend-otp"),
    # The public blog reader — deliberately unauthenticated (see
    # queries.get_public_blog_by_slug).
    ("GET", "/api/blog/view/{slug}"),
    ("GET", "/api/blog/{slug}"),
})


def _dependency_callables(dependant) -> set:
    """Flatten a FastAPI Dependant tree into the set of callables it invokes."""
    seen: set = set()

    def walk(d) -> None:
        if d.call is not None:
            seen.add(d.call)
        for sub in d.dependencies:
            walk(sub)

    walk(dependant)
    return seen


def _assert_all_routes_authenticated(app: FastAPI) -> None:
    from app.core.auth_deps import get_current_user, get_current_user_ws

    guards = {get_current_user, get_current_user_ws}
    violations: list[str] = []

    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        path = getattr(route, "path", None)
        if dependant is None or path is None:
            continue  # not a route FastAPI attaches a dependant to

        methods = getattr(route, "methods", None)
        if methods:  # HTTP route
            unmatched_methods = [
                m for m in methods if (m, path) not in PUBLIC_ROUTES
            ]
            if not unmatched_methods:
                continue
        else:  # WebSocket route — no `methods` attribute
            if ("WS", path) in PUBLIC_ROUTES:
                continue

        if guards & _dependency_callables(dependant):
            continue

        label = f"{','.join(sorted(methods))} {path}" if methods else f"WS {path}"
        violations.append(label)

    if violations:
        raise RuntimeError(
            "Refusing to start: the following routes have no authentication "
            "dependency and are not in app.main.PUBLIC_ROUTES:\n  - "
            + "\n  - ".join(sorted(violations))
        )


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

    from app.core.auth_deps import register_websocket_auth_handler
    register_websocket_auth_handler(application)

    # ── CSRF ─────────────────────────────────────────────────────────────
    # Applies to every HTTP request; WebSocket connections are untouched (see
    # CSRFMiddleware's docstring for why this must be middleware and not a
    # FastAPI Depends). Exempts safe methods and a short explicit list
    # (login/register/refresh, the Stripe webhook) internally.
    application.add_middleware(CSRFMiddleware)

    # ── Rate Limiting ────────────────────────────────────────────────────
    from app.middleware.rate_limit import setup_rate_limiter
    setup_rate_limiter(application)

    # ── CORS ─────────────────────────────────────────────────────────────
    # allow_credentials=True is required for the browser to send the session
    # cookies cross-origin (dev: localhost:3000 -> localhost:8000). In
    # production the app is served same-origin behind the Cloudflare tunnel
    # (see deployment notes), so this mainly matters for local development.
    origins = settings.cors_origin_list

    cors_kwargs = {
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }

    if not is_production:
        # In development, allow any http/https request from localhost or 127.0.0.1 on any port
        cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        if origins:
            cors_kwargs["allow_origins"] = origins
    else:
        cors_kwargs["allow_origins"] = origins

    application.add_middleware(
        CORSMiddleware,
        **cors_kwargs
    )

    # ── Routers ──────────────────────────────────────────────────────────
    from app.routers import (
        assistant,
        auth,
        billing,
        blog,
        google_auth,
        images,
        instagram_analytics,
        instagram_auth,
        linkedin,
        memory,
        personal_intelligence,
        planner,
        rag,
        runs,
        saved_topics,
        ws,
        youtube,
        youtube_analytics,
        youtube_competitors,
        youtube_playlist_items,
        youtube_prospects,
    )
    application.include_router(health.router)
    application.include_router(generate.router)
    application.include_router(ws.router)
    application.include_router(auth.router)
    application.include_router(rag.router)
    application.include_router(memory.router)
    application.include_router(runs.router)
    application.include_router(instagram.router)
    application.include_router(instagram_analytics.router)
    application.include_router(instagram_auth.router)
    application.include_router(instagram_auth.oauth_callback_router)
    application.include_router(billing.router)
    application.include_router(linkedin.router)
    application.include_router(linkedin.ws_router)
    application.include_router(blog.router)
    application.include_router(blog.ws_router)
    application.include_router(youtube.router)
    application.include_router(youtube.ws_router)
    application.include_router(planner.router)
    application.include_router(assistant.router)
    application.include_router(images.router)
    application.include_router(saved_topics.router)
    application.include_router(google_auth.router)
    application.include_router(youtube_analytics.router)
    application.include_router(youtube_playlist_items.router)
    application.include_router(youtube_competitors.router)
    application.include_router(youtube_prospects.router)
    application.include_router(personal_intelligence.router)

    _assert_all_routes_authenticated(application)

    return application


app = create_app()
