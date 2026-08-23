/**
 * API client for Personal Intelligence (/api/personal-intelligence) — the
 * user's own rules ("how the model should behave") and tracked goals, both
 * injected into every content-generation prompt. See app.services.
 * personal_intelligence.build_intelligence_block on the backend.
 */

import { request as apiRequest } from "@/lib/apiClient";

const BASE = "/personal-intelligence";

export type RuleScope = "global" | "youtube" | "blog" | "linkedin" | "instagram";
export type RuleCategory = "behavior" | "content" | "style" | "constraint";
export type GoalMetric = "subscribers" | "views" | "watch_hours" | "videos_published" | "custom";
export type GoalStatus = "active" | "achieved" | "missed" | "archived";

export const RULE_SCOPES: { value: RuleScope; label: string }[] = [
  { value: "global", label: "Everywhere" },
  { value: "youtube", label: "YouTube" },
  { value: "blog", label: "Blog" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "instagram", label: "Instagram" },
];

export const RULE_CATEGORIES: { value: RuleCategory; label: string }[] = [
  { value: "behavior", label: "Behavior" },
  { value: "content", label: "Content" },
  { value: "style", label: "Style" },
  { value: "constraint", label: "Constraint" },
];

export const GOAL_METRICS: { value: GoalMetric; label: string }[] = [
  { value: "subscribers", label: "Subscribers" },
  { value: "views", label: "Total views" },
  { value: "watch_hours", label: "Watch hours" },
  { value: "videos_published", label: "Videos published" },
  { value: "custom", label: "Custom (manual)" },
];

export interface Rule {
  id: string;
  user_id: string;
  scope: RuleScope;
  category: RuleCategory;
  rule_text: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuleCreatePayload {
  scope: RuleScope;
  category: RuleCategory;
  rule_text: string;
  priority?: number;
  is_active?: boolean;
}

export interface RuleUpdatePayload {
  scope?: RuleScope;
  category?: RuleCategory;
  rule_text?: string;
  priority?: number;
  is_active?: boolean;
}

export interface GoalProgress {
  current_value: number | null;
  pct: number | null;
  on_track: boolean | null;
  computed_at: string | null;
}

export interface Goal {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  platform: string;
  metric: GoalMetric;
  target_value: number;
  baseline_value: number;
  baseline_at: string;
  deadline: string;
  status: GoalStatus;
  progress: GoalProgress;
  created_at: string;
  updated_at: string;
}

export interface GoalCreatePayload {
  title: string;
  description?: string;
  platform?: string;
  metric: GoalMetric;
  target_value: number;
  deadline: string;
}

export interface DirectivesPreview {
  directives: string;
  char_count: number;
  rule_count: number;
  goal_count: number;
  rules_char_budget: number;
}

function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  return apiRequest<T>(`${BASE}${path}`, options);
}

export const piApi = {
  listRules: (params: { scope?: RuleScope; includeInactive?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.scope) qs.set("scope", params.scope);
    if (params.includeInactive) qs.set("include_inactive", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<Rule[]>(`/rules${suffix}`);
  },
  createRule: (payload: RuleCreatePayload) =>
    req<Rule>("/rules", { method: "POST", body: JSON.stringify(payload) }),
  updateRule: (ruleId: string, payload: RuleUpdatePayload) =>
    req<Rule>(`/rules/${ruleId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRule: (ruleId: string) =>
    req<{ message: string }>(`/rules/${ruleId}`, { method: "DELETE" }),

  listGoals: (status: GoalStatus | "" = "active") => {
    const qs = status ? `?status=${status}` : "";
    return req<Goal[]>(`/goals${qs}`);
  },
  createGoal: (payload: GoalCreatePayload) =>
    req<Goal>("/goals", { method: "POST", body: JSON.stringify(payload) }),
  updateGoal: (goalId: string, payload: Partial<GoalCreatePayload> & { status?: GoalStatus }) =>
    req<Goal>(`/goals/${goalId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteGoal: (goalId: string) =>
    req<{ message: string }>(`/goals/${goalId}`, { method: "DELETE" }),
  refreshGoal: (goalId: string) => req<GoalProgress>(`/goals/${goalId}/refresh`, { method: "POST" }),

  preview: (scope: RuleScope | "all" = "global") =>
    req<DirectivesPreview>(`/preview?scope=${scope}`),
};
