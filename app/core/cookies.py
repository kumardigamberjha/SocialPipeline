"""
Session cookie names, flags and lifecycle.

One source of truth. Cookie deletion only works when the Name, Path, Domain,
Secure and SameSite attributes match the ones used to set it — a single
mismatched Path silently leaves a live session cookie in the browser after
"log out", which is why nothing here hardcodes a name at the call site.

Layout
------
=============  ==========================  ==========================================
cookie         scope                       why
=============  ==========================  ==========================================
``nx_at``      ``/``, HttpOnly             access token; every API call needs it
``nx_rt``      ``/api/auth``, HttpOnly     refresh token; never sent to normal
                                           endpoints, so it is not exposed on every
                                           request it has no business being in
``nx_csrf``    ``/``, **readable by JS**   double-submit CSRF value
=============  ==========================  ==========================================

``SameSite=Lax``, not ``Strict``: the Google and Instagram OAuth callbacks are
top-level GET navigations from a third-party origin, and ``Strict`` would drop
the session on the way back. ``Lax`` still refuses to send cookies on cross-site
POST, which is the CSRF case that matters.

In production the names carry the ``__Host-`` prefix, which pins a cookie to the
exact host with ``Path=/`` and ``Secure`` and forbids a ``Domain`` attribute —
so a compromised sibling subdomain cannot overwrite the session. The browser
rejects that prefix over plain http, hence the environment-conditional naming.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Response

from app.config import get_settings

ACCESS_COOKIE = "nx_at"
REFRESH_COOKIE = "nx_rt"
CSRF_COOKIE = "nx_csrf"

# The refresh cookie is scoped to the auth router only.
REFRESH_PATH = "/api/auth"


@dataclass(frozen=True)
class CookieNames:
    access: str
    refresh: str
    csrf: str


def cookie_names() -> CookieNames:
    prefix = get_settings().cookie_prefix
    # __Host- requires Path=/ , which the refresh cookie deliberately violates,
    # so it takes the weaker __Secure- prefix instead of silently being rejected.
    secure_prefix = "__Secure-" if prefix else ""
    return CookieNames(
        access=f"{prefix}{ACCESS_COOKIE}",
        refresh=f"{secure_prefix}{REFRESH_COOKIE}",
        # Readable by JavaScript by design, so it cannot take __Host-/__Secure-
        # semantics that imply otherwise; it carries no authority on its own.
        csrf=CSRF_COOKIE,
    )


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    access_ttl: int,
    refresh_token: str,
    refresh_ttl: int,
    csrf_token: str,
) -> None:
    """Attach a full session to the response."""
    settings = get_settings()
    names = cookie_names()
    secure = settings.cookie_secure

    response.set_cookie(
        names.access,
        access_token,
        max_age=access_ttl,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        names.refresh,
        refresh_token,
        max_age=refresh_ttl,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=REFRESH_PATH,
    )
    response.set_cookie(
        names.csrf,
        csrf_token,
        max_age=refresh_ttl,
        httponly=False,  # the browser client must echo this in a header
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove every session cookie, matching the attributes used to set them."""
    settings = get_settings()
    names = cookie_names()
    secure = settings.cookie_secure

    for name, path in (
        (names.access, "/"),
        (names.refresh, REFRESH_PATH),
        (names.csrf, "/"),
    ):
        response.delete_cookie(
            name,
            path=path,
            secure=secure,
            samesite="lax",
            httponly=name != names.csrf,
        )
