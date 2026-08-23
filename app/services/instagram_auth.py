"""
Meta Instagram OAuth & 60-Day Token Lifecycle Management Service.

Handles:
1. Per-user OAuth Authorization Flow (OAuth URL generation & Callback code exchange),
   bound to the initiating user via a short-lived signed ``state`` JWT — the callback
   has no session, so this is the only way it learns which user connected.
2. Exchanging short-lived tokens for 60-Day Long-Lived Tokens.
3. Auto-refreshing 60-Day Long-Lived Tokens before expiration (~60 days validity).
4. Per-user token persistence to the ``instagram_oauth_tokens`` table, Fernet-encrypted
   with the same key Google Calendar/YouTube tokens use
   (settings.google_token_encryption_key — documented as shared across both).

Replaces the previous design, which wrote a single token into ``os.environ`` /
``app/.env`` — one Instagram connection for the whole deployment, shared (and
overwritten) by every user.
"""

import os
import time as _time
import logging
import httpx
import jwt
from cryptography.fernet import Fernet
from typing import Dict, Any, Optional, List
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db import sync_queries
from app.db.sync_session import sync_session_scope

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v20.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
STATE_TTL_SECONDS = 600


def get_instagram_app_credentials() -> Dict[str, Optional[str]]:
    """Retrieve App ID, App Secret, and Redirect URI from environment or config."""
    app_id = os.getenv("INSTAGRAM_APP_ID") or os.getenv("META_APP_ID")
    app_secret = os.getenv("INSTAGRAM_APP_SECRET") or os.getenv("META_APP_SECRET")
    # NOTE: os.getenv() only reads exported shell env vars, NOT .env file values.
    # Pydantic Settings reads .env, so we must use get_settings() as the primary source.
    redirect_uri = os.getenv("INSTAGRAM_REDIRECT_URI") or os.getenv("META_REDIRECT_URI")

    try:
        settings = get_settings()
        app_id = app_id or settings.instagram_app_id
        app_secret = app_secret or settings.instagram_app_secret
        # Use settings value if os.getenv returned nothing (most common case with .env files)
        redirect_uri = redirect_uri or settings.instagram_redirect_uri
    except Exception:
        pass

    # Only fall back to hardcoded default if BOTH os.environ AND .env file have nothing
    if not redirect_uri:
        redirect_uri = "http://localhost:8001/api/instagram/oauth/callback"

    return {
        "app_id": app_id.strip() if app_id else None,
        "app_secret": app_secret.strip() if app_secret else None,
        "redirect_uri": redirect_uri.strip() if redirect_uri else None,
    }


def build_instagram_oauth_url(
    scopes: Optional[List[str]] = None,
    use_instagram_login: bool = True,
    state: Optional[str] = None,
) -> str:
    """
    Generates Meta/Instagram OAuth dialog URL for user permission grant.
    Defaults to Instagram Business Login (api.instagram.com) for Instagram App IDs.
    ``state`` is echoed back verbatim on the callback — used to identify the user
    who initiated the flow (see ``make_state_token``/``verify_state_token``).
    """
    creds = get_instagram_app_credentials()
    app_id = creds["app_id"]
    redirect_uri = creds["redirect_uri"]

    logger.info("Building OAuth URL — app_id=%s | redirect_uri=%s", app_id, redirect_uri)

    if not app_id:
        raise ValueError("INSTAGRAM_APP_ID is missing in environment/.env configuration.")

    state_param = f"&state={quote(state)}" if state else ""

    if use_instagram_login:
        if not scopes:
            scopes = [
                "instagram_business_basic",
                "instagram_business_manage_messages",
                "instagram_business_manage_comments",
                "instagram_business_content_publish",
                "instagram_business_manage_insights",
            ]
        scope_str = ",".join(scopes)
        return (
            f"https://api.instagram.com/oauth/authorize?"
            f"client_id={app_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope_str}&"
            f"response_type=code"
            f"{state_param}"
        )

    if not scopes:
        scopes = [
            "instagram_basic",
            "pages_show_list",
            "instagram_manage_messages",
            "instagram_manage_insights",
            "pages_read_engagement",
            "instagram_content_publish",
        ]
    scope_str = ",".join(scopes)

    return (
        f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?"
        f"client_id={app_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope_str}&"
        f"response_type=code"
        f"{state_param}"
    )


