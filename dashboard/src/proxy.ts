import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Route guard, UX-only. (`middleware.ts` was renamed to `proxy.ts` in
 * Next.js 16 — this is the same file convention under its new name; the
 * exported function is now `proxy`, not `middleware`.)
 *
 * This checks for the *presence* of a session cookie, nothing more — it
 * cannot verify the JWT's signature without the backend's signing key (and
 * should not try to; duplicating that secret into the frontend would be its
 * own security problem). A present-but-expired or forged cookie passes this
 * check and is then correctly rejected by the API, which redirects through
 * apiClient's 401 handler. This is exactly the "optimistic check" pattern
 * Next.js recommends for Proxy: read the cookie, never the database.
 *
 * It checks `nx_csrf` in addition to the access-token cookie
 * (`nx_at`/`__Host-nx_at`), not just the access cookie alone: `nx_at` expires
 * after 15 minutes (app/core/cookies.py), so checking it alone meant anyone
 * who left a tab idle past that got hard-redirected to /login on their next
 * navigation — before the client-side silent-refresh in AuthContext ever got
 * a chance to run, even though the 30-day refresh session (`nx_rt`) was still
 * perfectly valid. `nx_csrf` is set in the same response as `nx_rt` with the
 * same 30-day lifetime, but unlike `nx_rt` (scoped to Path=/api/auth, never
 * sent on a page navigation) it has Path=/, so it's actually visible here —
 * a free, reliable stand-in signal for "a refresh token likely still exists"
 * without the edge ever needing to read `nx_rt` itself.
 *
 * The real security boundary is the API's `get_current_user` dependency
 * (fail-closed, see app/core/auth_deps.py). This file exists purely so a
 * genuinely signed-out visitor sees `/login` immediately instead of a flash
 * of dashboard chrome that then errors out.
 */

const PUBLIC_PATHS = ["/login", "/signup"];
const ACCESS_COOKIE_NAMES = ["nx_at", "__Host-nx_at"];
const CSRF_COOKIE_NAME = "nx_csrf";

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  if (pathname.startsWith("/_next") || pathname === "/favicon.ico") return true;
  return false;
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  const hasSessionCookie =
    ACCESS_COOKIE_NAMES.some((name) => request.cookies.has(name)) ||
    request.cookies.has(CSRF_COOKIE_NAME);

  // Already authenticated — bounce away from the auth pages to avoid the
  // user being stuck on /login after a successful login/signup call.
  if (isPublicPath(pathname)) {
    if (
      hasSessionCookie &&
      (pathname === "/login" || pathname === "/signup")
    ) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  if (!hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname + search);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Run on page navigations only — never on /api/*. API calls are JSON
  // fetches handled by apiClient, which already has its own 401 -> refresh ->
  // redirect cycle; redirecting them here instead sends back a 307 to the
  // /login *page* (HTML), which apiClient then fails to JSON.parse. That
  // previously broke every unauthenticated call, including
  // /api/auth/register and /api/auth/login themselves, before they ever
  // reached the backend. Auth for /api/* is enforced by the backend's
  // get_current_user (fail-closed, see app/core/auth_deps.py) regardless.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
