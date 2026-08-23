"""
FastAPI Router for Meta Instagram OAuth & 60-Day Token Management.

Endpoints:
- GET    /api/instagram-auth/url        : Generates a per-user Meta OAuth Authorization URL.
- GET    /api/instagram/oauth/callback  : Meta OAuth callback handler (exchanges code -> 60-day
                                           token, stores it against the initiating user).
- POST   /api/instagram-auth/refresh    : Force-refreshes the caller's 60-day long-lived token.
- GET    /api/instagram-auth/status     : Returns the caller's Instagram connection status.
- DELETE /api/instagram-auth/disconnect : Removes the caller's stored Instagram connection.

Per-user, mirroring app/routers/google_auth.py: /url carries a signed short-lived
state JWT with the user_id (the callback has no session, so this is the only way
it learns who connected), and the token itself is stored Fernet-encrypted in
instagram_oauth_tokens, keyed by user_id — see app/services/instagram_auth.py.
"""

import logging
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.services import instagram_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram-auth", tags=["Instagram OAuth"])
oauth_callback_router = APIRouter(prefix="/api/instagram/oauth", tags=["Instagram OAuth Callback"])


@router.get("/url")
def get_oauth_authorization_url(
    auth_type: Optional[str] = Query("instagram"),
    user: dict = Depends(get_current_user),
):
    """Generates a Meta OAuth dialog URL bound to the current user via signed state."""
    try:
        use_ig = (auth_type != "facebook")
        url = instagram_auth.build_authorize_url(user["id"], use_instagram_login=use_ig)
        return {"authorization_url": url}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@oauth_callback_router.get("/callback")
def instagram_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_reason: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_challenge_alt: Optional[str] = Query(None, alias="hub_challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_verify_token_alt: Optional[str] = Query(None, alias="hub_verify_token"),
):
    """
    Handles Meta OAuth redirect callback AND Webhook verification challenges:
    1. If hub.challenge is present (Meta Webhook verification), returns challenge in plain text (200 OK).
    2. If authorization code + state are present (User OAuth login), exchanges code -> 60-day token
       and stores it against the user identified by state.
    """
    challenge = hub_challenge or hub_challenge_alt
    if challenge:
        logger.info("Meta Webhook Verification Challenge received: %s", challenge)
        return Response(content=str(challenge), media_type="text/plain", status_code=200)

    frontend = get_settings().frontend_url.rstrip("/")
    # The Instagram analytics page is at /instagram-analysis
    ig_page = f"{frontend}/instagram-analysis"

    if error or not code or not state:
        err_detail = error_description or error_reason or error or "Authorization code or state missing"
        logger.warning("Meta OAuth Callback Error: %s", err_detail)
        return RedirectResponse(f"{ig_page}?instagram=error&msg={quote(str(err_detail))}")

    try:
        user_id = instagram_auth.exchange_code(code, state)
        status = instagram_auth.connection_status(user_id)
        logger.info(
            "Successfully connected Instagram OAuth for user %s (expires %s)",
            user_id, status.get("expires_at"),
        )
        expires_at = status.get("expires_at") or ""
        return RedirectResponse(f"{ig_page}?instagram=connected&expires_at={quote(expires_at)}")
    except Exception as exc:
        logger.error("Failed to complete Meta OAuth flow: %s", exc)
        return RedirectResponse(f"{ig_page}?instagram=error&msg={quote(str(exc))}")


@router.post("/refresh")
def force_token_refresh(user: dict = Depends(get_current_user)):
    """Forces immediate refresh of the caller's long-lived Meta token."""
    try:
        refreshed = instagram_auth.refresh_if_needed(user["id"], force=True)
        if not refreshed:
            raise ValueError("No Instagram connection to refresh.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token refresh failed: {str(exc)}")
    return {
        "status": "success",
        "message": "Instagram 60-Day Long-Lived Token refreshed successfully!",
        "data": instagram_auth.connection_status(user["id"]),
    }


@router.get("/status")
def get_instagram_auth_status(user: dict = Depends(get_current_user)):
    """Returns the caller's Instagram connection presence, expiration, and health."""
    return instagram_auth.connection_status(user["id"])


@router.delete("/disconnect")
def instagram_disconnect(user: dict = Depends(get_current_user)):
    removed = instagram_auth.revoke_and_disconnect(user["id"])
    if not removed:
        raise HTTPException(status_code=404, detail="No Instagram connection to remove")
    return {"message": "Instagram disconnected"}