def exchange_code_for_short_lived_token(code: str) -> Dict[str, Any]:
    """
    Exchanges authorization code received from Meta OAuth redirect for a short-lived token.
    Uses api.instagram.com/oauth/access_token (not graph.facebook.com) for Instagram Business Login flows.
    """
    creds = get_instagram_app_credentials()
    app_id = creds["app_id"]
    app_secret = creds["app_secret"]
    redirect_uri = creds["redirect_uri"]

    if not app_id or not app_secret:
        raise ValueError("INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET must be set to exchange OAuth code.")

    # Instagram Business Login requires api.instagram.com/oauth/access_token for the code exchange.
    # graph.facebook.com/oauth/access_token is only for the SECOND step (short → long-lived).
    url = "https://api.instagram.com/oauth/access_token"
    payload = {
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }

    with httpx.Client(timeout=20.0) as client:
        # Instagram token exchange requires POST with form-encoded body
        resp = client.post(url, data=payload)
        data = resp.json()
        if "error" in data or "error_type" in data:
            err_msg = data.get("error_message") or data.get("error", {}).get("message", "Failed to exchange OAuth code")
            err_code = data.get("code") or data.get("error", {}).get("code", "")
            logger.error("OAuth code exchange error: %s", data)
            raise ValueError(f"Meta OAuth Error: {err_msg} (Code: {err_code})")
        return data


def get_long_lived_token(app_id: str, app_secret: str, short_lived_token: str) -> Dict[str, Any]:
    """
    Exchange short-lived Instagram token for a 60-day long-lived token.

    For Instagram Business Login tokens, the correct endpoint is:
      GET graph.instagram.com/access_token?grant_type=ig_exchange_token

    NOT graph.facebook.com (that's for Facebook Login / fb_exchange_token only).
    """
    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": app_secret,   # Only secret needed — no client_id
        "access_token": short_lived_token,
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, params=params)
        data = resp.json()
        if "error" in data:
            err_msg = data["error"].get("message", "Failed to exchange for long-lived token")
            logger.error("Long-lived token exchange error: %s", data["error"])
            raise ValueError(f"Meta Token Exchange Error: {err_msg} (Code: {data['error'].get('code')})")
        logger.info("Long-lived token obtained. expires_in=%s seconds", data.get("expires_in"))
        return data
        # Returns: {"access_token": "...", "token_type": "bearer", "expires_in": 5183944}


def refresh_long_lived_token(app_id: str, app_secret: str, current_long_lived_token: str) -> Dict[str, Any]:
    """
    Refresh the 60-day long-lived Instagram token before it expires.

    For Instagram Business Login tokens, the correct refresh endpoint is:
      GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token

    Only the current long-lived token is needed — no app_id or app_secret.
    """
    url = "https://graph.instagram.com/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": current_long_lived_token,
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, params=params)
        data = resp.json()
        if "error" in data:
            err_msg = data["error"].get("message", "Failed to refresh long-lived token")
            logger.error("Token refresh error: %s", data["error"])
            raise ValueError(f"Meta Token Refresh Error: {err_msg} (Code: {data['error'].get('code')})")
        logger.info("Long-lived Instagram token refreshed. expires_in=%s seconds", data.get("expires_in"))
        return data


# ── Encryption ───────────────────────────────────────────────────────────────


def _get_fernet() -> Fernet:
    key = get_settings().google_token_encryption_key
    if not key:
        raise ValueError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def _decrypt_token(access_token_enc: str) -> str:
    return _get_fernet().decrypt(access_token_enc.encode()).decode()


# ── Per-user OAuth state ─────────────────────────────────────────────────────


def make_state_token(user_id: str) -> str:
    """Short-lived signed state so the callback can identify the user without a
    session and reject CSRF token-planting."""
    settings = get_settings()
    return jwt.encode(
        {"sub": user_id, "purpose": "instagram_oauth", "exp": int(_time.time()) + STATE_TTL_SECONDS},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_state_token(state: str) -> str:
    """Return the user_id carried in a valid state token, or raise ValueError."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid OAuth state: {exc}")
    if payload.get("purpose") != "instagram_oauth" or not payload.get("sub"):
        raise ValueError("Invalid OAuth state payload")
    return payload["sub"]


def build_authorize_url(user_id: str, use_instagram_login: bool = True) -> str:
    return build_instagram_oauth_url(
        use_instagram_login=use_instagram_login,
        state=make_state_token(user_id),
    )


# ── Per-user token storage ───────────────────────────────────────────────────


def _parse_expires_at(value) -> datetime:
    """``sync_queries.get_instagram_tokens`` goes through ``row_to_dict``, which
    serializes every datetime column to an ISO string (see app/db/_util.py::_iso)
    so response models can accept the same shape everywhere — so this is a
    string on read, even though it was a real datetime on write."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _store_credentials(
    user_id: str,
    ig_user_id: str,
    username: Optional[str],
    access_token: str,
    expires_in: int,
    scopes: Optional[str] = None,
) -> None:
    encrypted = _get_fernet().encrypt(access_token.encode()).decode()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    with sync_session_scope() as session:
        sync_queries.save_instagram_tokens(
            session, user_id, ig_user_id, username, encrypted, expires_at, scopes=scopes,
        )


