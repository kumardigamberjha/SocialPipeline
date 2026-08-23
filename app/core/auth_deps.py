"""
Authentication dependencies.

**This module fails closed.** Its predecessor returned a hardcoded dummy user
(``00000000-0000-0000-0000-000000000000``) whenever a token was missing,
expired, malformed or forged. Every "protected" endpoint was therefore public,
and all anonymous traffic shared a single tenant's data. There is no fallback
identity here: anything short of a verified token raises 401.

Token sources, in order:

1. ``Authorization: Bearer`` — for CLI clients and tests.
2. The access cookie — what the browser uses.

The ``?token=`` query parameter the old code accepted is **gone**. Query strings
land in access logs, proxy logs and ``Referer`` headers, so a credential placed
there leaks by default.

Revocation
----------
A signature check alone cannot express "this session was logged out", because a
JWT is valid until it expires. Three Redis keys close that gap, checked in one
pipelined round trip:

* ``deny:jti:{jti}``      — this exact token (logout)
* ``deny:sid:{sid}``      — this session family (refresh-token reuse detected)
* ``deny:user:{user_id}`` — every session for the user (log out everywhere)

They live on the ``noeviction`` Redis instance: an evicted denylist entry would
silently un-revoke a token.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import cookie_names
from app.core.redis_client import astate, auth_key
from app.core.tokens import AccessClaims, TokenError, decode_access_token
from app.db import queries
from app.db.session import get_session

logger = logging.getLogger(__name__)

# WebSocket close codes. 4401/4403 mirror HTTP 401/403 in the private range.
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)

_UNVERIFIED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Email address has not been verified",
)


def _extract_token(headers, cookies) -> str | None:
    auth_header = headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    return cookies.get(cookie_names().access)


async def _assert_not_revoked(claims: AccessClaims) -> None:
    """Raise TokenError if this token, its session, or its user was revoked."""
    try:
        redis = astate()
        pipe = redis.pipeline()
        pipe.exists(auth_key("deny", "jti", claims.jti))
        pipe.get(auth_key("deny", "sid", claims.session_id))
        pipe.get(auth_key("deny", "user", claims.user_id))
        jti_denied, sid_revoked_at, user_revoked_at = await pipe.execute()
    except Exception as exc:
        # Fail closed. If the revocation store is unreachable we cannot tell a
        # live session from a revoked one, and guessing "live" would resurrect
        # every logged-out token for the duration of the outage.
        logger.error("Revocation check unavailable: %s", exc)
        raise TokenError("Unable to verify session state") from exc

    if jti_denied:
        raise TokenError("Token has been revoked")

    issued_ms = claims.issued_at.timestamp() * 1000
    for revoked_at, scope in ((sid_revoked_at, "session"), (user_revoked_at, "user")):
        # Tokens minted after the revocation instant are legitimate — this is
        # what lets "log out everywhere" not also kill the login that follows it.
        if revoked_at and issued_ms < float(revoked_at):
            raise TokenError(f"Token was revoked ({scope})")


async def _authenticate(
    headers, cookies, session: AsyncSession
) -> dict:
    token = _extract_token(headers, cookies)
    if not token:
        raise TokenError("No credentials supplied")

    claims = decode_access_token(token)
    await _assert_not_revoked(claims)

    user = await queries.get_user_by_id(session, claims.user_id)
    if user is None:
        # Signed by us, but the account is gone.
        raise TokenError("User no longer exists")
    if not user.get("is_active", True):
        raise TokenError("Account is disabled")
    if not user.get("email_verified_at"):
        raise EmailNotVerifiedError("Email address has not been verified")

    user.pop("password_hash", None)
    user["session_id"] = claims.session_id
    user["jti"] = claims.jti
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The authenticated and *verified* user, or 401/403.

    Returns 401 when there is no valid session at all.
    Returns 403 when there is a valid session but the email is unverified.
    """
    try:
        return await _authenticate(request.headers, request.cookies, session)
    except EmailNotVerifiedError as exc:
        logger.debug("Unverified user: %s", exc)
        raise _UNVERIFIED from exc
    except TokenError as exc:
        logger.debug("Authentication rejected: %s", exc)
        raise _UNAUTHENTICATED from exc


async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict | None:
    """The authenticated user, or None.

    Only for endpoints that genuinely serve both signed-in and anonymous
    callers. It is not a softer ``get_current_user`` — an endpoint returning
    tenant data must use the strict one.
    """
    try:
        return await _authenticate(request.headers, request.cookies, session)
    except TokenError:
        return None


async def get_current_user_ws(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Authenticate a WebSocket handshake, closing 4401 on failure.

    Cookies are sent on same-origin WebSocket handshakes (the handshake is an
    HTTP GET), so the browser needs nothing extra. The connection is closed
    *before* ``accept()``, so an unauthenticated client never gets a live socket.
    """
    try:
        return await _authenticate(websocket.headers, websocket.cookies, session)
    except TokenError as exc:
        logger.debug("WebSocket authentication rejected: %s", exc)
        await websocket.close(code=WS_UNAUTHENTICATED, reason="Not authenticated")
        raise WebSocketAuthError(str(exc)) from exc


class EmailNotVerifiedError(Exception):
    """Raised when a valid session exists but the email is not yet verified.

    Converted to HTTP 403 by get_current_user so the frontend can distinguish
    'not logged in' (401) from 'logged in but unverified' (403).
    """


class WebSocketAuthError(Exception):
    """Raised after the socket has already been closed with 4401 or 4403.

    Purely a control-flow signal to unwind out of dependency resolution and
    skip the route body — the close has already happened by the time this is
    raised. See ``register_websocket_auth_handler`` for why the app must
    install an exception handler for it.
    """


async def _silence_websocket_auth_error(request, exc: WebSocketAuthError) -> None:
    """No-op handler for WebSocketAuthError.

    Without this, FastAPI has no registered handler for the exception, so it
    propagates to uvicorn's ASGI server as a genuine crash — logged at ERROR
    with a full traceback — for what is routine, expected traffic (someone
    hit a WebSocket endpoint without a valid session). The socket is already
    closed by the time this runs; there is nothing left to do.
    """
    return None


def register_websocket_auth_handler(app) -> None:
    """Wire the silencer above into the FastAPI app. Call once, from main.py."""
    app.add_exception_handler(WebSocketAuthError, _silence_websocket_auth_error)
