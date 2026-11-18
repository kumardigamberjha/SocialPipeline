import { request } from "./apiClient";

export type ShortFormPlatform = "youtube" | "instagram" | "tiktok";
export type ProspectStatus = "new" | "contacted" | "replied" | "archived";

export interface ShortFormProfile {
  platform: ShortFormPlatform;
  identifier: string;
  title: string;
  handle: string;
  avatar_url?: string | null;
  followers_or_subs: number;
  total_videos_or_posts: number;
  bio?: string | null;
  profile_url?: string | null;
}

export interface ShortFormGapMetrics {
  shorts_count: number;
  longform_count: number;
  shorts_ratio_pct: number;
  estimated_missed_views: number;
  outlier_multiplier: number;
  shortform_opportunity_score: number;
  opportunity_verdict: string;
}

export interface ReelConversionBlueprint {
  source_title: string;
  source_url?: string | null;
  clip_timestamp_start: string;
  clip_timestamp_end: string;
  duration_seconds: number;
  viral_hook_3s: string;
  visual_hook_prompt: string;
  pacing_and_sound: string;
  caption: string;
  estimated_viral_score: number;
}

export interface HookTeardown {
  original_angle: string;
  weakness_diagnosis: string;
  viral_rewrite_1: string;
  viral_rewrite_2: string;
  framework_used: string;
}

export interface ShortFormSprintDay {
  day_number: number;
  week_number: number;
  pillar: string;
  topic: string;
  hook: string;
  format_style: string;
  target_cta: string;
}

export interface ShortFormOutreachCopy {
  cold_email_subject: string;
  cold_email_body: string;
  dm_pitch: string;
  followup_bump: string;
}

export interface ShortFormAuditReport {
  report_id: string;
  profile: ShortFormProfile;
  gap_metrics: ShortFormGapMetrics;
  blueprints: ReelConversionBlueprint[];
  hook_teardowns: HookTeardown[];
  sprint_calendar: ShortFormSprintDay[];
  outreach_copy: ShortFormOutreachCopy;
  executive_summary: string;
  generated_at: string;
  model: string;
  outreach_status: ProspectStatus;
}

export interface ShortFormLookupResponse {
  profile: ShortFormProfile;
  gap_metrics: ShortFormGapMetrics;
  sample_videos_count: number;
}

export const shortformApi = {
  lookup: (platform: ShortFormPlatform, query: string) =>
    request<ShortFormLookupResponse>("/shortform-prospects/lookup", {
      method: "POST",
      body: JSON.stringify({ platform, query }),
    }),

  generate: (platform: ShortFormPlatform, identifier: string) =>
    request<ShortFormAuditReport>("/shortform-prospects/generate", {
      method: "POST",
      body: JSON.stringify({ platform, identifier }),
    }),

  getReport: (reportId: string) =>
    request<ShortFormAuditReport>(`/shortform-prospects/${reportId}`),

  list: () =>
    request<{ items: ShortFormAuditReport[] }>("/shortform-prospects/list"),

  updateStatus: (reportId: string, status: ProspectStatus) =>
    request<{ status: ProspectStatus; report_id: string }>(
      `/shortform-prospects/${reportId}/status`,
      {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }
    ),
};
