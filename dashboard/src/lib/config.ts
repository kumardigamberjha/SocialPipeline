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
 */
export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API ?? "";
export const API_BASE_URL = `${BACKEND_URL}/api`;

/**
 * WebSocket origin: must point directly at FastAPI because Next.js rewrites
 * cannot proxy WebSocket connections.  In development this is the backend port
 * directly; in production set NEXT_PUBLIC_WS_ORIGIN to the wss:// address.
 */
export function wsOrigin(): string {
  // Explicit override (production wss:// address or custom dev setup).
  const override = process.env.NEXT_PUBLIC_WS_ORIGIN;
  if (override) return override;

  // BACKEND_URL is a full URL (non-proxied deployment) — derive WS from it.
  if (BACKEND_URL.startsWith("https")) return BACKEND_URL.replace(/^https/, "wss");
  if (BACKEND_URL.startsWith("http")) return BACKEND_URL.replace(/^http/, "ws");

  // BACKEND_URL is empty (Next.js-proxied) — WS must bypass the proxy and go
  // directly to the FastAPI port.  Fall back to 8001 in SSR/build contexts.
  if (typeof window !== "undefined") {
    // In development Next.js runs on 3000; FastAPI is on 8001.
    return `ws://127.0.0.1:8001`;
  }
  return "ws://127.0.0.1:8001";
}
