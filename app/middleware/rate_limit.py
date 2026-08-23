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
    """Rate-limit key: the authenticated user when known, else the client IP.

    Reads the same two token sources as the auth dependency — the Authorization
    header and the access cookie. It deliberately does *not* read ``?token=``:
    that parameter was removed because query strings leak into access and proxy
    logs, and a rate limiter honouring it would keep that shape alive.

    Verification failures fall through to the IP key rather than raising. This
    is a throttle, not an authorization check; the real one runs in
    app.core.auth_deps and fails closed.
    """
    from app.core.cookies import cookie_names

    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(cookie_names().access)

    if token:
        try:
            from app.core.tokens import decode_access_token

            return f"user:{decode_access_token(token).user_id}"
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
