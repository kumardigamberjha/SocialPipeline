/**
 * API client for prospect channel audits (/api/youtube-prospects).
 *
 * A "prospect" is a channel the user does NOT own, looked up by name, @handle
 * or URL and run through the same analysis engine as their own channel. The
 * backend reuses `analyze_strategy` / `generate_roadmap` verbatim, so the
 * `audit` and `roadmap` payloads are the same `Strategy` and `Roadmap` shapes
 * the owner-channel screens already render — they are re-exported here rather
 * than redeclared so the two can never drift.
 *
 * Two-step by design: POST /lookup resolves the channel and costs nothing,
 * so the user confirms they have the right creator before POST /{id}/report
 * spends two LLM calls.
 */

import { request as apiRequest } from "@/lib/apiClient";
import type { Roadmap, Strategy } from "@/lib/youtubeAnalyticsApi";

export type { Roadmap, RoadmapItem, RoadmapWeek, Strategy } from "@/lib/youtubeAnalyticsApi";

const BASE = "/youtube-prospects";

function req<T>(path: string, options: RequestInit = {}) {
  return apiRequest<T>(`${BASE}${path}`, options);
}

export type ProspectStatus = "new" | "contacted" | "replied" | "archived";

export interface ProspectChannel {
  channel_id: string;
  title: string;
  handle: string | null;
  description: string | null;
  thumbnail_url: string | null;
  country: string | null;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  uploads_playlist_id?: string | null;
}

/**
 * One video-length bucket. Both statistics are carried deliberately: the
 * headline gate is struck on `median_views`, while the chart used to print
 * `avg_views` — the same bucket rendering as two different numbers on one page.
 * Anything that displays either one must label which it is.
 */
export interface BucketStats {
  count: number;
  avg_views: number;
  median_views: number;
  total_views: number;
}

export interface ProspectVideo {
  video_id: string;
  title: string;
  views: number;
  likes: number;
  published_at: string;
  duration_seconds: number;
  bucket: string;
}

export interface BreakoutVideo {
  video_id: string;
  title: string;
  views: number;
  likes: number;
  published_at: string;
  duration_seconds: number;
  bucket: string;
  multiplier: number;
}

export interface SimilarChannel {
  channel_id: string;
  title: string;
  handle: string;
  subscriber_count: number;
  thumbnail_url: string;
}

export interface OutreachHooks {
  primary: string;
  duration_hook?: string;
  breakout_hook?: string;
  cadence_hook?: string;
}

export interface TimeframeStat {
  days: number;
  label: string;
  uploads: number;
  views: number;
  uploads_views?: number;
  avg_views: number;
  long_form_count: number;
  shorts_count: number;
  est_earnings?: string;
  est_earnings_low?: number;
  est_earnings_high?: number;
  uploads_per_month?: number;
}

export interface TimeframeAnalytics {
  last_7d: TimeframeStat;
  last_28d: TimeframeStat;
  last_1y: TimeframeStat;
}

export interface KeywordStat {
  keyword: string;
  video_count: number;
  avg_views: number;
  total_views: number;
  multiplier: number;
  status: "high_demand" | "steady" | "underperforming";
  top_video_title?: string;
}

export interface KeywordAnalysis {
  top_keywords: KeywordStat[];
  underperforming_keywords?: KeywordStat[];
  avg_seo_score?: number | null;
}

export interface DayTimingStat {
  day: string;
  day_short: string;
  day_index: number;
  video_count: number;
  total_views: number;
  avg_views: number;
  multiplier: number;
  top_video_count: number;
  is_best: boolean;
}

export interface TimeSlotStat {
  slot: string;
  label: string;
  period: string;
  video_count: number;
  total_views: number;
  avg_views: number;
  multiplier: number;
  top_video_count: number;
}

export interface BestUploadWindow {
  best_days: string[];
  best_day_name: string;
  /** null when no window clears the sample floor, or when a check dropped it. */
  best_time_slot: string | null;
  best_slot_key: string | null;
  combined_label: string;
  /**
   * Day-of-week and time-of-day are independent computations and never share a
   * value — a time claim must never be backed by a day statistic. Both are
   * struck against the channel MEDIAN, not the average.
   */
  day_multiplier: number;
  slot_multiplier: number | null;
  day_lift_pct: number;
  slot_lift_pct: number;
  day_sample: number;
  slot_sample: number;
  day_confident: boolean;
  slot_confident: boolean;
  top_video_proof: string;
  /** Both sides counted from one list: proof_count <= top_tier_count, always. */
  proof_count: number;
  window_proof_count: number;
  top_tier_count: number;
  recommendation: string;
}

export interface TopTimingVideo {
  video_id: string;
  title: string;
  views: number;
  likes: number;
  published_at: string;
  day_name: string;
  day_short: string;
  time_utc: string;
  multiplier: number;
  /** Whether this video actually sits inside the recommended window. */
  in_best_window: boolean;
}

