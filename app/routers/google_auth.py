"""
Google OAuth router for the planner's calendar integration.

Flow:
  1. Frontend GET /api/google/authorize?next=/youtube-analysis → {authorization_url},
     then redirects the browser there. The URL carries a signed short-lived state JWT
     with the user_id and optional next_url (CSRF protection — the callback has no session).
  2. Google redirects to GET /api/google/callback?code&state; we exchange the code,
     encrypt + store the credentials, and redirect the browser back to
     {frontend_url}{next_url}?google=connected|error (defaults to /planner).
  3. GET /api/google/status and DELETE /api/google/disconnect manage the link.

Token JSON is never returned by any endpoint.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.services import google_calendar

# Every handler below is a sync `def`. FastAPI runs those in its threadpool
# automatically, which is correct here: google_calendar's functions are
# blocking by nature (a credential load can trigger a token refresh over
# HTTPS), so there is nothing to gain from asyncio.to_thread on top of that —
# it would just be a thread hopping to another thread.

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["google"])

# Allowlist of frontend paths that the callback is allowed to redirect to.
# This prevents an open-redirect where an attacker embeds an arbitrary URL.
_NEXT_ALLOWLIST = frozenset({
    "/planner",
    "/youtube-analysis",
    "/dashboard",
})


def _safe_next(next_url: str) -> str:
    """Return next_url if it is in the allowlist, otherwise '/planner'."""
    if next_url and next_url in _NEXT_ALLOWLIST:
        return next_url
    return "/planner"


@router.get("/status")
def google_status(current_user: dict = Depends(get_current_user)):
    return google_calendar.connection_status(current_user["id"])


@router.get("/authorize")
def google_authorize(
    current_user: dict = Depends(get_current_user),
    next: str = Query(default="", alias="next"),
):
    """Start the Google OAuth flow.

    ``next`` is an optional frontend path to redirect to after the callback
    (e.g. ``/youtube-analysis``). Only paths in ``_NEXT_ALLOWLIST`` are
    accepted; anything else falls back to ``/planner``.
    """
    safe_next = _safe_next(next)
    try:
        url = google_calendar.build_authorize_url(current_user["id"], next_url=safe_next)
    except google_calendar.CalendarError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"authorization_url": url}


@router.get("/callback")
def google_callback(code: str = None, state: str = None, error: str = None):
    """Handle the redirect from Google after user authorization.

    The ``state`` JWT carries the ``next_url`` embedded at authorize-time so
    we redirect back to the right frontend page without needing a session.
    """
    frontend = get_settings().frontend_url.rstrip("/")
    if error or not code or not state:
        logger.warning("Google OAuth callback error: %s", error or "missing code/state")
        return RedirectResponse(f"{frontend}/planner?google=error")
    try:
        _user_id, next_url = google_calendar.exchange_code(code, state)
    except google_calendar.CalendarError as exc:
        logger.warning("Google OAuth exchange failed: %s", exc)
        return RedirectResponse(f"{frontend}/planner?google=error")

    dest = _safe_next(next_url)
    return RedirectResponse(f"{frontend}{dest}?google=connected")


@router.delete("/disconnect")
def google_disconnect(current_user: dict = Depends(get_current_user)):
    removed = google_calendar.revoke_and_disconnect(current_user["id"])
    if not removed:
        raise HTTPException(status_code=404, detail="No Google connection to remove")
    return {"message": "Google Calendar disconnected"}
