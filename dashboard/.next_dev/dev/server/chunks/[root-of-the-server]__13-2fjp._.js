module.exports = [
"[externals]/next/dist/build/adapter/setup-node-env.external.js [external] (next/dist/build/adapter/setup-node-env.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/build/adapter/setup-node-env.external.js", () => require("next/dist/build/adapter/setup-node-env.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/lib/incremental-cache/tags-manifest.external.js [external] (next/dist/server/lib/incremental-cache/tags-manifest.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/lib/incremental-cache/tags-manifest.external.js", () => require("next/dist/server/lib/incremental-cache/tags-manifest.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/node:async_hooks [external] (node:async_hooks, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("node:async_hooks", () => require("node:async_hooks"));

module.exports = mod;
}),
"[externals]/path [external] (path, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("path", () => require("path"));

module.exports = mod;
}),
"[externals]/next/dist/server/lib/incremental-cache/memory-cache.external.js [external] (next/dist/server/lib/incremental-cache/memory-cache.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/lib/incremental-cache/memory-cache.external.js", () => require("next/dist/server/lib/incremental-cache/memory-cache.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/lib/incremental-cache/shared-cache-controls.external.js [external] (next/dist/server/lib/incremental-cache/shared-cache-controls.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/lib/incremental-cache/shared-cache-controls.external.js", () => require("next/dist/server/lib/incremental-cache/shared-cache-controls.external.js"));

module.exports = mod;
}),
"[externals]/crypto [external] (crypto, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("crypto", () => require("crypto"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[project]/src/proxy.ts [middleware] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "config",
    ()=>config,
    "proxy",
    ()=>proxy
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$middleware$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [middleware] (ecmascript)");
;
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
 */ const PUBLIC_PATHS = [
    "/login",
    "/signup"
];
const ACCESS_COOKIE_NAMES = [
    "nx_at",
    "__Host-nx_at"
];
const CSRF_COOKIE_NAME = "nx_csrf";
function isPublicPath(pathname) {
    if (PUBLIC_PATHS.includes(pathname)) return true;
    if (pathname.startsWith("/_next") || pathname === "/favicon.ico") return true;
    return false;
}
function proxy(request) {
    const { pathname, search } = request.nextUrl;
    const hasSessionCookie = ACCESS_COOKIE_NAMES.some((name)=>request.cookies.has(name)) || request.cookies.has(CSRF_COOKIE_NAME);
    // Already authenticated — bounce away from the auth pages to avoid the
    // user being stuck on /login after a successful login/signup call.
    if (isPublicPath(pathname)) {
        if (hasSessionCookie && (pathname === "/login" || pathname === "/signup")) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$middleware$5d$__$28$ecmascript$29$__["NextResponse"].redirect(new URL("/", request.url));
        }
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$middleware$5d$__$28$ecmascript$29$__["NextResponse"].next();
    }
    if (!hasSessionCookie) {
        const loginUrl = new URL("/login", request.url);
        loginUrl.searchParams.set("next", pathname + search);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$middleware$5d$__$28$ecmascript$29$__["NextResponse"].redirect(loginUrl);
    }
    return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$middleware$5d$__$28$ecmascript$29$__["NextResponse"].next();
}
const config = {
    // Run on page navigations only — never on /api/*. API calls are JSON
    // fetches handled by apiClient, which already has its own 401 -> refresh ->
    // redirect cycle; redirecting them here instead sends back a 307 to the
    // /login *page* (HTML), which apiClient then fails to JSON.parse. That
    // previously broke every unauthenticated call, including
    // /api/auth/register and /api/auth/login themselves, before they ever
    // reached the backend. Auth for /api/* is enforced by the backend's
    // get_current_user (fail-closed, see app/core/auth_deps.py) regardless.
    matcher: [
        "/((?!api|_next/static|_next/image|favicon.ico).*)"
    ]
};
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__13-2fjp._.js.map