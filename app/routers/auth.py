"""
Authentication endpoints: signup, email-OTP verification, login, refresh, logout.

Registration flow
-----------------
1. POST /register  — create account (unverified), store OTP in Redis, send email.
                     Returns 202 with no session cookie.
2. POST /verify-email — submit OTP; stamps email_verified_at, issues session.
3. POST /resend-otp   — regenerate and resend the OTP (rate-limited 3/minute).

Sessions are cookie-based; no token is ever returned in a response body, so
there is nothing for page JavaScript (or an XSS payload) to read.

Refresh rotation
----------------
Each login starts a token *family*. Refreshing marks the presented token used
(atomically — see REUSE_GRACE_SECONDS below) and issues a child in the same
family. Presenting a token that is already marked used means the same secret
was submitted twice. If that happened moments ago, it's overwhelmingly likely
to be the same legitimate client racing itself (e.g. two tabs both waking from
idle and refreshing within the same second) rather than theft, so it is
tolerated: a second child is issued instead of revoking anything. Only a reuse
*outside* that grace window is treated as a stolen token being replayed and
revokes the entire family — the legitimate user is logged out too, which is
the point: a silent takeover is worse than an unexpected re-login.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.core.cookies import clear_auth_cookies, cookie_names, set_auth_cookies
from app.core.otp import delete_otp, generate_otp, store_otp, verify_otp
from app.core.redis_client import astate, auth_key
from app.core.tokens import (
    TokenError,
    create_access_token,
    new_csrf_token,
    new_refresh_token,
    parse_refresh_cookie,
    refresh_expiry,
)
from app.db import queries
from app.db.session import get_session
from app.db.tables import RefreshToken, User
from app.middleware.rate_limit import limiter
from app.services.dispatch import should_use_celery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A real bcrypt hash of a value nobody can supply. Login verifies against this
# when the email is unknown so that "no such user" and "wrong password" take the
# same time; otherwise response latency enumerates registered accounts.
_DUMMY_HASH = bcrypt.hashpw(b"invalid-password-placeholder", bcrypt.gensalt())

# Revocation markers only need to outlive one access token.
_DENY_TTL = 900

# How long after a refresh token is marked used a second presentation of it is
# tolerated as a same-client multi-tab race rather than treated as theft.
REFRESH_REUSE_GRACE_SECONDS = 15


class LoginCredentials(BaseModel):
    """Login only checks shape, never strength.

    A short or old-policy password must still fail with the same 401 as any
    other wrong password — reusing the registration model here would 422 a
    too-short *guess* before it ever reaches the bcrypt comparison, which both
    breaks login for legitimately weak legacy passwords and gives an attacker
    a length oracle distinct from "wrong password".
    """

    email: EmailStr
    password: str


class RegisterCredentials(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def _check_length(cls, value: str) -> str:
        minimum = get_settings().password_min_length
        if len(value) < minimum:
            raise ValueError(f"Password must be at least {minimum} characters")
        # bcrypt silently truncates at 72 bytes, so anything beyond that is not
        # actually protecting the account and is better rejected than ignored.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return value


class VerifyEmailBody(BaseModel):
    email: EmailStr
    otp: str


class ResendOtpBody(BaseModel):
    email: EmailStr


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())


def _verify_password(plain: str, hashed: str | bytes) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed)
    except ValueError:
        return False


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user.get("created_at"),
    }


async def _issue_session(
    response: Response,
    session: AsyncSession,
    user_id: str,
    request: Request,
    family_id: str | None = None,
    parent_id: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    """Mint an access + refresh pair and set the cookies."""
    cookie_value, family, token_hash = new_refresh_token(family_id)
    expiry = expires_at or refresh_expiry()

    await session.execute(
        RefreshToken.__table__.insert().values(
            family_id=family,
            user_id=user_id,
            token_hash=token_hash,
            parent_id=parent_id,
            expires_at=expiry,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    )

    access_token, _, access_ttl = create_access_token(user_id, family)
    set_auth_cookies(
        response,
        access_token=access_token,
        access_ttl=access_ttl,
        refresh_token=cookie_value,
        refresh_ttl=int((expiry - _now()).total_seconds()),
        csrf_token=new_csrf_token(),
    )


def _queue_verification_email(
    email: str, otp: str, background_tasks: BackgroundTasks
) -> None:
    """Send the OTP email via Celery, falling back to in-process if no worker
    is consuming the default queue (dev convenience — mirrors
    :func:`app.services.dispatch.dispatch_pipeline`).

    Either way this returns immediately: ``apply_async`` only enqueues, and
    the in-process path runs after the response via ``BackgroundTasks``. A
    failure to even enqueue (e.g. Redis down) is logged, not raised — a
    missing verification email must never fail registration itself; the OTP
    is still recoverable via "Resend code".
    """
    from app.celery_tasks.email_task import send_verification_email_task

    if should_use_celery("celery"):
        try:
            send_verification_email_task.apply_async(
                args=[email, otp], queue="celery", ignore_result=True
            )
            return
        except Exception as exc:
            logger.warning(
                "Celery dispatch failed for verification email to %s: %s", email, exc
            )

    background_tasks.add_task(
        send_verification_email_task.apply, args=[email, otp], throw=False
    )


async def _revoke_family(session: AsyncSession, family_id: str) -> None:
    """Kill every refresh token in a family and its outstanding access tokens."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    try:
        await astate().set(
            auth_key("deny", "sid", family_id),
            str(_now().timestamp() * 1000),
            ex=_DENY_TTL,
        )
    except Exception as exc:
        logger.error("Could not publish session revocation for %s: %s", family_id, exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, summary="Create an account")
