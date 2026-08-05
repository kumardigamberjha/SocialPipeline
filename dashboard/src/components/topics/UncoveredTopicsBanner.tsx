"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Lightbulb, ArrowRight, X } from "lucide-react";
import {
  savedTopicsApi,
  SAVED_TOPICS_UPDATED_EVENT,
  type SavedTopicSummary,
} from "@/lib/savedTopicsApi";

// Dismissal is per-session on purpose: the backlog is worth one reminder per
// visit, not one per navigation.
const DISMISS_KEY = "uncoveredTopicsBannerDismissed";

export default function UncoveredTopicsBanner() {
  const [summary, setSummary] = useState<SavedTopicSummary | null>(null);
  // Read once at mount. Safe against hydration mismatch because the first
  // render returns null regardless (summary is still loading), so server and
  // client agree on the DOM even when this value differs.
  const [hidden, setHidden] = useState(
    () => typeof window !== "undefined" && window.sessionStorage.getItem(DISMISS_KEY) === "1",
  );

  const load = useCallback(async () => {
    try {
      setSummary(await savedTopicsApi.getSummary());
    } catch {
      /* backlog is a nicety — never surface an error for it */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    // A run can finish while this is mounted, and auto-research emits the
    // custom event the moment it saves new candidates.
    window.addEventListener("focus", load);
    window.addEventListener(SAVED_TOPICS_UPDATED_EVENT, load);
    return () => {
      window.removeEventListener("focus", load);
      window.removeEventListener(SAVED_TOPICS_UPDATED_EVENT, load);
    };
  }, [load]);

  const dismiss = () => {
    window.sessionStorage.setItem(DISMISS_KEY, "1");
    setHidden(true);
  };

  if (hidden || !summary || summary.uncovered_count === 0) return null;

  const n = summary.uncovered_count;

  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 flex items-center gap-3 flex-wrap">
      <Lightbulb className="w-4 h-4 text-amber-400 shrink-0" />
      <div className="flex-1 min-w-[180px]">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Uncovered Topics
        </p>
        <p className="text-xs text-slate-500 mt-0.5">
          {n} researched {n === 1 ? "topic is" : "topics are"} waiting to be turned into content.
        </p>
      </div>
      <Link
        href="/topics"
        className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5"
      >
        Review {n} <ArrowRight className="w-3 h-3" />
      </Link>
      <button
        onClick={dismiss}
        aria-label="Dismiss for this session"
        className="text-xs p-1.5 rounded-lg border border-white/10 text-slate-500 hover:text-slate-200 hover:border-white/20 transition-colors"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
