"use client";

/**
 * Today at a glance. Backed by GET /assistant/digest, which runs no LLM — so
 * this renders in milliseconds and the page is never an empty box waiting on an
 * eight-second answer.
 */

import { CalendarDays, ClipboardCheck, Inbox, TriangleAlert } from "lucide-react";
import Link from "next/link";

import type { Digest } from "@/lib/assistantApi";

function Stat({
  icon: Icon,
  label,
  value,
  tone = "text-slate-200",
}: {
  icon: typeof Inbox;
  label: string;
  value: number | string;
  tone?: string;
}) {
  return (
    <div className="glass-card flex items-center gap-2.5 rounded-xl border border-white/5 px-3 py-2.5">
      <Icon className="h-4 w-4 shrink-0 text-slate-500" />
      <div className="min-w-0">
        <div className={`text-sm font-semibold ${tone}`}>{value}</div>
        <div className="truncate text-[10px] uppercase tracking-[0.15em] text-slate-500">
          {label}
        </div>
      </div>
    </div>
  );
}

export default function DigestStrip({ digest }: { digest: Digest | null }) {
  if (!digest) {
    return (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="glass-card h-[58px] animate-pulse rounded-xl border border-white/5"
          />
        ))}
      </div>
    );
  }

  const empty =
    digest.items_this_week === 0 &&
    digest.pending_review === 0 &&
    digest.backlog_uncovered === 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat icon={CalendarDays} label="Today" value={digest.items_today.length} />
        <Stat icon={Inbox} label="This week" value={digest.items_this_week} />
        <Stat icon={ClipboardCheck} label="To review" value={digest.pending_review} />
        <Stat
          icon={TriangleAlert}
          label="Overdue"
          value={digest.overdue}
          tone={digest.overdue > 0 ? "text-amber-300" : "text-slate-200"}
        />
      </div>

      {digest.items_today.length > 0 && (
        <div className="glass-card rounded-xl border border-white/5 p-3">
          <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-slate-500">
            Scheduled today
          </div>
          <ul className="space-y-1.5">
            {digest.items_today.slice(0, 5).map((item) => (
              <li key={item.id} className="flex items-baseline gap-2 text-xs">
                <span className="w-11 shrink-0 font-mono text-[11px] text-slate-500">
                  {item.event_time ?? "--:--"}
                </span>
                <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-400">
                  {item.platform}
                </span>
                <span className="truncate text-slate-300">{item.topic}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {empty && (
        <div className="glass-card rounded-xl border border-white/5 p-4 text-center">
          <p className="text-xs text-slate-400">
            Nothing planned yet.{" "}
            <Link href="/planner" className="text-blue-400 underline underline-offset-2">
              Create your first plan →
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}