@limiter.limit("5/minute")
async def register(
    request: Request,
    creds: RegisterCredentials,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Create an unverified account and send a 6-digit OTP to the supplied email.

    **No session cookie is issued here.** The caller must follow up with
    ``POST /verify-email`` once the OTP arrives. Until then the account exists
    but cannot be used.
    """
    email = creds.email.lower()
    existing = await queries.get_user_by_email(session, email)
    if existing:
        if existing.get("email_verified_at"):
            raise HTTPException(status_code=409, detail="That email is already registered")
        # Unverified duplicate — resend the OTP silently.
        otp = generate_otp()
        await store_otp(existing["id"], otp)
        _queue_verification_email(email, otp, background_tasks)
        return {"email": email, "message": "Verification code sent — check your inbox"}

    # bcrypt is 100-300ms of deliberate CPU. Off the event loop so it does not
    # stall other in-flight requests.
    password_hash = await asyncio.to_thread(_hash_password, creds.password)

    user = await queries.create_user(session, email, password_hash.decode("utf-8"))
    await queries.init_usage(session, user["id"])

    otp = generate_otp()
    await store_otp(user["id"], otp)
    _queue_verification_email(email, otp, background_tasks)

    logger.info("New account registered (unverified): %s", user["id"])
    return {"email": email, "message": "Verification code sent — check your inbox"}


@router.post("/verify-email", summary="Submit OTP to activate the account")
@limiter.limit("5/minute")
async def verify_email(
    request: Request,
    response: Response,
    body: VerifyEmailBody,
    session: AsyncSession = Depends(get_session),
):
    """
    Verify the OTP emailed during registration.

    On success: stamps ``email_verified_at``, issues the session cookie pair,
    and returns the public user object — the client can immediately redirect to
    the dashboard.
    """
    email = body.email.lower()
    user = await queries.get_user_by_email(session, email)
    if user is None:
        raise HTTPException(status_code=404, detail="No account found for that email")

    if user.get("email_verified_at"):
        raise HTTPException(status_code=409, detail="Email is already verified")

    valid = await verify_otp(user["id"], body.otp.strip())
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification code",
        )

    # Stamp the verification timestamp.
    await session.execute(
        update(User)
        .where(User.id == user["id"])
        .values(email_verified_at=_now())
    )
    await session.flush()

    # Re-fetch so _public_user sees the updated record.
    user = await queries.get_user_by_id(session, user["id"])

    await _issue_session(response, session, user["id"], request)
    logger.info("Email verified, session issued for user %s", user["id"])
    return {"user": _public_user(user)}


@router.post("/resend-otp", summary="Resend the email verification code")
@limiter.limit("3/minute")
async def resend_otp(
    request: Request,
    body: ResendOtpBody,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a fresh OTP and resend it.

    Always returns 200, even when the email is unknown — callers must not be
    able to use this endpoint to check whether an address is registered.
    """
    email = body.email.lower()
    user = await queries.get_user_by_email(session, email)

    if user and not user.get("email_verified_at"):
        otp = generate_otp()
        await store_otp(user["id"], otp)
        _queue_verification_email(email, otp, background_tasks)

    return {"message": "If that email is registered, a new code has been sent"}


@router.post("/login", summary="Sign in")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    creds: LoginCredentials,
    session: AsyncSession = Depends(get_session),
):
    user = await queries.get_user_by_email(session, creds.email.lower())

    # Always run a verification, even with no matching user, so both paths cost
    # the same wall-clock time.
    stored_hash = user["password_hash"] if user else _DUMMY_HASH
    valid = await asyncio.to_thread(_verify_password, creds.password, stored_hash)

    if not user or not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="This account is disabled")

    await _issue_session(response, session, user["id"], request)
    return {"user": _public_user(user)}


