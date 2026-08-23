/**
 * API client for the content planner backend (/api/plans, /api/google).
 */

import { request } from "@/lib/apiClient";
import { API_BASE_URL } from "@/lib/config";

// ── Types ────────────────────────────────────────────────────────────────────

export type PlanType = "weekly" | "monthly" | "board";

/**
 * The channel a plan belongs to. Adding one here plus an entry in PLATFORMS is
 * the whole cost of a new platform — the backend needs no migration.
 */
export type Platform = "youtube" | "instagram" | "linkedin" | "blog" | "x" | "tiktok";

export const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
];
export type ContentType = "linkedin" | "blog" | "youtube_script";
export type GenerateType = ContentType | "all";
export type VideoFormat = "short" | "full";
export type ProductionStatus =
  // YouTube's video pipeline…
  | "pending"
  | "script_generated"
  | "presentation_created"
  | "video_created"
  | "video_edited"
  | "video_published"
  // …and the plain board every other platform uses. Stored verbatim rather
  // than mapped onto the stages above, so neither vocabulary is lossy.
  | "idea"
  | "in_production"
  | "scheduled"
  | "published";
export type ReviewStatus = "generating" | "ready" | "approved" | "rejected" | "failed";

export const PRODUCTION_STATUSES: { value: ProductionStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "script_generated", label: "Script Generated" },
  { value: "presentation_created", label: "Presentation Created" },
  { value: "video_created", label: "Video Created" },
  { value: "video_edited", label: "Video Edited" },
  { value: "video_published", label: "Video Published" },
];

export const BOARD_STATUSES: { value: ProductionStatus; label: string }[] = [
  { value: "idea", label: "Idea" },
  { value: "in_production", label: "In Production" },
  { value: "scheduled", label: "Scheduled" },
  { value: "published", label: "Published" },
];

/** Only YouTube runs the full video pipeline; mirrors VIDEO_PLATFORMS server-side. */
export const isVideoPlatform = (platform: Platform) => platform === "youtube";

export const statusesFor = (platform: Platform) =>
  isVideoPlatform(platform) ? PRODUCTION_STATUSES : BOARD_STATUSES;

/**
 * The coarse bucket a status belongs to, for filters and counters that must
 * work on either vocabulary.
 *
 * Total by construction: every ProductionStatus maps to a bucket, so filtering
 * can never make an item disappear. Ported from the server-side collapse table
 * (`board_compat._TO_BOARD_STATUS`) that the Instagram board shim used before
 * the frontend cut over to this planner; that shim is gone, so this is now the
 * only copy of the mapping.
 */
const STATUS_BUCKET: Record<ProductionStatus, StatusBucket> = {
  // Video pipeline…
  pending: "todo",
  script_generated: "in_production",
  presentation_created: "in_production",
  video_created: "in_production",
  video_edited: "in_production",
  video_published: "published",
  // …and the generic board.
  idea: "todo",
  in_production: "in_production",
  scheduled: "in_production",
  published: "published",
};

export type StatusBucket = "todo" | "in_production" | "published";

export const bucketOf = (status: ProductionStatus): StatusBucket =>
  STATUS_BUCKET[status] ?? "todo";

/** Bucket labels differ per vocabulary — "Pending" vs "Idea" reads very differently. */
export const bucketLabels = (
  platform: Platform,
): Record<StatusBucket, string> =>
  isVideoPlatform(platform)
    ? { todo: "Pending", in_production: "In Production", published: "Published" }
    : { todo: "Ideas", in_production: "In Progress", published: "Published" };

/** Content generation only exists for platforms the pipelines can produce for. */
export const canGenerate = (platform: Platform) =>
  platform === "youtube" || platform === "linkedin" || platform === "blog";

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
  /** Null for an undated backlog idea. */
  scheduled_date: string | null;
  publish_date: string | null;
  platform: Platform;
  /** Platform-specific fields: caption, image_prompt, slides_count, metrics… */
  meta: Record<string, unknown>;
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

/** The Instagram-specific half of `plan_items.meta`. */
export interface InstagramMeta {
  type: "reel" | "carousel" | "single" | "story";
  caption: string;
  image_prompt: string;
  slides_count: number;
  /** Set by POST /plans/{id}/items/{id}/image; the file is served back by GET. */
  image_file?: string;
  likes?: number;
  shares?: number;
  saves?: number;
  reach?: number;
}

export const INSTAGRAM_POST_TYPES: InstagramMeta["type"][] = [
  "reel",
  "carousel",
  "single",
  "story",
];

/** Read Instagram fields out of the untyped meta bag, with the same defaults
 *  the old board applied (carousels default to 7 slides). */
export function instagramMeta(meta: Record<string, unknown>): InstagramMeta {
  const type = (
    INSTAGRAM_POST_TYPES.includes(meta.type as InstagramMeta["type"])
      ? meta.type
      : "reel"
  ) as InstagramMeta["type"];
  const num = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);
  return {
    type,
    caption: typeof meta.caption === "string" ? meta.caption : "",
    image_prompt: typeof meta.image_prompt === "string" ? meta.image_prompt : "",
    slides_count: num(meta.slides_count) || (type === "carousel" ? 7 : 1),
    image_file: typeof meta.image_file === "string" ? meta.image_file : undefined,
    likes: num(meta.likes),
    shares: num(meta.shares),
    saves: num(meta.saves),
    reach: num(meta.reach),
  };
}

