"use client";

import { useEffect, useRef, useState } from "react";
import { History, Trash2, Check } from "lucide-react";

export interface HistoryEntry {
  id: string;
  created_at: string;
  model?: string | null;
  /** Optional trailing detail, e.g. "4 weeks · 30 days". */
  detail?: string;
}

/** "22 Aug 2026, 14:32" — same rendering wherever a run's timestamp appears. */
export function formatRunTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Dropdown of past analysis runs, shared by the YouTube and Instagram
 * strategy/roadmap cards. It only lists and selects — the caller owns fetching
 * the chosen run's payload, because the two platforms store reports in
 * different tables with different field vocabularies.
 */
export default function AnalysisHistoryPicker({
  entries,
  currentId,
  loading = false,
  onSelect,
  onDelete,
  tint = "text-slate-300",
}: {
  entries: HistoryEntry[];
  currentId: string | null;
  loading?: boolean;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
  tint?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape so the popover never strands the page.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!entries.length) return null;

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={loading}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-white/[0.03] border border-white/10 hover:bg-white/[0.06] transition-colors disabled:opacity-50 ${tint}`}
      >
        <History size={14} />
        History
        <span className="text-slate-500 tabular-nums">({entries.length})</span>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute right-0 z-20 mt-2 w-72 max-h-80 overflow-y-auto rounded-xl border border-white/10 bg-[#0f172a] shadow-xl shadow-black/40 p-1"
        >
          {entries.map((entry) => {
            const active = entry.id === currentId;
            return (
              <div
                key={entry.id}
                className={`group flex items-center gap-2 rounded-lg px-2 py-2 text-left ${
                  active ? "bg-white/[0.07]" : "hover:bg-white/[0.04]"
                }`}
              >
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onSelect(entry.id);
                    setOpen(false);
                  }}
                  className="flex-1 min-w-0 text-left"
                >
                  <span className="flex items-center gap-1.5 text-xs text-slate-200 tabular-nums">
                    {active && <Check size={12} className="flex-shrink-0 text-emerald-400" />}
                    {formatRunTime(entry.created_at)}
                  </span>
                  <span className="block truncate text-[11px] text-slate-500 mt-0.5">
                    {[entry.detail, entry.model].filter(Boolean).join(" · ") || " "}
                  </span>
                </button>

                {onDelete && (
                  <button
                    type="button"
                    aria-label="Delete this run"
                    onClick={() => onDelete(entry.id)}
                    className="p-1 rounded text-slate-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
