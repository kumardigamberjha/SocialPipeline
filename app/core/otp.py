"""
One-time password (OTP) helpers for email verification.

A 6-digit numeric code is generated with ``secrets`` and stored in Redis as an
HMAC-SHA256 hash (so a Redis leak does not yield usable codes).  The raw code
is sent to the user's inbox; only the hash is ever persisted.

Key space: ``otp:verify:{user_id}``  (on the noeviction state instance)
TTL:       configurable via ``email_verify_otp_ttl_seconds`` (default 600 s)

Verification is constant-time to resist timing attacks; the key is deleted on
first success to make OTPs truly single-use.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import logging

from app.config import get_settings
from app.core.redis_client import astate

logger = logging.getLogger(__name__)

_KEY_PREFIX = "otp:verify:"


def _otp_key(user_id: str) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def _hash_otp(raw: str) -> str:
    """HMAC-SHA256 of the raw OTP keyed on the application SECRET_KEY."""
    secret = get_settings().secret_key.encode()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()


def generate_otp() -> str:
    """Return a cryptographically random 6-digit string (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def store_otp(user_id: str, otp: str) -> None:
    """Hash and store the OTP in Redis with the configured TTL."""
    ttl = get_settings().email_verify_otp_ttl_seconds
    await astate().set(_otp_key(user_id), _hash_otp(otp), ex=ttl)
    logger.debug("OTP stored for user %s (ttl=%ds)", user_id, ttl)


async def verify_otp(user_id: str, otp: str) -> bool:
    """
    Return True if *otp* matches the stored hash for *user_id*.

    Deletes the key on success (single-use).  Returns False — never raises —
    on mismatch, expiry, or missing key.
    """
    stored = await astate().get(_otp_key(user_id))
    if stored is None:
        logger.debug("OTP verify: no key found for user %s", user_id)
        return False

    # ``stored`` may come back as bytes or str depending on redis decode setting.
    stored_str = stored.decode() if isinstance(stored, bytes) else stored
    candidate = _hash_otp(otp)

    if not hmac.compare_digest(stored_str, candidate):
        logger.debug("OTP verify: mismatch for user %s", user_id)
        return False

    # Consume the OTP — it must not be usable again.
    await astate().delete(_otp_key(user_id))
    logger.debug("OTP verified and consumed for user %s", user_id)
    return True


async def delete_otp(user_id: str) -> None:
    """Explicitly remove any pending OTP (e.g. on account deletion)."""
    await astate().delete(_otp_key(user_id))
