"""
Google Calendar integration for the content planner.

OAuth tokens (including the long-lived refresh token) are stored per user in
the google_oauth_tokens table, Fernet-encrypted with
settings.google_token_encryption_key. Credentials are auto-refreshed on load
and re-persisted after refresh.

Events are created as TIMED events at 09:00 in settings.default_timezone (not
all-day) because Google Calendar reminder overrides are unreliable on all-day
events in several clients.
"""

import json
import logging
import os
import time as _time
from datetime import datetime, timedelta

import jwt
from cryptography.fernet import Fernet
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.db import queries

# Google may echo back extra previously-granted scopes when include_granted_scopes
# is used, which oauthlib treats as a scope-change error. Relax that check so the
# token exchange succeeds on (re)connect.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    # Read-only access to the connected account's YouTube channel, playlists and
    # uploads (for the playlist-wise trending-topics feature). Existing
    # calendar-only connections keep working; users must reconnect to grant this.
    "https://www.googleapis.com/auth/youtube.readonly",
]
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
EVENT_START_HOUR = 9  # local time in settings.default_timezone
DEFAULT_DURATION_MINUTES = 60
STATE_TTL_SECONDS = 600


class CalendarError(Exception):
    """Any Google Calendar API failure the router should surface as 502."""


class NotConnectedError(CalendarError):
    """The user has no (valid) Google connection."""


class EventGoneError(CalendarError):
    """The linked calendar event no longer exists in Google Calendar."""


# ── Encryption ───────────────────────────────────────────────────────────────


def get_fernet() -> Fernet:
    key = get_settings().google_token_encryption_key
    if not key:
        raise CalendarError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


# ── OAuth flow ───────────────────────────────────────────────────────────────


