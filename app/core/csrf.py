"""
CSRF protection for cookie-authenticated requests.

Cookies are attached by the browser automatically, so a cross-site form post
would carry a valid session unless something proves the request came from our
own page. ``SameSite=Lax`` already blocks the common case; this is the second
layer, for the cases it does not cover (and for browsers that treat Lax
loosely).

Double-submit: the ``nx_csrf`` cookie is readable by JavaScript, the client
echoes it in ``X-CSRF-Token``, and the two must match. An attacker's page can
cause the cookie to be *sent* but cannot read it to set the header.

Exempt by design:

* ``GET`` / ``HEAD`` / ``OPTIONS`` — must be side-effect free anyway.
* ``/api/auth/login`` and ``/api/auth/register`` — no session exists yet.
* ``/api/auth/verify-email`` and ``/api/auth/resend-otp`` — same: these run
  between register and the session being issued, so there is no ``nx_csrf``
  cookie yet for the client to echo back.
* ``/api/auth/refresh`` — the refresh cookie is ``SameSite=Lax`` *and* scoped to
  ``/api/auth``, so it is not attached to a cross-site request in the first place.
* ``/api/billing/webhook`` — Stripe cannot send our header; it is authenticated
  by signature instead.
* the OAuth callbacks — top-level GETs authenticated by a signed ``state``.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.cookies import cookie_names

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_HEADER = "X-CSRF-Token"

EXEMPT_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/verify-email",
        "/api/auth/resend-otp",
        "/api/auth/refresh",
        "/api/billing/webhook",
    }
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject a state-changing request that does not echo the CSRF cookie.

    This is ASGI middleware rather than a FastAPI ``Depends`` on purpose.
    ``BaseHTTPMiddleware`` only ever sees the ``http`` scope — Starlette routes
    ``websocket`` scope connections around it — so it cannot be applied to a
    WebSocket handshake, which is exactly what is needed: a WS route has no
    ``Request`` to inject, and app-level ``Depends(require_csrf)`` crashed
    every WebSocket connection with a 500 (missing required argument) trying
    to resolve one.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in SAFE_METHODS or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Bearer callers (CLI, tests, server-to-server) are not driven by a
        # browser and never carry ambient cookies, so CSRF does not apply.
        if request.headers.get("authorization", "").lower().startswith("bearer "):
            return await call_next(request)

        cookie_value = request.cookies.get(cookie_names().csrf)
        header_value = request.headers.get(CSRF_HEADER)

        if not cookie_value or not header_value:
            return JSONResponse(status_code=403, content={"detail": "CSRF token missing"})
        if not hmac.compare_digest(cookie_value, header_value):
            return JSONResponse(status_code=403, content={"detail": "CSRF token mismatch"})

        return await call_next(request)