/** Only Instagram items can have an image generated for them today. */
export const canGenerateImage = (platform: Platform) => platform === "instagram";

export interface Plan {
  id: string;
  name: string;
  plan_type: PlanType;
  platform: Platform;
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

/** GET /plans/board — items plus the platform's Kanban column order. */
export interface BoardResponse {
  platform: Platform;
  plan_id: string | null;
  statuses: ProductionStatus[];
  items: PlanItem[];
}

export interface SuggestedTopic {
  topic: string;
  rationale: string;
  scheduled_date: string;
  /** Platform-specific extras to carry into plan_items.meta (Instagram's
   *  type / caption / image_prompt); empty for YouTube. */
  meta?: Record<string, unknown>;
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

// ── API ──────────────────────────────────────────────────────────────────────
//
// `request()` (cookies + CSRF + refresh-on-401) now lives in apiClient.ts —
// this file previously carried its own copy, reading a bearer token from
// localStorage that nothing in the app ever wrote there.

/** One draft item as POSTed to the server; shared by createPlan and addItem. */
export interface PlanItemInput {
  topic: string;
  scheduled_date: string | null;
  publish_date?: string | null;
  notes?: string | null;
  topic_source?: "ai" | "manual";
  video_format?: VideoFormat;
  /** Platform-specific fields (Instagram: type, caption, image_prompt, slides_count). */
  meta?: Record<string, unknown>;
}

export const plannerApi = {
  /** Omit `platform` for every plan across all platforms. */
  listPlans: (platform?: Platform) =>
    request<Plan[]>(`/plans${platform ? `?platform=${platform}` : ""}`),

  /** Kanban read: every item on a platform, plus its column order. */
  getBoard: (platform: Platform, planId?: string) => {
    const qs = new URLSearchParams({ platform });
    if (planId) qs.set("plan_id", planId);
    return request<BoardResponse>(`/plans/board?${qs}`);
  },

  /** Cross-plan calendar feed for one platform. */
  listItems: (platform: Platform, dateFrom?: string, dateTo?: string) => {
    const qs = new URLSearchParams({ platform });
    if (dateFrom) qs.set("date_from", dateFrom);
    if (dateTo) qs.set("date_to", dateTo);
    return request<PlanItem[]>(`/plans/items?${qs}`);
  },

  getStats: (platform?: Platform) =>
    request<PlannerStats>(`/plans/stats${platform ? `?platform=${platform}` : ""}`),

  getPlan: (planId: string) => request<PlanDetail>(`/plans/${planId}`),

  createPlan: (payload: {
    name: string;
    plan_type: PlanType;
    niche: string;
    start_date: string;
    /** Omitting this used to silently create the plan as YouTube. */
    platform: Platform;
    items: PlanItemInput[];
  }) => request<PlanDetail>("/plans", { method: "POST", body: JSON.stringify(payload) }),

  updatePlan: (planId: string, payload: { name?: string; status?: "active" | "archived" }) =>
    request<Plan>(`/plans/${planId}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deletePlan: (planId: string) => request<{ message: string }>(`/plans/${planId}`, { method: "DELETE" }),

  /** `platform` picks the grounding: YouTube's channel history, or Instagram's
   *  synced account data. Without it the server defaults to YouTube. */
  suggestTopics: (payload: { plan_type: PlanType; niche: string; start_date: string; platform: Platform; count?: number; provider?: string }) =>
    request<{ topics: SuggestedTopic[] }>("/plans/suggest-topics", { method: "POST", body: JSON.stringify(payload) }),

  addItem: (planId: string, payload: PlanItemInput) =>
    request<PlanItem>(`/plans/${planId}/items`, { method: "POST", body: JSON.stringify(payload) }),

  updateItem: (
    planId: string,
    itemId: string,
    // `meta` is shallow-merged server-side — send only the keys that changed.
    payload: { topic?: string; scheduled_date?: string; publish_date?: string | null; event_time?: string | null; event_duration_minutes?: number | null; notes?: string; production_status?: ProductionStatus; video_format?: VideoFormat; meta?: Record<string, unknown> },
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

  /** Render the item's image via Gemini. Returns base64 for an immediate
   *  preview plus the stored filename, which later loads fetch by URL. */
  generateImage: (planId: string, itemId: string, payload?: { prompt?: string; model?: string }) =>
    request<{ image_file: string; image_b64: string; model: string; duration_s: number }>(
      `/plans/${planId}/items/${itemId}/image`,
      { method: "POST", body: JSON.stringify(payload ?? {}) },
    ),

  /** Owner-scoped URL for an already-generated image; `<img src>` sends cookies. */
  itemImageUrl: (planId: string, itemId: string) =>
    `${API_BASE_URL}/plans/${planId}/items/${itemId}/image`,

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
