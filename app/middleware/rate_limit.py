"""
Rate limiting middleware using slowapi.

Per-user rate limiting keyed by JWT user_id (fallback to client IP).
Tiers: free (2/hour), pro (10/hour), enterprise (unlimited).

Usage:
    In app/main.py:
        from app.middleware.rate_limit import setup_rate_limiter
        setup_rate_limiter(app)
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _get_user_key(request: Request) -> str:
    """
    Extract rate-limit key from request.
    Priority: JWT user_id from Authorization header > client IP.
    """
    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Also check query params (used by WebSocket upgrade requests)
    if not token:
        token = request.query_params.get("token")

    if token:
        try:
            import jwt
            from app.config import get_settings
            settings = get_settings()
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_get_user_key)


def setup_rate_limiter(app: FastAPI):
    """Attach the slowapi rate limiter to the FastAPI application."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _custom_rate_limit_handler)


async def _custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return a JSON 429 response instead of slowapi's default HTML."""
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "detail": "Rate limit exceeded. Please slow down or upgrade your plan.",
            "retry_after": exc.detail,
        },
    )
