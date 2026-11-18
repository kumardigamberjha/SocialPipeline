module.exports = [
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[project]/src/lib/config.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

/**
 * The single source of truth for the backend's base URL.
 *
 * In development, Next.js proxies /api/* to the FastAPI backend via rewrites
 * in next.config.ts — so all API calls go through the *same* Next.js origin
 * (localhost:3000).  That means cookies set by login/register are on the same
 * origin the browser is already on, and both the proxy.ts auth guard and the
 * browser's credential store agree on the cookie.
 *
 * Set NEXT_PUBLIC_BACKEND_API to a full URL only in environments where the
 * API is NOT proxied through Next.js (e.g. a separate Docker service with a
 * shared domain via a reverse proxy).
 */ __turbopack_context__.s([
    "API_BASE_URL",
    ()=>API_BASE_URL,
    "BACKEND_URL",
    ()=>BACKEND_URL,
    "wsOrigin",
    ()=>wsOrigin
]);
const BACKEND_URL = ("TURBOPACK compile-time value", "") ?? "";
const API_BASE_URL = `${BACKEND_URL}/api`;
function wsOrigin() {
    // Explicit override (production wss:// address or custom dev setup).
    const override = process.env.NEXT_PUBLIC_WS_ORIGIN;
    if (override) return override;
    // BACKEND_URL is a full URL (non-proxied deployment) — derive WS from it.
    if (BACKEND_URL.startsWith("https")) return BACKEND_URL.replace(/^https/, "wss");
    if (BACKEND_URL.startsWith("http")) return BACKEND_URL.replace(/^http/, "ws");
    if ("TURBOPACK compile-time falsy", 0) //TURBOPACK unreachable
    ;
    return "ws://localhost:8001";
}
}),
"[project]/src/lib/apiClient.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ApiError",
    ()=>ApiError,
    "apiClient",
    ()=>apiClient,
    "request",
    ()=>request,
    "requestBlob",
    ()=>requestBlob,
    "trySilentRefresh",
    ()=>trySilentRefresh
]);
/**
 * The one HTTP client for the backend. Every other API module
 * (plannerApi, savedTopicsApi, youtubePlaylistItemsApi, and the inline
 * `fetch` calls scattered across the Instagram/YouTube dashboards) used to
 * carry its own copy of this logic — or, for the plain components, none of
 * it at all, silently sending unauthenticated requests.
 *
 * What this centralizes:
 *   - `credentials: "include"` on every request, so the session cookies
 *     (httpOnly `nx_at`/`nx_rt` + readable `nx_csrf`) are actually sent.
 *   - The `X-CSRF-Token` header, read from the `nx_csrf` cookie, attached to
 *     every mutating request (the backend's CSRFMiddleware requires it).
 *   - A single-flight 401 -> `/api/auth/refresh` -> retry-once interceptor.
 *     Without the single-flight guard, ten components each hitting a stale
 *     access token at once would fire ten concurrent refresh calls, and the
 *     refresh-token rotation model treats the second one as a replay and
 *     revokes the whole session.
 *   - A hard redirect to `/login` when the refresh itself fails, since at
 *     that point there is no session left to recover.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$config$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/config.ts [app-ssr] (ecmascript)");
;
class ApiError extends Error {
    status;
    constructor(message, status){
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}
function readCookie(name) {
    if (typeof document === "undefined") return null;
    const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&")}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
}
function csrfHeaders(method) {
    const m = method.toUpperCase();
    if (m === "GET" || m === "HEAD" || m === "OPTIONS") return {};
    const token = readCookie("nx_csrf");
    return token ? {
        "X-CSRF-Token": token
    } : {};
}
// Single-flight refresh: concurrent 401s share one in-flight refresh call
// instead of each triggering their own (which would race the refresh-token
// rotation and revoke the session — see module docstring).
let refreshInFlight = null;
async function refreshSession() {
    if (!refreshInFlight) {
        refreshInFlight = fetch(`${__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$config$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["API_BASE_URL"]}/auth/refresh`, {
            method: "POST",
            credentials: "include"
        }).then((r)=>r.ok).catch(()=>false).finally(()=>{
            refreshInFlight = null;
        });
    }
    return refreshInFlight;
}
async function trySilentRefresh() {
    return refreshSession();
}
function redirectToLogin() {
    if ("TURBOPACK compile-time truthy", 1) return;
    //TURBOPACK unreachable
    ;
    const next = undefined;
}
async function parseErrorDetail(response) {
    let detail = `Request failed (${response.status})`;
    try {
        const data = await response.json();
        if (data?.detail) {
            detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        }
    } catch  {
    /* non-JSON error body */ }
    return detail;
}
async function request(path, options = {}) {
    const { skipAuthRetry, ...init } = options;
    const method = init.method ?? "GET";
    const normalizedPath = path.startsWith("/api/") ? path.slice(4) : path;
    const doFetch = ()=>fetch(`${__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$config$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["API_BASE_URL"]}${normalizedPath}`, {
            ...init,
            credentials: "include",
            headers: {
                "Content-Type": "application/json",
                ...csrfHeaders(method),
                ...init.headers ?? {}
            }
        });
    let response = await doFetch();
    if (response.status === 401 && !skipAuthRetry) {
        const refreshed = await refreshSession();
        if (refreshed) {
            response = await doFetch();
        } else {
            redirectToLogin();
            throw new ApiError("Session expired", 401);
        }
    }
    if (!response.ok) {
        if (response.status === 401 && !skipAuthRetry) {
            redirectToLogin();
        }
        throw new ApiError(await parseErrorDetail(response), response.status);
    }
    // 204 / empty-body responses (e.g. some DELETE endpoints).
    const text = await response.text();
    return text ? JSON.parse(text) : undefined;
}
async function requestBlob(path, options = {}) {
    const { skipAuthRetry, ...init } = options;
    const doFetch = ()=>fetch(`${__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$config$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["API_BASE_URL"]}${path}`, {
            ...init,
            credentials: "include",
            headers: {
                ...csrfHeaders(init.method ?? "GET"),
                ...init.headers ?? {}
            }
        });
    let response = await doFetch();
    if (response.status === 401 && !skipAuthRetry) {
        if (await refreshSession()) {
            response = await doFetch();
        } else {
            redirectToLogin();
            throw new ApiError("Session expired", 401);
        }
    }
    if (!response.ok) {
        if (response.status === 401 && !skipAuthRetry) redirectToLogin();
        throw new ApiError(await parseErrorDetail(response), response.status);
    }
    return response.blob();
}
const apiClient = {
    request,
    requestBlob
};
}),
"[project]/src/lib/auth/AuthContext.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AuthProvider",
    ()=>AuthProvider,
    "useAuth",
    ()=>useAuth
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
/**
 * Session state for the whole dashboard.
 *
 * Bootstraps from `GET /api/auth/me` on mount (the cookie, if any, is sent
 * automatically). There is no token anywhere in this file — the browser
 * carries the session via httpOnly cookies, and this context only tracks
 * *whether* one is live, never a credential itself.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/apiClient.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
const AuthContext = /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["createContext"])(null);
function AuthProvider({ children }) {
    const [user, setUser] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [loading, setLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(true);
    const bootstrap = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async ()=>{
        try {
            // A 401 here is a normal, expected "not signed in" — never send this
            // through the apiClient's refresh/redirect cycle, or a fresh visitor
            // gets bounced through /login before they've done anything.
            const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/me", {
                skipAuthRetry: true
            });
            setUser(data.user);
        } catch  {
            // The access token is short-lived (15 min) and expires constantly just
            // from a tab sitting in the background — that alone isn't "logged out"
            // as long as the 30-day refresh cookie is still valid. Try one silent
            // refresh before concluding there's no session, so returning to a tab
            // doesn't bounce a still-valid session to the login screen.
            try {
                const refreshed = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["trySilentRefresh"])();
                if (refreshed) {
                    const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/me", {
                        skipAuthRetry: true
                    });
                    setUser(data.user);
                    return;
                }
            } catch  {
            /* fall through to logged-out */ }
            setUser(null);
        } finally{
            setLoading(false);
        }
    }, []);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        bootstrap();
    }, [
        bootstrap
    ]);
    const login = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async (email, password)=>{
        const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/login", {
            method: "POST",
            body: JSON.stringify({
                email,
                password
            }),
            skipAuthRetry: true
        });
        setUser(data.user);
    }, []);
    /**
   * Register a new account.
   * Returns { email } — does NOT set the user or issue a session.
   * The caller should show an OTP entry step next.
   */ const signup = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async (email, password)=>{
        const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/register", {
            method: "POST",
            body: JSON.stringify({
                email,
                password
            }),
            skipAuthRetry: true
        });
        return {
            email: data.email
        };
    }, []);
    /** Submit the OTP received by email. On success sets the user (session issued). */ const verifyEmail = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async (email, otp)=>{
        const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/verify-email", {
            method: "POST",
            body: JSON.stringify({
                email,
                otp
            }),
            skipAuthRetry: true
        });
        setUser(data.user);
    }, []);
    /** Request a fresh OTP for the given email. */ const resendOtp = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async (email)=>{
        await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/resend-otp", {
            method: "POST",
            body: JSON.stringify({
                email
            }),
            skipAuthRetry: true
        });
    }, []);
    const logout = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async ()=>{
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["request"])("/auth/logout", {
                method: "POST",
                skipAuthRetry: true
            });
        } catch (err) {
            // Cookies may already be gone (e.g. expired) — that is still "logged
            // out" from the UI's perspective, so swallow anything but a genuine
            // network failure.
            if (!(err instanceof __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$apiClient$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ApiError"])) throw err;
        } finally{
            setUser(null);
        }
    }, []);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(AuthContext.Provider, {
        value: {
            user,
            loading,
            login,
            signup,
            verifyEmail,
            resendOtp,
            logout,
            refresh: bootstrap,
            setUser
        },
        children: children
    }, void 0, false, {
        fileName: "[project]/src/lib/auth/AuthContext.tsx",
        lineNumber: 147,
        columnNumber: 5
    }, this);
}
function useAuth() {
    const ctx = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useContext"])(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
    return ctx;
}
}),
"[project]/src/app/providers.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "Providers",
    ()=>Providers
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$auth$2f$AuthContext$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/auth/AuthContext.tsx [app-ssr] (ecmascript)");
"use client";
;
;
function Providers({ children }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$auth$2f$AuthContext$2e$tsx__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AuthProvider"], {
        children: children
    }, void 0, false, {
        fileName: "[project]/src/app/providers.tsx",
        lineNumber: 8,
        columnNumber: 10
    }, this);
}
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/action-async-storage.external.js [external] (next/dist/server/app-render/action-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/action-async-storage.external.js", () => require("next/dist/server/app-render/action-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/dynamic-access-async-storage.external.js [external] (next/dist/server/app-render/dynamic-access-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/dynamic-access-async-storage.external.js", () => require("next/dist/server/app-render/dynamic-access-async-storage.external.js"));

module.exports = mod;
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__0etu0c8._.js.map