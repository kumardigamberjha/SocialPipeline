"""
Access and refresh token primitives.

**Access token** — a short-lived (15 min) HS256 JWT. Short by design: it is a
bearer credential the server cannot take back once issued, so revocation is
enforced by a Redis denylist that only has to outlive one token lifetime rather
than the 30 days the previous implementation used.

**Refresh token** — deliberately *not* a JWT. It is an opaque
``{family_id}.{secret}`` pair, and only ``sha256(secret)`` is ever stored, so a
database leak yields no usable tokens. A JWT here would be self-validating,
which is exactly what you do not want for a credential that must be revocable
and single-use.

Rotation and reuse detection live in :mod:`app.routers.auth`; this module only
mints and parses.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

TOKEN_TYPE_ACCESS = "access"


class TokenError(Exception):
    """Any failure to produce a trustworthy identity from a token."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    session_id: str
    jti: str
    issued_at: datetime
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Access tokens ─────────────────────────────────────────────────────────────


def create_access_token(user_id: str, session_id: str) -> tuple[str, str, int]:
    """Mint an access JWT.

    Returns ``(token, jti, ttl_seconds)``. The jti is returned so a caller that
    logs the user out can denylist this exact token.
    """
    settings = get_settings()
    ttl = settings.access_token_ttl_seconds
    issued = _now()
    jti = str(uuid.uuid4())

    token = jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "jti": jti,
            "typ": TOKEN_TYPE_ACCESS,
            "iat": issued,
            "exp": issued + timedelta(seconds=ttl),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, ttl


def decode_access_token(token: str) -> AccessClaims:
    """Verify an access token's signature, type and expiry.

    Raises :class:`TokenError` on anything suspect. It never returns a fallback
    identity — the predecessor of this code returned a hardcoded dummy user when
    verification failed, which made every protected endpoint public.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Access token is invalid") from exc

    # A refresh token must never be accepted as an access token.
    if payload.get("typ") != TOKEN_TYPE_ACCESS:
        raise TokenError("Not an access token")

    user_id, session_id, jti = payload.get("sub"), payload.get("sid"), payload.get("jti")
    if not user_id or not session_id or not jti:
        raise TokenError("Access token is missing required claims")

    return AccessClaims(
        user_id=user_id,
        session_id=session_id,
        jti=jti,
        issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


# ── Refresh tokens ────────────────────────────────────────────────────────────


def new_refresh_token(family_id: str | None = None) -> tuple[str, str, bytes]:
    """Create a refresh token.

    Returns ``(cookie_value, family_id, token_hash)``. Only ``token_hash`` is
    persisted.
    """
    family_id = family_id or str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    return f"{family_id}.{secret}", family_id, hash_refresh_secret(secret)


def hash_refresh_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def parse_refresh_cookie(raw: str) -> tuple[str, bytes]:
    """Split a refresh cookie into ``(family_id, token_hash)``.

    Raises :class:`TokenError` when the value is not the expected shape.
    """
    if not raw or "." not in raw:
        raise TokenError("Malformed refresh token")
    family_id, _, secret = raw.partition(".")
    if not family_id or not secret:
        raise TokenError("Malformed refresh token")
    try:
        uuid.UUID(family_id)
    except ValueError as exc:
        raise TokenError("Malformed refresh token") from exc
    return family_id, hash_refresh_secret(secret)


def refresh_expiry() -> datetime:
    """Absolute expiry for a new token family.

    Absolute, not sliding: under a sliding window a stolen refresh token that
    keeps being used never expires.
    """
    return _now() + timedelta(seconds=get_settings().refresh_token_ttl_seconds)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
