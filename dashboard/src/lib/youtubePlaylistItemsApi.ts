/**
 * API client for the local YouTube playlist production tracker
 * (/api/youtube-playlists). These are locally-tracked "pending → published" video
 * ideas attached to a real YouTube playlist id — the real playlist is never written to.
 */

const BACKEND_URL = "http://localhost:8000";
const API_BASE = `${BACKEND_URL}/api/youtube-playlists`;

export type VideoFormat = "short" | "full";
export type ProductionStatus =
  | "pending"
  | "script_generated"
  | "presentation_created"
  | "video_created"
  | "video_edited"
  | "video_published";

export const PRODUCTION_STATUSES: { value: ProductionStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "script_generated", label: "Script Generated" },
  { value: "presentation_created", label: "Presentation Created" },
  { value: "video_created", label: "Video Created" },
  { value: "video_edited", label: "Video Edited" },
  { value: "video_published", label: "Video Published" },
];

export interface YoutubePlaylistItem {
  id: string;
  user_id: string;
  playlist_id: string;
  playlist_title: string | null;
  title: string;
  description: string | null;
  video_format: VideoFormat;
  scheduled_date: string | null;
  publish_date: string | null;
  production_status: ProductionStatus;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface AddItemPayload {
  playlist_id: string;
  playlist_title?: string | null;
  title: string;
  description?: string | null;
  video_format?: VideoFormat;
  scheduled_date?: string | null;
  publish_date?: string | null;
  source?: string;
}

export interface UpdateItemPayload {
  title?: string;
  description?: string | null;
  video_format?: VideoFormat;
  scheduled_date?: string | null;
  publish_date?: string | null;
  production_status?: ProductionStatus;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const playlistItemsApi = {
  list: (playlistId?: string) =>
    request<YoutubePlaylistItem[]>(
      `/items${playlistId ? `?playlist_id=${encodeURIComponent(playlistId)}` : ""}`,
    ),

  add: (payload: AddItemPayload) =>
    request<YoutubePlaylistItem>("/items", { method: "POST", body: JSON.stringify(payload) }),

  update: (itemId: string, payload: UpdateItemPayload) =>
    request<YoutubePlaylistItem>(`/items/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) }),

  remove: (itemId: string) =>
    request<{ message: string }>(`/items/${itemId}`, { method: "DELETE" }),
};