@router.post("/refresh", summary="Rotate the session")
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    raw = request.cookies.get(cookie_names().refresh)
    if not raw:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        family_id, token_hash = parse_refresh_cookie(raw)
    except TokenError:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
    ).scalar_one_or_none()

    if row is None or row.family_id != family_id:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if row.revoked_at is not None or row.expires_at <= _now():
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token is no longer valid")

    # Atomically claim this token for rotation. A plain "check used_at, then
    # UPDATE it" has a TOCTOU window where two concurrent requests presenting
    # the same token (e.g. two tabs both waking from idle and refreshing
    # within the same second) can both observe used_at IS NULL before either
    # commits. This conditional UPDATE closes that window: only one request
    # can ever flip used_at from NULL.
    claimed = (
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == row.id, RefreshToken.used_at.is_(None))
            .values(used_at=_now())
            .returning(RefreshToken.id)
        )
    ).first()

    if claimed is None:
        # Someone already rotated this token. If that happened moments ago,
        # this is almost certainly the same legitimate client racing itself
        # across tabs rather than a stolen token replayed later — tolerate it
        # and issue another child instead of nuking the session. A reuse
        # outside the grace window is treated as genuine theft.
        fresh_used_at = (
            await session.execute(
                select(RefreshToken.used_at).where(RefreshToken.id == row.id)
            )
        ).scalar_one_or_none()
        raced = (
            fresh_used_at is not None
            and (_now() - fresh_used_at).total_seconds() < REFRESH_REUSE_GRACE_SECONDS
        )
        if not raced:
            logger.warning(
                "Refresh token reuse detected — revoking family %s for user %s (ip=%s)",
                row.family_id,
                row.user_id,
                request.client.host if request.client else "unknown",
            )
            await _revoke_family(session, row.family_id)
            clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="Refresh token already used")
        logger.info("Refresh token race tolerated (multi-tab) for family %s", row.family_id)

    user = await queries.get_user_by_id(session, row.user_id)
    if user is None or not user.get("is_active", True):
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Account is unavailable")

    # The child inherits the family's original expiry, so a session cannot be
    # extended indefinitely by refreshing.
    await _issue_session(
        response,
        session,
        row.user_id,
        request,
        family_id=row.family_id,
        parent_id=row.id,
        expires_at=row.expires_at,
    )
    return {"user": _public_user(user)}


@router.post("/logout", summary="Sign out of this session")
async def logout(
    response: Response,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _revoke_family(session, user["session_id"])
    try:
        # The access token stays cryptographically valid until it expires, so it
        # is denylisted explicitly rather than just dropped from the browser.
        await astate().set(auth_key("deny", "jti", user["jti"]), "1", ex=_DENY_TTL)
    except Exception as exc:
        logger.error("Could not denylist access token on logout: %s", exc)

    clear_auth_cookies(response)
    return {"message": "Signed out"}


@router.post("/logout-all", summary="Sign out everywhere")
async def logout_all(
    response: Response,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user["id"], RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    try:
        await astate().set(
            auth_key("deny", "user", user["id"]),
            str(_now().timestamp() * 1000),
            ex=_DENY_TTL,
        )
    except Exception as exc:
        logger.error("Could not publish account-wide revocation: %s", exc)

    clear_auth_cookies(response)
    return {"message": "Signed out of all sessions"}


@router.get("/me", summary="The signed-in user")
async def me(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user)}
