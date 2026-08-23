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
 */

import { API_BASE_URL } from "./config";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&")}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

function csrfHeaders(method: string): Record<string, string> {
  const m = method.toUpperCase();
  if (m === "GET" || m === "HEAD" || m === "OPTIONS") return {};
  const token = readCookie("nx_csrf");
  return token ? { "X-CSRF-Token": token } : {};
}

// Single-flight refresh: concurrent 401s share one in-flight refresh call
// instead of each triggering their own (which would race the refresh-token
// rotation and revoke the session — see module docstring).
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/**
 * Attempt a silent refresh without the request()/redirect-to-login machinery.
 * Used by auth bootstrap: an expired access token on mount (e.g. the tab was
 * merely backgrounded past its 15-minute TTL) should transparently recover
 * the session from the refresh cookie, not be treated as "logged out".
 */
export async function trySilentRefresh(): Promise<boolean> {
  return refreshSession();
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/login?next=${next}`;
}

async function parseErrorDetail(response: Response): Promise<string> {
  let detail = `Request failed (${response.status})`;
  try {
    const data = await response.json();
    if (data?.detail) {
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    }
  } catch {
    /* non-JSON error body */
  }
  return detail;
}

export interface RequestOptions extends RequestInit {
  /** Skip the 401 -> refresh -> retry cycle (used by the refresh call itself
   * and by auth bootstrap, where a 401 is an expected, valid outcome). */
  skipAuthRetry?: boolean;
}

/**
 * `path` is relative to `/api` (e.g. `/plans`, `/youtube-analytics/stats`).
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuthRetry, ...init } = options;
  const method = init.method ?? "GET";

  const doFetch = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeaders(method),
        ...(init.headers ?? {}),
      },
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
  return (text ? JSON.parse(text) : undefined) as T;
}

export const apiClient = { request };