def _client_config() -> dict:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise CalendarError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured.")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _make_flow() -> Flow:
    settings = get_settings()
    # PKCE is disabled: this is a confidential web client (it has a client_secret),
    # so the secret secures the exchange. Auto-generating a code_verifier here is
    # actively harmful — build_authorize_url and exchange_code use separate Flow
    # instances, so a verifier generated on one is unknown to the other, causing
    # Google's "Missing code verifier" (invalid_grant) at token exchange.
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, autogenerate_code_verifier=False
    )
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def make_state_token(user_id: str) -> str:
    """Short-lived signed state so the callback can identify the user without a
    session and reject CSRF token-planting."""
    settings = get_settings()
    return jwt.encode(
        {"sub": user_id, "purpose": "google_oauth", "exp": int(_time.time()) + STATE_TTL_SECONDS},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_state_token(state: str) -> str:
    """Return the user_id carried in a valid state token, or raise CalendarError."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise CalendarError(f"Invalid OAuth state: {exc}")
    if payload.get("purpose") != "google_oauth" or not payload.get("sub"):
        raise CalendarError("Invalid OAuth state payload")
    return payload["sub"]


def build_authorize_url(user_id: str) -> str:
    flow = _make_flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",  # force a refresh_token on every connect
        include_granted_scopes="true",
        state=make_state_token(user_id),
    )
    return url


def exchange_code(code: str, state: str) -> str:
    """Complete the OAuth flow: validate state, exchange the code, store the
    encrypted credentials. Returns the user_id the tokens were stored for."""
    user_id = verify_state_token(state)
    flow = _make_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # oauthlib/transport errors are not CalendarError
        raise CalendarError(f"Google token exchange failed: {exc}")
    creds: Credentials = flow.credentials

    connected_email = None
    try:
        # userinfo needs no extra scope grant for the email when using OIDC;
        # best-effort only — never fail the connect on this.
        oauth2 = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        connected_email = oauth2.userinfo().get().execute().get("email")
    except Exception:
        pass

    _store_credentials(user_id, creds, connected_email=connected_email)
    return user_id


def _store_credentials(user_id: str, creds: Credentials, connected_email: str = None) -> None:
    encrypted = get_fernet().encrypt(creds.to_json().encode()).decode()
    queries.save_google_tokens(
        user_id, encrypted,
        scopes=" ".join(creds.scopes or SCOPES),
        connected_email=connected_email,
    )


def load_credentials(user_id: str) -> Credentials:
    """Decrypt stored credentials, refreshing (and re-persisting) if expired.
    Raises NotConnectedError when there is nothing usable."""
    row = queries.get_google_tokens(user_id)
    if not row:
        raise NotConnectedError("Google Calendar is not connected.")
    try:
        info = json.loads(get_fernet().decrypt(row["token_json_encrypted"].encode()).decode())
        creds = Credentials.from_authorized_user_info(info, scopes=SCOPES)
    except Exception as exc:
        raise NotConnectedError(f"Stored Google credentials are unreadable: {exc}")

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            _store_credentials(user_id, creds, connected_email=row.get("connected_email"))
        except Exception as exc:
            raise NotConnectedError(f"Google token refresh failed — reconnect required: {exc}")
    return creds


def connection_status(user_id: str) -> dict:
    row = queries.get_google_tokens(user_id)
    if not row:
        return {"connected": False}
    return {
        "connected": True,
        "email": row.get("connected_email"),
        "scopes": (row.get("scopes") or "").split(),
        "updated_at": row.get("updated_at"),
    }


def revoke_and_disconnect(user_id: str) -> bool:
    """Best-effort token revocation at Google, then delete the stored row."""
    row = queries.get_google_tokens(user_id)
    if row:
        try:
            import httpx

            info = json.loads(get_fernet().decrypt(row["token_json_encrypted"].encode()).decode())
            token = info.get("refresh_token") or info.get("token")
            if token:
                httpx.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
        except Exception as exc:
            logger.warning("Google token revocation failed (continuing): %s", exc)
    return queries.delete_google_tokens(user_id)


# ── Event creation ───────────────────────────────────────────────────────────


def _parse_hh_mm(value, default_hour: int) -> tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute); fall back to (default_hour, 0)."""
    try:
        hh, mm = str(value).split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return default_hour, 0


def _event_body(item: dict, plan_name: str, event_time: str, settings,
                duration_minutes: int = None) -> dict:
    """Build the summary/description/start/end for an item's calendar event."""
    # Use the publish date when set, else the working/scheduled date.
    date_str = item.get("publish_date") or item["scheduled_date"]  # 'YYYY-MM-DD'
    hour, minute = _parse_hh_mm(event_time or item.get("event_time"), EVENT_START_HOUR)

    duration = duration_minutes or item.get("event_duration_minutes") or DEFAULT_DURATION_MINUTES
    try:
        duration = max(5, min(int(duration), 1440))
    except (ValueError, TypeError):
        duration = DEFAULT_DURATION_MINUTES

    start_dt = datetime(int(date_str[0:4]), int(date_str[5:7]), int(date_str[8:10]), hour, minute)
    end_dt = start_dt + timedelta(minutes=duration)
    start = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    description_lines = [
        f"Content plan: {plan_name}",
        f"Topic: {item['topic']}",
        f"Status: {item['production_status']}",
        f"Scheduled: {item['scheduled_date']}",
    ]
    if item.get("publish_date"):
        description_lines.append(f"Publish: {item['publish_date']}")
    if item.get("notes"):
        description_lines.append(f"Notes: {item['notes']}")
    description_lines.append(f"Open planner: {settings.frontend_url}/planner?plan={item['plan_id']}")

    return {
        "summary": f"[Content] {item['topic']}",
        "description": "\n".join(description_lines),
        "start": {"dateTime": start, "timeZone": settings.default_timezone},
        "end": {"dateTime": end, "timeZone": settings.default_timezone},
    }


def create_event_for_item(user_id: str, item: dict, plan_name: str,
                          reminders_minutes: list[int] = None,
                          event_time: str = None, duration_minutes: int = None) -> dict:
    """Create a timed calendar event on the item's scheduled date at the chosen
    time of day (event_time 'HH:MM'; defaults to 09:00) for the chosen length
    (duration_minutes; defaults to 60). Returns {event_id, event_link}."""
    settings = get_settings()
    creds = load_credentials(user_id)
    reminders = reminders_minutes or [1440, 60]

    body = _event_body(item, plan_name, event_time, settings, duration_minutes)
    body["reminders"] = {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": int(m)} for m in reminders[:5]],
    }

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = service.events().insert(calendarId="primary", body=body).execute()
    except NotConnectedError:
        raise
    except Exception as exc:
        raise CalendarError(f"Google Calendar event creation failed: {exc}")

    return {"event_id": event.get("id"), "event_link": event.get("htmlLink")}


def update_event_for_item(user_id: str, item: dict, plan_name: str,
                          event_time: str = None, duration_minutes: int = None) -> dict:
    """Patch the item's existing Google Calendar event (identified by
    item['gcal_event_id']) so date/time/duration/topic/notes changes stay in
    sync. Reminders are left untouched. Raises EventGoneError if the event no
    longer exists in Google Calendar. Returns {event_id, event_link}."""
    event_id = item.get("gcal_event_id")
    if not event_id:
        raise CalendarError("Item has no linked calendar event to update.")

    settings = get_settings()
    creds = load_credentials(user_id)
    body = _event_body(item, plan_name, event_time, settings, duration_minutes)

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    except NotConnectedError:
        raise
    except HttpError as exc:
        if exc.resp is not None and exc.resp.status in (404, 410):
            raise EventGoneError(f"Calendar event {event_id} no longer exists")
        raise CalendarError(f"Google Calendar event update failed: {exc}")
    except Exception as exc:
        raise CalendarError(f"Google Calendar event update failed: {exc}")

    return {"event_id": event.get("id"), "event_link": event.get("htmlLink")}
