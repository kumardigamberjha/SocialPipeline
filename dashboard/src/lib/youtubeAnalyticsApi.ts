/**
 * API client for the YouTube analytics backend (/api/youtube-analytics).
 *
 * Strategy and roadmap runs are persisted server-side in `youtube_analyses`
 * (see app/routers/youtube_analytics.py::_save_analysis). A generated run is
 * therefore never lost — but the two shapes differ and callers should not have
 * to care:
 *
 *   POST /strategy|/roadmap  → the report itself, with `analysis_id` and
 *                              `created_at` stamped onto the top level.
 *   GET  /analyses/{id}      → a row, with the report nested under `payload`.
 *
 * `normalizeRun` folds both into one { data, analysisId, createdAt }.
 */

import { request } from "@/lib/apiClient";

const BASE = "/youtube-analytics";

// ── Types ────────────────────────────────────────────────────────────────────

export type AnalysisKind = "strategy" | "roadmap" | "ai_analysis";

export interface Strategy {
  verdict: string;
  whats_working: string[];
  underperforming: string[];
  format_insights: string[];
  content_gaps: string[];
  priorities: string[];
  model?: string;
}

export interface RoadmapItem {
  title: string;
  format: string;
  theme: string;
  rationale: string;
  date?: string;
}

export interface RoadmapWeek {
  week_number: number;
  start_date: string;
  focus: string;
  items: RoadmapItem[];
}

export interface Roadmap {
  cadence: string;
  weeks: RoadmapWeek[];
  model?: string;
}

/** What POST /roadmap/add-to-plan accepts for each selected roadmap item. */
export interface RoadmapItemPayload extends RoadmapItem {
  week_number: number;
}

export interface AddToPlanResult {
  plan_id: string | null;
  created: { id: string; topic: string; scheduled_date: string; publish_date: string | null }[];
  skipped: { title: string; reason: string }[];
  /** Where the dates came from: "channel_data" (real performance) or "roadmap_dates". */
  profile: { weekdays: number[] | null; event_time: string; source: string };
}

/** One past run, as listed by GET /analyses — metadata only, no payload. */
export interface AnalysisSummary {
  id: string;
  kind: AnalysisKind;
  time_range: string;
  weeks: number | null;
  model: string | null;
  created_at: string;
}

/** A full row from GET /analyses/{id} or /analyses/latest. */
export interface AnalysisRow extends AnalysisSummary {
  payload: unknown;
}

/** The uniform shape every caller in the UI works with. */
export interface AnalysisRun<T> {
  data: T;
  analysisId: string | null;
  createdAt: string | null;
}

// ── Shape normalization ──────────────────────────────────────────────────────

/**
 * Fold a POST response or a saved row into one shape.
 *
 * Returns null for the "nothing saved yet" case: /analyses/latest answers with
 * `{}` rather than 404, and `isEmpty` guards against restoring a run that has
 * no usable content (an old failed generation, say).
 */
export function normalizeRun<T>(
  raw: unknown,
  isEmpty: (data: T) => boolean,
): AnalysisRun<T> | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;

  // A saved row nests the report under `payload`; a fresh POST does not.
  const isRow = "payload" in record;
  const data = (isRow ? record.payload : record) as T;
  if (!data || typeof data !== "object" || isEmpty(data)) return null;

  const analysisId = (isRow ? record.id : record.analysis_id) as string | undefined;
  return {
    data,
    analysisId: analysisId ?? null,
    createdAt: (record.created_at as string | undefined) ?? null,
  };
}

export const isStrategyEmpty = (s: Strategy) =>
  !s.verdict && !(s.priorities?.length || s.whats_working?.length);

export const isRoadmapEmpty = (r: Roadmap) => !r.weeks?.length;

// ── Calls ────────────────────────────────────────────────────────────────────

export const youtubeAnalyticsApi = {
  generateStrategy: (timeRange: string, refresh: boolean) =>
    request<unknown>(`${BASE}/strategy?time_range=${timeRange}&refresh=${refresh}`, {
      method: "POST",
    }),

  generateRoadmap: (timeRange: string, weeks: number, refresh: boolean) =>
    request<unknown>(
      `${BASE}/roadmap?time_range=${timeRange}&weeks=${weeks}&refresh=${refresh}`,
      { method: "POST" },
    ),

  /** Newest saved run of `kind`, or `{}` when there is none yet. */
  latest: (kind: AnalysisKind, timeRange?: string) => {
    const qs = new URLSearchParams({ kind });
    if (timeRange) qs.set("time_range", timeRange);
    return request<unknown>(`${BASE}/analyses/latest?${qs}`);
  },

  /** Past runs, newest first. Metadata only — no payload. */
  history: (kind: AnalysisKind, limit = 20) =>
    request<AnalysisSummary[]>(`${BASE}/analyses?kind=${kind}&limit=${limit}`),

  byId: (analysisId: string) => request<AnalysisRow>(`${BASE}/analyses/${analysisId}`),

  /** Schedule roadmap items into the content planner. */
  addRoadmapToPlan: (body: {
    items: RoadmapItemPayload[];
    plan_id?: string;
    plan_name?: string;
    strategic?: boolean;
  }) =>
    request<AddToPlanResult>(`${BASE}/roadmap/add-to-plan`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  remove: (analysisId: string) =>
    request<{ message: string }>(`${BASE}/analyses/${analysisId}`, { method: "DELETE" }),
};
