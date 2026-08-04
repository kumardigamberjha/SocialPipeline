/**
 * API client for the content planner backend (/api/plans, /api/google).
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API || "http://localhost:8000";
const API_BASE = `${BACKEND_URL}/api`;

// ── Types ────────────────────────────────────────────────────────────────────

export type PlanType = "weekly" | "monthly";
export type ContentType = "linkedin" | "blog" | "youtube_script";
export type GenerateType = ContentType | "all";
export type VideoFormat = "short" | "full";
export type ProductionStatus =
  | "pending"
  | "script_generated"
  | "presentation_created"
  | "video_created"
  | "video_edited"
  | "video_published";
export type ReviewStatus = "generating" | "ready" | "approved" | "rejected" | "failed";

export const PRODUCTION_STATUSES: { value: ProductionStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "script_generated", label: "Script Generated" },
  { value: "presentation_created", label: "Presentation Created" },
  { value: "video_created", label: "Video Created" },
  { value: "video_edited", label: "Video Edited" },
  { value: "video_published", label: "Video Published" },
];

export interface ContentSummary {
  id: string;
  item_id: string;
  content_type: ContentType;
  run_id: string | null;
  content_ref_id: string | null;
  review_status: ReviewStatus;
  reviewed_at: string | null;
  created_at: string;
}

export interface ContentDetail extends ContentSummary {
  title: string | null;
  body: string | null;
  meta: Record<string, unknown>;
}

export interface PlanItem {
  id: string;
  plan_id: string;
  topic: string;
  scheduled_date: string;
  publish_date: string | null;
  event_time: string | null;
  event_duration_minutes: number | null;
  notes: string | null;
  topic_source: "ai" | "manual";
  video_format: VideoFormat;
  production_status: ProductionStatus;
  gcal_event_id: string | null;
  gcal_event_link: string | null;
  contents: ContentSummary[];
}

export interface Plan {
  id: string;
  name: string;
  plan_type: PlanType;
  niche: string;
  start_date: string;
  end_date: string;
  status: "active" | "archived";
  created_at: string;
  item_count?: number;
  published_count?: number;
}

export interface PlanDetail extends Plan {
  items: PlanItem[];
}

export interface SuggestedTopic {
  topic: string;
  rationale: string;
  scheduled_date: string;
}

export interface GoogleStatus {
  connected: boolean;
  email?: string;
  scopes?: string[];
}

// ── Analytics ────────────────────────────────────────────────────────────────

export interface PlannerStats {
  kpis: {
    total_plans: number;
    total_items: number;
    total_content: number;
    published_items: number;
    approval_rate: number;
    avg_gen_seconds: number;
  };
  plans: {
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    by_niche: Record<string, number>;
  };
  items_funnel: { status: ProductionStatus; count: number }[];
  items_by_format: Record<string, number>;
  items_by_source: Record<string, number>;
  content_by_type: Record<ContentType, number>;
  content_by_review: Record<ReviewStatus, number>;
  volume_over_time: { day: string; n: number }[];
  schedule: { published: number; overdue: number; upcoming: number };
  generation: Record<string, { count: number; avg_seconds: number }>;
  word_metrics: Record<ContentType, { count: number; total_words: number; avg_words: number }>;
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

export const plannerApi = {
  listPlans: () => request<Plan[]>("/plans"),

  getStats: () => request<PlannerStats>("/plans/stats"),

  getPlan: (planId: string) => request<PlanDetail>(`/plans/${planId}`),

  createPlan: (payload: {
    name: string;
    plan_type: PlanType;
    niche: string;
    start_date: string;
    items: { topic: string; scheduled_date: string; publish_date?: string | null; notes?: string | null; topic_source?: "ai" | "manual"; video_format?: VideoFormat }[];
  }) => request<PlanDetail>("/plans", { method: "POST", body: JSON.stringify(payload) }),

  updatePlan: (planId: string, payload: { name?: string; status?: "active" | "archived" }) =>
    request<Plan>(`/plans/${planId}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deletePlan: (planId: string) => request<{ message: string }>(`/plans/${planId}`, { method: "DELETE" }),

  suggestTopics: (payload: { plan_type: PlanType; niche: string; start_date: string; count?: number; provider?: string }) =>
    request<{ topics: SuggestedTopic[] }>("/plans/suggest-topics", { method: "POST", body: JSON.stringify(payload) }),

  addItem: (planId: string, payload: { topic: string; scheduled_date: string; publish_date?: string | null; notes?: string | null; topic_source?: "ai" | "manual"; video_format?: VideoFormat }) =>
    request<PlanItem>(`/plans/${planId}/items`, { method: "POST", body: JSON.stringify(payload) }),

  updateItem: (
    planId: string,
    itemId: string,
    payload: { topic?: string; scheduled_date?: string; publish_date?: string | null; event_time?: string | null; event_duration_minutes?: number | null; notes?: string; production_status?: ProductionStatus; video_format?: VideoFormat },
  ) => request<PlanItem>(`/plans/${planId}/items/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deleteItem: (planId: string, itemId: string) =>
    request<{ message: string }>(`/plans/${planId}/items/${itemId}`, { method: "DELETE" }),

  generateContent: (planId: string, itemId: string, contentType: GenerateType, provider: string) =>
    request<{ dispatched: { content_type: ContentType; run_id: string; content_id: string }[] }>(
      `/plans/${planId}/items/${itemId}/generate`,
      { method: "POST", body: JSON.stringify({ content_type: contentType, provider }) },
    ),

  getItemContent: (planId: string, itemId: string) =>
    request<ContentDetail[]>(`/plans/${planId}/items/${itemId}/content`),

  reviewContent: (contentId: string, action: "approve" | "reject", regenerate = false, provider?: string) =>
    request<{ content: ContentSummary; dispatched?: unknown[] }>(`/plans/content/${contentId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, regenerate, provider }),
    }),

  addToCalendar: (planId: string, itemId: string, eventTime?: string, durationMinutes?: number, remindersMinutes?: number[]) =>
    request<{ event_id: string; event_link: string }>(`/plans/${planId}/items/${itemId}/calendar`, {
      method: "POST",
      body: JSON.stringify({
        reminders_minutes: remindersMinutes ?? [1440, 60],
        event_time: eventTime ?? null,
        event_duration_minutes: durationMinutes ?? null,
      }),
    }),

  googleStatus: () => request<GoogleStatus>("/google/status"),

  googleAuthorizeUrl: () => request<{ authorization_url: string }>("/google/authorize"),

  googleDisconnect: () => request<{ message: string }>("/google/disconnect", { method: "DELETE" }),
};
