/**
 * API client for YouTube competitor tracking (/api/youtube-competitors).
 *
 * Discovery is async-in-request (not a Celery job today): POST /discover
 * runs the LLM-propose + YouTube-verify loop inline and returns the finished
 * run. Approved competitors are excluded from every future discovery run,
 * in any status (approved/rejected/archived) — see the backend's
 * filter_known_competitor_ids.
 */

import { request as apiRequest } from "@/lib/apiClient";

const BASE = "/youtube-competitors";

export type CompetitorStatus = "approved" | "rejected" | "archived";
export type CompetitorTier = "peer" | "aspirational" | "adjacent";

export interface CompetitorCandidate {
  channel_id: string;
  title: string;
  handle: string;
  description: string;
  thumbnail_url: string | null;
  uploads_playlist_id: string | null;
  country: string | null;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  rationale: string;
  tier: CompetitorTier;
  niche?: string;
}

export interface DiscoveryRun {
  id: string;
  user_id: string;
  niche: string;
  status: "pending" | "applied" | "discarded";
  candidates: CompetitorCandidate[];
  approved_count: number;
  rejected_count: number;
  quota_units_spent: number;
  created_at: string;
  decided_at: string | null;
}

export interface Competitor {
  user_id: string;
  channel_id: string;
  title: string;
  handle: string | null;
  description: string | null;
  thumbnail_url: string | null;
  uploads_playlist_id: string | null;
  country: string | null;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  niche: string | null;
  relevance_score: number;
  rationale: string | null;
  tags: string[] | null;
  status: CompetitorStatus;
  priority: number;
  discovered_by: "llm" | "manual";
  source_run_id: string | null;
  last_synced_at: string | null;
  sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompetitorVideo {
  video_id: string;
  channel_id: string;
  title: string;
  description: string | null;
  published_at: string | null;
  duration_seconds: number;
  is_short: boolean;
  views: number;
  likes: number;
  comments: number;
  tags: string[] | null;
  thumbnail_url: string | null;
  fetched_at: string;
}

export interface CompetitorDetail extends Competitor {
  videos: CompetitorVideo[];
}

export interface CompetitorListPage {
  items: Competitor[];
  next_cursor: string | null;
}

export interface ApproveResult {
  approved: number;
  rejected: number;
  videos_synced: number;
}

export interface CompetitorVideoPage {
  items: (CompetitorVideo & {
    channel_title?: string;
    channel_thumbnail?: string;
    channel_handle?: string;
  })[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(`${BASE}${path}`, options);
}

export const competitorsApi = {
  discover: (params: { niche?: string; count?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.niche) qs.set("niche", params.niche);
    if (params.count) qs.set("count", String(params.count));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<DiscoveryRun>(`/discover${suffix}`, { method: "POST" });
  },

  getRun: (runId: string) => req<DiscoveryRun>(`/discover/${runId}`),

  approve: (runId: string, approved: string[], rejected: string[]) =>
    req<ApproveResult>(`/discover/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved, rejected }),
    }),

  list: (
    params: { cursor?: string | null; limit?: number; status?: CompetitorStatus; q?: string } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.cursor) qs.set("cursor", params.cursor);
    if (params.limit) qs.set("limit", String(params.limit));
    qs.set("status", params.status ?? "approved");
    if (params.q) qs.set("q", params.q);
    return req<CompetitorListPage>(`?${qs.toString()}`);
  },

  listVideos: (params: { page?: number; per_page?: number; channel_id?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set("page", String(params.page));
    if (params.per_page) qs.set("per_page", String(params.per_page));
    if (params.channel_id) qs.set("channel_id", params.channel_id);
    return req<CompetitorVideoPage>(`/videos?${qs.toString()}`);
  },

  summary: () => req<{ approved: number; rejected: number }>("/summary"),

  get: (channelId: string) => req<CompetitorDetail>(`/${channelId}`),

  update: (channelId: string, payload: { status?: CompetitorStatus; priority?: number }) =>
    req<Competitor>(`/${channelId}`, { method: "PATCH", body: JSON.stringify(payload) }),

  remove: (channelId: string) =>
    req<{ message: string }>(`/${channelId}`, { method: "DELETE" }),

  sync: (channelId: string) =>
    req<{ synced: number; quota_units: number }>(`/${channelId}/sync`, { method: "POST" }),

  add: (payload: { channel_id?: string; handle?: string }) =>
    req<Competitor>("", { method: "POST", body: JSON.stringify(payload) }),
};

