/**
 * Client for the saved ("uncovered") topics backlog.
 *
 * Auto-research parks the candidate topics it did not generate here; this is
 * how the Topics page and the backlog banner read and act on them.
 */

import type { ContentType, GenerateType, ReviewStatus } from "./plannerApi";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API || "http://localhost:8000";
const API_BASE = `${BACKEND_URL}/api`;

// ── Types ────────────────────────────────────────────────────────────────────

// Re-exported so consumers import one module, not two.
export type { ContentType, GenerateType, ReviewStatus };

export type SavedTopicStatus = "uncovered" | "generating" | "generated";

export interface SavedTopicRun {
  id: string;
  content_type: ContentType;
  run_id: string | null;
  content_ref_id: string | null;
  review_status: ReviewStatus;
  created_at: string | null;
}

export interface SavedTopic {
  id: string;
  topic: string;
  rationale: string | null;
  niche: string | null;
  source: string | null;
  source_run_id: string | null;
  status: SavedTopicStatus;
  dismissed_at: string | null;
  generated_at: string | null;
  created_at: string | null;
  runs: SavedTopicRun[];
}

export interface SavedTopicSummary {
  uncovered_count: number;
  latest_created_at: string | null;
}

export interface HydratedContent extends SavedTopicRun {
  title: string | null;
  body: string | null;
  meta: Record<string, unknown>;
}

// ── Fetch helper ─────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data?.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return response.json();
}

// ── API ──────────────────────────────────────────────────────────────────────

/** Fired after auto-research saves new topics, so the banner can refetch
 *  without polling. Dispatched from ApprovalQueue's WebSocket handler. */
export const SAVED_TOPICS_UPDATED_EVENT = "saved-topics-updated";

export const savedTopicsApi = {
  listTopics: (status?: SavedTopicStatus, includeDismissed = false) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (includeDismissed) params.set("include_dismissed", "true");
    const qs = params.toString();
    return request<SavedTopic[]>(`/saved-topics${qs ? `?${qs}` : ""}`);
  },

  getSummary: () => request<SavedTopicSummary>("/saved-topics/summary"),

  createTopic: (topic: string, rationale?: string, niche = "ai") =>
    request<SavedTopic>("/saved-topics", {
      method: "POST",
      body: JSON.stringify({ topic, rationale, niche }),
    }),

  generate: (topicId: string, contentType: GenerateType, provider: string) =>
    request<{ dispatched: { content_type: ContentType; run_id: string; content_id: string }[]; topic: SavedTopic }>(
      `/saved-topics/${topicId}/generate`,
      { method: "POST", body: JSON.stringify({ content_type: contentType, provider }) },
    ),

  getContent: (topicId: string) => request<HydratedContent[]>(`/saved-topics/${topicId}/content`),

  dismiss: (topicId: string) =>
    request<SavedTopic>(`/saved-topics/${topicId}/dismiss`, { method: "POST" }),

  deleteTopic: (topicId: string) =>
    request<{ message: string }>(`/saved-topics/${topicId}`, { method: "DELETE" }),
};