export interface UploadTimingAnalysis {
  has_timing_data: boolean;
  /** Enough clock data to be worth printing the hour breakdown table. */
  has_hour_data: boolean;
  /**
   * The one timing gate: whether an hour-level window may be *recommended*
   * anywhere in this report. Computed by
   * `youtube_metrics.time_of_day_recommendation_allowed` and closed again by the
   * validator if the window it produced did not survive its evidence check.
   * Every surface — this widget, the audit narrative, the priorities, the
   * roadmap — reads this one answer. Optional because reports cached before the
   * field existed will not carry it; `slot_confident` is the fallback.
   */
  time_of_day_allowed?: boolean;
  days: DayTimingStat[];
  time_slots: TimeSlotStat[];
  best_window: BestUploadWindow | null;
  top_timing_videos: TopTimingVideo[];
  /**
   * The exact list the report cites, so the UI and the validator agree about
   * what was held up as evidence. Optional because a report cached before this
   * field existed will not carry it; the UI falls back to the first N of
   * top_timing_videos, which is what the backend slice would have produced.
   */
  evidence_videos?: TopTimingVideo[];
}

/** A video old enough to judge that came in under the channel baseline. */
export interface FlaggedVideo {
  video_id: string;
  title: string;
  views: number;
  published_at: string;
  ratio: number | null;
}

/** A video too recently published to judge — measured at matched age instead. */
export interface FreshSignal {
  video_id: string;
  title: string;
  views: number;
  published_at: string;
  age_days: number;
  views_per_hour: number;
  peer_views_per_hour: number | null;
  ratio: number | null;
}

/** Sample floors, shipped so the UI never hardcodes a second copy. */
export interface ReportRules {
  top_breakout_n: number;
  min_slot_sample: number;
  min_day_sample: number;
  evidence_cited: number;
  fresh_upload_days: number;
  min_bucket_sample: number;
}

/** One internal contradiction found before render, and what was done about it. */
export interface IntegrityConflict {
  check: string;
  section: string;
  detail: string;
  action_taken: string;
}

/** The single authority on publishing rate and days. */
export interface ReportCadence {
  label: string;
  items_per_week: number;
  uploads_per_week: number;
  publish_days: string[];
  total_items: number;
}

export interface BreakoutClusterItem {
  keyword: string;
  count: number;
  total_breakouts: number;
  percentage: number;
  avg_views: number;
  avg_multiplier: number;
  matching_video_ids?: string[];
}

export interface BreakoutKeywordPattern {
  has_pattern: boolean;
  breakout_video_count: number;
  common_keywords: string[];
  cluster_title: string;
  pattern_summary: string;
  insight: string;
  hook_text: string;
  clusters: BreakoutClusterItem[];
}

export interface OutreachHooks {
  primary: string;
  duration_hook?: string;
  breakout_hook?: string;
  breakout_pattern_hook?: string;
  timing_hook?: string;
  cadence_hook?: string;
}

export interface ProspectMetrics {
  video_count_analyzed: number;
  duration_available: boolean;
  total_views?: number;
  avg_views?: number;
  median_views?: number;
  engagement_rate?: number | null;
  buckets: Record<string, BucketStats>;
  last_upload?: string;
  days_since_upload?: number | null;
  uploads_last_30?: number;
  uploads_last_90?: number;
  top_videos?: ProspectVideo[];
  recent_videos?: ProspectVideo[];
  keywords?: string[];
  avg_seo_title_score?: number | null;
  subscriber_count?: number;
  // vidIQ intelligence vitals
  long_form_count?: number;
  long_form_avg_views?: number;
  long_form_median_views?: number;
  long_form_total_views?: number;
  shorts_count?: number;
  shorts_avg_views?: number;
  shorts_median_views?: number;
  shorts_total_views?: number;
  avg_video_length_seconds?: number;
  avg_long_form_length_seconds?: number;
  uploads_per_week?: number;
  upload_frequency?: string;
  views_last_30d?: number;
  est_monthly_views?: number;
  est_monthly_earnings?: string;
  est_monthly_earnings_low?: number;
  est_monthly_earnings_high?: number;
  breakout_videos?: BreakoutVideo[];
  timeframe_analytics?: TimeframeAnalytics;
  keyword_analysis?: KeywordAnalysis;
  upload_timing?: UploadTimingAnalysis;
  breakout_patterns?: BreakoutKeywordPattern;
  flagged_videos?: FlaggedVideo[];
  fresh_signal?: FreshSignal[];
  rules?: ReportRules;
}

/**
 * The single comparison the outreach line makes. Computed in Python, never by
 * the model — `null` means the channel's data supported no honest claim, and
 * the UI must then show no outreach line rather than inventing one.
 */
export interface ProspectHeadline {
  kind: "duration_bucket" | "breakout_pattern" | "keyword" | "timing" | "cadence";
  label: string;
  value: number;
  /** Which statistic `value` is. Renderers must print this, never assume. */
  value_kind?: "median" | "average" | "days";
  /** The same slice's mean, so the banner and the length chart can agree. */
  avg_value?: number | null;
  baseline: number;
  baseline_kind?: "median" | "average" | "count";
  channel_avg_views?: number;
  sample: number;
  multiple: number | null;
}

