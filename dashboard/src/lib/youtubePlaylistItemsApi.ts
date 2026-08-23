/**
 * API client for the local YouTube playlist production tracker
 * (/api/youtube-playlists). These are locally-tracked "pending → published" video
 * ideas attached to a real YouTube playlist id — the real playlist is never written to.
 */

import { request as apiRequest } from "@/lib/apiClient";

// This module's routes live under /api/youtube-playlists rather than /api
// directly, so every call below prefixes this onto the shared apiClient path.
const BASE = "/youtube-playlists";

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

function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(`${BASE}${path}`, options);
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
