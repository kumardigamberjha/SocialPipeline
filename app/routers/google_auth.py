"""
Google OAuth router for the planner's calendar integration.

Flow:
  1. Frontend GET /api/google/authorize → {authorization_url}, then redirects
     the browser there. The URL carries a signed short-lived state JWT with the
     user_id (CSRF protection — the callback has no session).
  2. Google redirects to GET /api/google/callback?code&state; we exchange the
     code, encrypt + store the credentials, and redirect the browser back to
     {frontend_url}/planner?google=connected|error.
  3. GET /api/google/status and DELETE /api/google/disconnect manage the link.

Token JSON is never returned by any endpoint.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.services import google_calendar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["google"])


@router.get("/status")
def google_status(current_user: dict = Depends(get_current_user)):
    return google_calendar.connection_status(current_user["id"])


@router.get("/authorize")
def google_authorize(current_user: dict = Depends(get_current_user)):
    try:
        url = google_calendar.build_authorize_url(current_user["id"])
    except google_calendar.CalendarError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"authorization_url": url}


@router.get("/callback")
def google_callback(code: str = None, state: str = None, error: str = None):
    frontend = get_settings().frontend_url.rstrip("/")
    if error or not code or not state:
        logger.warning("Google OAuth callback error: %s", error or "missing code/state")
        return RedirectResponse(f"{frontend}/planner?google=error")
    try:
        google_calendar.exchange_code(code, state)
    except google_calendar.CalendarError as exc:
        logger.warning("Google OAuth exchange failed: %s", exc)
        return RedirectResponse(f"{frontend}/planner?google=error")
    return RedirectResponse(f"{frontend}/planner?google=connected")


@router.delete("/disconnect")
def google_disconnect(current_user: dict = Depends(get_current_user)):
    removed = google_calendar.revoke_and_disconnect(current_user["id"])
    if not removed:
        raise HTTPException(status_code=404, detail="No Google connection to remove")
    return {"message": "Google Calendar disconnected"}