/** Which rung of the LLM cascade produced a report.
 *
 * `grade` is the one field that matters to the UI: "client_grade" means the
 * report came from a primary model and may be printed, shared and exported;
 * "internal_only" means a fallback wrote it and the backend will refuse those
 * surfaces with a 409. The UI disables the buttons to match, but the server is
 * the enforcement — never the other way round.
 */
export interface ReportTier {
  index: number | null;
  name: string | null;
  grade: "client_grade" | "internal_only";
  /** Exact model string. Internal display only — never put in a client export. */
  model: string | null;
}

export interface ProspectReport {
  channel: ProspectChannel;
  metrics: ProspectMetrics;
  headline: ProspectHeadline | null;
  outreach_line: string;
  outreach_hooks?: OutreachHooks;
  similar_channels?: SimilarChannel[];
  audit: Strategy;
  roadmap: Roadmap;
  cadence?: ReportCadence;
  integrity?: { conflicts: IntegrityConflict[]; checked_at: string };
  duration_available: boolean;
  weeks?: number;
  generated_at?: string;
  model?: string;
  tier?: ReportTier;
  prospect_id?: string;
  outreach_status?: ProspectStatus;
}

/** A saved prospect row, as listed by GET "" — no report payload. */
export interface ProspectSummary {
  id: string;
  channel_id: string;
  title: string;
  handle: string | null;
  thumbnail_url: string | null;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  outreach_line: string | null;
  outreach_status: ProspectStatus;
  duration_available: boolean;
  last_report_at: string | null;
  created_at: string;
}

export const prospectsApi = {
  /** Resolve a channel. No LLM call, nothing persisted. */
  lookup: (query: string) =>
    req<{ channel: ProspectChannel }>("/lookup", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  generateReport: (channelId: string, params: { weeks?: number; refresh?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.weeks) qs.set("weeks", String(params.weeks));
    if (params.refresh) qs.set("refresh", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<ProspectReport>(`/${channelId}/report${suffix}`, { method: "POST" });
  },

  list: () => req<{ items: ProspectSummary[] }>(""),

  /** The latest saved report. 404s until one has been generated.
   *
   * `surface` tells the backend what the read is for. The client-facing
   * surfaces ("share", "print", "pdf") are refused with a 409 for a report a
   * fallback model wrote; "internal" always resolves, so the dashboard can show
   * the warning banner instead of an error page.
   */
  get: (channelId: string, surface: "internal" | "share" | "print" = "internal") =>
    req<ProspectReport>(`/${channelId}?surface=${surface}`),

  /** Rerun an internal_only audit on a primary tier. 503 if none is free. */
  regenerateOnPrimary: (channelId: string, weeks = 4) =>
    req<ProspectReport>(`/${channelId}/regenerate-on-primary?weeks=${weeks}`, {
      method: "POST",
    }),

  setStatus: (channelId: string, outreach_status: ProspectStatus) =>
    req<ProspectSummary>(`/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify({ outreach_status }),
    }),

  remove: (channelId: string) => req<{ deleted: boolean }>(`/${channelId}`, { method: "DELETE" }),
};

// ── Shared formatting ────────────────────────────────────────────────────────

export const fmtNum = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : n.toLocaleString();

export const fmtCompact = (n: number | null | undefined): string => {
  if (n === null || n === undefined) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
};

export const fmtDuration = (seconds: number | null | undefined): string => {
  if (!seconds || seconds <= 0) return "—";
  const mins = seconds / 60;
  if (mins < 1) return `${seconds}s`;
  if (mins >= 60) {
    const hrs = Math.floor(mins / 60);
    const remMins = Math.round(mins % 60);
    return `${hrs}h ${remMins}m`;
  }
  return `${mins.toFixed(1).replace(/\.0$/, "")} min`;
};

export const formatModelName = (rawModel: string | null | undefined): string => {
  if (!rawModel) return "Gemini 3.6 Flash";
  const clean = rawModel.split("#")[0].replace(/^gemini\//, "").trim();
  const lowered = clean.toLowerCase();
  if (lowered.includes("gemini-3.7-flash") || lowered.includes("gemini 3.7")) return "Gemini 3.7 Flash";
  if (lowered.includes("gemini-3.6-flash") || lowered.includes("gemini 3.6")) return "Gemini 3.6 Flash";
  if (lowered.includes("gemini-2.5-flash") || lowered.includes("gemini-1.5-flash")) return "Gemini 2.5 Flash";
  if (lowered.includes("gemini-3-pro") || lowered.includes("gemini-pro")) return "Gemini 3 Pro";
  if (lowered.includes("deepseek")) return "NVIDIA DeepSeek";
  if (lowered.includes("gemma")) return "Gemma 31B";
  if (lowered.includes("qwen")) return "Qwen 2.5";
  if (lowered.includes("groq") || lowered.includes("llama")) return "Groq LLaMA 3.3";
  return clean.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

export const fmtDate = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
};

/** Display order for the length buckets; mirrors youtube_metrics.DURATION_BUCKETS. */
export const BUCKET_ORDER = ["Shorts (<=1m)", "1-5 min", "5-15 min", "15-30 min", "30+ min"];

