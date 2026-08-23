"use client";

/**
 * One turn. User turns render as plain text (never markdown — echoing a user's
 * own input through a renderer buys nothing and widens the surface); assistant
 * turns render markdown plus their resolved-range chip, source chips and any
 * proposed actions.
 */

import { Bot, User } from "lucide-react";

import ActionCard from "@/components/assistant/ActionCard";
import MarkdownMessage from "@/components/assistant/MarkdownMessage";
import type { AssistantAction, ResolvedRange, SourceRef } from "@/lib/assistantApi";

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  resolved?: ResolvedRange | null;
  actions?: AssistantAction[];
  sources?: SourceRef[];
  error?: boolean;
}

function formatRange(resolved: ResolvedRange): string | null {
  const { date_from: from, date_to: to } = resolved;
  if (!from && !to) return null;
  const fmt = (d: string) =>
    new Date(`${d}T00:00:00`).toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
  if (from && to && from === to) return fmt(from);
  if (from && to) return `${fmt(from)} – ${fmt(to)}`;
  return fmt((from ?? to)!);
}

export default function ChatMessage({
  turn,
  onActionUpdated,
}: {
  turn: ChatTurn;
  onActionUpdated?: (updated: AssistantAction) => void;
}) {
  const isUser = turn.role === "user";
  const range = turn.resolved ? formatRange(turn.resolved) : null;

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : ""}`}>
      {!isUser && (
        <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-600/20">
          <Bot className="h-3.5 w-3.5 text-blue-300" />
        </div>
      )}

      <div className={`min-w-0 ${isUser ? "max-w-[85%]" : "flex-1"}`}>
        {isUser ? (
          <div className="rounded-xl rounded-tr-sm bg-white/[0.06] px-3.5 py-2.5">
            <p className="whitespace-pre-wrap break-words text-sm text-slate-200">
              {turn.content}
            </p>
          </div>
        ) : (
          <div
            className={`rounded-xl rounded-tl-sm border p-3.5 ${
              turn.error
                ? "border-amber-500/20 bg-amber-500/5"
                : "border-white/5 bg-white/[0.02]"
            }`}
          >
            {(range || (turn.resolved?.platforms?.length ?? 0) > 0) && (
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                {range && (
                  <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-slate-400">
                    {range}
                  </span>
                )}
                {turn.resolved?.platforms?.map((p) => (
                  <span
                    key={p}
                    className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-slate-400"
                  >
                    {p}
                  </span>
                ))}
              </div>
            )}

            <MarkdownMessage>{turn.content}</MarkdownMessage>

            {turn.actions?.map((action) => (
              <ActionCard key={action.id} action={action} onExecuted={onActionUpdated} />
            ))}

            {(turn.sources?.length ?? 0) > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/5 pt-2.5">
                {turn.sources!.slice(0, 6).map((s) => (
                  <span
                    key={`${s.kind}-${s.id}`}
                    className="max-w-[220px] truncate rounded-md bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-500"
                    title={s.label}
                  >
                    {s.label}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-white/5">
          <User className="h-3.5 w-3.5 text-slate-400" />
        </div>
      )}
    </div>
  );
}
