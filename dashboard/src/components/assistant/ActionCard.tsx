"use client";

/**
 * One proposed write, with confirm/cancel.
 *
 * The label is server-authored and rendered as plain text, never markdown: a
 * button that authorizes a database write must not be phrased — or linked — by
 * the model, and topics reaching it are user- or AI-written free text.
 *
 * On failure the server's `detail` is shown verbatim. That is how the 429 quota
 * message and the 409 "already published" reach the user, and why nothing here
 * ever auto-retries a write.
 */

import { motion } from "framer-motion";
import {
  AlertTriangle,
  CalendarClock,
  Check,
  CheckCircle2,
  Loader2,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { useState } from "react";

import { assistantApi, type AssistantAction, type AssistantVerb } from "@/lib/assistantApi";

const VERB_STYLE: Record<
  AssistantVerb,
  { border: string; icon: typeof Check; confirm: string; button: string; destructive?: boolean }
> = {
  mark_published: {
    border: "border-l-emerald-400/60",
    icon: CheckCircle2,
    confirm: "Mark published",
    button: "bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25",
  },
  reschedule: {
    border: "border-l-sky-400/60",
    icon: CalendarClock,
    confirm: "Reschedule",
    button: "bg-sky-500/15 text-sky-200 hover:bg-sky-500/25",
  },
  generate_content: {
    border: "border-l-violet-400/60",
    icon: Sparkles,
    confirm: "Generate",
    button: "bg-violet-500/15 text-violet-200 hover:bg-violet-500/25",
  },
  approve_draft: {
    border: "border-l-emerald-400/60",
    icon: ThumbsUp,
    confirm: "Approve",
    button: "bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25",
  },
  reject_draft: {
    border: "border-l-rose-400/60",
    icon: ThumbsDown,
    confirm: "Reject",
    button: "bg-rose-500/15 text-rose-200 hover:bg-rose-500/25",
    destructive: true,
  },
};

const RECEIPT: Record<AssistantVerb, string> = {
  mark_published: "Marked as published",
  reschedule: "Rescheduled",
  generate_content: "Generation dispatched",
  approve_draft: "Approved",
  reject_draft: "Rejected",
};

function isExpired(action: AssistantAction): boolean {
  if (!action.expires_at) return false;
  return new Date(action.expires_at).getTime() < Date.now();
}

export default function ActionCard({
  action,
  onExecuted,
}: {
  action: AssistantAction;
  onExecuted?: (updated: AssistantAction) => void;
}) {
  const [status, setStatus] = useState<AssistantAction["status"]>(action.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dispatched, setDispatched] = useState(0);

  const style = VERB_STYLE[action.verb];
  const Icon = style.icon;
  const expired = status === "proposed" && isExpired(action);

  const run = async (kind: "confirm" | "cancel") => {
    setBusy(true);
    setError(null);
    try {
      if (kind === "confirm") {
        const res = await assistantApi.confirmAction(action.id);
        setDispatched(res.dispatched?.length ?? 0);
        setStatus("executed");
        onExecuted?.(res.action);
      } else {
        const res = await assistantApi.cancelAction(action.id);
        setStatus("cancelled");
        onExecuted?.(res.action);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Something went wrong.";
      setError(detail);
      // Stays actionable only via Cancel — never silently retry a write.
      setStatus("proposed");
    } finally {
      setBusy(false);
    }
  };

  if (status === "executed" || status === "cancelled") {
    const done = status === "executed";
    return (
      <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
        {done ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <X className="h-3.5 w-3.5 text-slate-500" />
        )}
        <span>
          {done ? RECEIPT[action.verb] : "Dismissed"}
          {done && dispatched > 0 && ` · ${dispatched} run dispatched`}
        </span>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass-card mt-2 rounded-xl border border-white/5 border-l-2 ${style.border} p-3`}
    >
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
        <div className="min-w-0 flex-1">
          {/* Plain text on purpose — see the file docstring. */}
          <p className="text-sm text-slate-200">{action.label}</p>

          {action.params?.regenerate && (
            <p className="mt-1 text-[11px] text-amber-300/80">
              Will generate a replacement · uses 1 run from your monthly quota
            </p>
          )}

          {action.item_topic && action.verb !== "mark_published" && (
            <p className="mt-1 truncate text-[11px] text-slate-500">
              {action.item_platform} · {action.item_topic}
            </p>
          )}

          {error && (
            <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/10 p-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
              <p className="text-[11px] text-amber-200">{error}</p>
            </div>
          )}

          {expired ? (
            <p className="mt-2 text-[11px] text-slate-500">
              This suggestion expired — ask again to get a fresh one.
            </p>
          ) : (
            <div className="mt-2.5 flex items-center gap-2">
              <button
                onClick={() => run("confirm")}
                disabled={busy}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-colors disabled:opacity-50 ${style.button}`}
              >
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                {style.confirm}
              </button>
              <button
                onClick={() => run("cancel")}
                disabled={busy}
                className="rounded-lg px-3 py-1.5 text-[11px] text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