def exchange_code(code: str, state: str) -> str:
    """Complete the OAuth flow: validate state, run the short→long-lived token
    exchange, fetch the connected profile, store the encrypted credentials.
    Returns the user_id the tokens were stored for."""
    user_id = verify_state_token(state)

    creds = get_instagram_app_credentials()
    app_id, app_secret = creds["app_id"], creds["app_secret"]
    if not app_id or not app_secret:
        raise ValueError("INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET must be set to exchange OAuth code.")

    short_res = exchange_code_for_short_lived_token(code)
    short_token = short_res.get("access_token")
    if not short_token:
        raise ValueError("No access token returned from code exchange.")

    long_res = get_long_lived_token(app_id, app_secret, short_token)
    long_token = long_res.get("access_token")
    expires_in = long_res.get("expires_in", 5184000)
    if not long_token:
        raise ValueError("No long-lived token returned from Meta exchange.")

    # Deferred import: instagram_data.py imports this module back (for token
    # lookup), so this stays function-local to avoid a module-level cycle.
    from app.services.instagram_data import get_connected_instagram_account

    profile = get_connected_instagram_account(long_token)
    ig_user_id = profile.get("id")
    if not ig_user_id:
        raise ValueError("Could not determine the connected Instagram account.")

    _store_credentials(user_id, ig_user_id, profile.get("username"), long_token, expires_in)
    return user_id


def connection_status(user_id: str) -> dict:
    with sync_session_scope() as session:
        row = sync_queries.get_instagram_tokens(session, user_id)
    if not row:
        return {"connected": False, "username": None, "is_valid": False, "days_remaining": None, "expires_at": None}

    expires_at = _parse_expires_at(row["token_expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    days_remaining = round((expires_at - datetime.now(timezone.utc)).total_seconds() / 86400.0, 1)
    return {
        "connected": True,
        "username": row.get("username"),
        "is_valid": days_remaining > 0,
        "days_remaining": days_remaining,
        "expires_at": expires_at.isoformat(),
    }


def revoke_and_disconnect(user_id: str) -> bool:
    """Meta has no documented public token-revoke endpoint for Instagram Business
    Login tokens (unlike Google) — this just removes the stored row."""
    with sync_session_scope() as session:
        return sync_queries.delete_instagram_tokens(session, user_id)


def refresh_if_needed(user_id: str, force: bool = False) -> Optional[dict]:
    """Refreshes the stored long-lived token if it's within 15 days of expiry
    (or if forced). Returns the (possibly refreshed) stored row, or None if the
    user has no connection."""
    with sync_session_scope() as session:
        row = sync_queries.get_instagram_tokens(session, user_id)
    if not row:
        return None

    expires_at = _parse_expires_at(row["token_expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    days_remaining = (expires_at - datetime.now(timezone.utc)).total_seconds() / 86400.0

    if not force and days_remaining > 15:
        return row

    creds = get_instagram_app_credentials()
    app_id, app_secret = creds["app_id"], creds["app_secret"]
    if not app_id or not app_secret:
        logger.debug("Instagram token refresh skipped: app credentials not configured.")
        return row

    try:
        current_token = _decrypt_token(row["access_token_enc"])
        result = refresh_long_lived_token(app_id, app_secret, current_token)
    except Exception as exc:
        logger.warning("Instagram token refresh failed for user %s: %s", user_id, exc)
        if force:
            raise
        return row

    new_token = result.get("access_token")
    if not new_token:
        return row

    _store_credentials(
        user_id, row["ig_user_id"], row.get("username"), new_token,
        result.get("expires_in", 5184000), scopes=row.get("scopes"),
    )
    with sync_session_scope() as session:
        return sync_queries.get_instagram_tokens(session, user_id)


def get_instagram_access_token(user_id: str) -> Optional[str]:
    """Decrypted access token for the user's connected Instagram account,
    auto-refreshing first if it's expiring soon. Returns None if not connected."""
    row = refresh_if_needed(user_id)
    if not row:
        return None
    return _decrypt_token(row["access_token_enc"])
