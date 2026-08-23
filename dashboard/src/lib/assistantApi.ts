/**
 * API client for the centralized assistant (/api/assistant).
 *
 * Mirrors the Pydantic shapes in `app/models/assistant.py`. Note that `ask` can
 * legitimately take tens of seconds — the backend runs a two-call LLM cascade
 * and cannot stream, so the UI manages perceived latency rather than progress.
 */

import { request } from "@/lib/apiClient";

// ── Types ────────────────────────────────────────────────────────────────────

export type AssistantVerb =
  | "mark_published"
  | "reschedule"
  | "generate_content"
  | "approve_draft"
  | "reject_draft";

export type ActionStatus =
  | "proposed"
  | "executing"
  | "executed"
  | "cancelled"
  | "failed"
  | "expired";

export interface AssistantAction {
  id: string;
  /** Present when fetched via getConversation; used to group actions by bubble. */
  message_id?: string | null;
  verb: AssistantVerb;
  /** Server-authored, built from validated DB values. Render as plain text. */
  label: string;
  item_id: string;
  content_id?: string | null;
  item_topic: string;
  item_platform: string;
  params: {
    scheduled_date?: string;
    event_time?: string;
    content_type?: string;
    production_status?: string;
    regenerate?: boolean;
  };
  status: ActionStatus;
  expires_at?: string | null;
}

export interface ResolvedRange {
  intent: string;
  date_from?: string | null;
  date_to?: string | null;
  platforms: string[];
}

export interface SourceRef {
  kind: "plan_item" | "review" | "backlog" | "report" | "analytics";
  id: string;
  label: string;
  platform?: string | null;
}

export interface AskResponse {
  conversation_id: string;
  message_id: string;
  answer_markdown: string;
  resolved: ResolvedRange;
  actions: AssistantAction[];
  sources: SourceRef[];
  meta: {
    model?: string | null;
    tier?: string | null;
    latency_ms?: number;
    resolver_fallback?: boolean;
    truncated?: Record<string, boolean>;
  };
}

export interface ConfirmResponse {
  action: AssistantAction;
  item?: Record<string, unknown> | null;
  content?: Record<string, unknown> | null;
  dispatched: unknown[];
}

export interface Conversation {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  message_count: number;
}

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  meta: {
    intent?: string;
    date_from?: string | null;
    date_to?: string | null;
    platforms?: string[];
    language?: string;
    model?: string | null;
    tier?: string | null;
    latency_ms?: number;
  };
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: AssistantMessage[];
  actions: AssistantAction[];
}

export interface DigestItem {
  id: string;
  short_id: string;
  platform: string;
  topic: string;
  scheduled_date?: string | null;
  event_time?: string | null;
  production_status: string;
  video_format?: string;
  notes?: string;
}

export interface Digest {
  today: string;
  week_from: string;
  week_to: string;
  items_today: DigestItem[];
  items_this_week: number;
  pending_review: number;
  backlog_uncovered: number;
  overdue: number;
}

/** Prompts offered on an empty thread — also how the user discovers Hinglish works. */
export const SUGGESTED_PROMPTS: string[] = [
  "Aaj mujhe kya post karna hai?",
  "What's pending review?",
  "Is hafte ka schedule dikha",
  "Backlog mein kya bacha hai?",
];

// ── Client ───────────────────────────────────────────────────────────────────

export const assistantApi = {
  ask: (question: string, conversationId?: string | null) =>
    request<AskResponse>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
    }),

  confirmAction: (actionId: string) =>
    request<ConfirmResponse>(`/assistant/actions/${actionId}/confirm`, { method: "POST" }),

  cancelAction: (actionId: string) =>
    request<{ action: AssistantAction }>(`/assistant/actions/${actionId}/cancel`, {
      method: "POST",
    }),

  listConversations: () => request<Conversation[]>("/assistant/conversations"),

  getConversation: (id: string) =>
    request<ConversationDetail>(`/assistant/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<{ message: string }>(`/assistant/conversations/${id}`, { method: "DELETE" }),

  digest: () => request<Digest>("/assistant/digest"),
};
