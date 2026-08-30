"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Trophy,
  TrendingUp,
  Users,
  Eye,
  Clock,
  ThumbsUp,
  MessageCircle,
  Upload,
  RefreshCw,
  AlertTriangle,
  Info,
} from "lucide-react";
import { request } from "@/lib/apiClient";

// ─── Types ───────────────────────────────────────────────────────────────────

// achieved_date and next_milestone_eta are nullable on purpose: the backend
// sends null when it has no history to date a milestone from, or no growth rate
// to project one. The cards drop those lines rather than showing a guess.

interface AchievementMilestone {
  metric: string;
  milestone: number | null;
  milestone_label: string;
  achieved_date: string | null;
  current_value: number;
  next_milestone: number | null;
  next_milestone_label: string;
  next_milestone_eta: string | null;
  progress_pct: number;
}

interface TopPerformingMonth {
  metric: string;
  milestone: number;
  milestone_label: string;
  achieved_date: string;
  current_value: number;
  progress_pct: number;
}

interface AchievementsData {
  /** Which history produced the dates — see the provenance caption below. */
  basis: "analytics_api" | "upload_month";
  as_of: string;
  months_of_history: number;
  key_achievements: AchievementMilestone[];
  top_performing_months: TopPerformingMonth[];
  unavailable: { metric: string; reason: string }[];
}

// ─── Metric config ────────────────────────────────────────────────────────────

const METRIC_CONFIG: Record<
  string,
  {
    label: string;
    icon: React.ElementType;
    iconBg: string;
  }
> = {
  subscribers: { label: "Subscribers", icon: Users, iconBg: "bg-emerald-500" },
  views:       { label: "Views",        icon: Eye,         iconBg: "bg-red-500"  },
  uploads:     { label: "Uploads",      icon: Upload,      iconBg: "bg-blue-500" },
  likes:       { label: "Likes",        icon: ThumbsUp,    iconBg: "bg-amber-500"},
  watch_time:  { label: "Hours watched",icon: Clock,       iconBg: "bg-sky-500"  },
  comments:    { label: "Comments",     icon: MessageCircle, iconBg: "bg-fuchsia-500" },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function MetricIcon({ metric, size = 40 }: { metric: string; size?: number }) {
  const cfg = METRIC_CONFIG[metric];
  if (!cfg) return null;
  const Icon = cfg.icon;
  return (
    <div
      className={`flex-shrink-0 flex items-center justify-center rounded-xl ${cfg.iconBg}`}
      style={{ width: size, height: size }}
    >
      <Icon size={size * 0.5} className="text-white" />
    </div>
  );
}

// ─── Key Achievement Card ─────────────────────────────────────────────────────

function KeyAchievementCard({
  item,
  isFirst,
}: {
  item: AchievementMilestone;
  isFirst: boolean;
}) {
  const cfg = METRIC_CONFIG[item.metric];
  const label = cfg?.label ?? item.metric;

  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
        isFirst
          ? "border-blue-500/50 bg-blue-500/5 ring-1 ring-blue-500/20"
          : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
      }`}
    >
      <div className="flex items-center gap-3">
        <MetricIcon metric={item.metric} size={44} />
        <div className="flex-1 min-w-0">
          <p className="text-xl font-extrabold text-white leading-none">
            {item.milestone_label || item.current_value.toLocaleString()}{" "}
            <span className="text-base font-semibold text-slate-300">{label}</span>
          </p>
          {item.achieved_date ? (
            <p className="text-xs text-slate-500 mt-0.5">Reached in {item.achieved_date}</p>
          ) : (
            <p className="text-xs text-slate-600 mt-0.5">Date not tracked</p>
          )}
        </div>
      </div>

      {item.next_milestone_label && (
        <p className="text-xs text-slate-400">
          Next up:{" "}
          <span className="font-semibold text-white">
            {item.next_milestone_label} {label}
          </span>
          {item.next_milestone_eta ? ` — on pace for ${item.next_milestone_eta}` : ""}
        </p>
      )}

      <div className="space-y-1">
        <div className="w-full bg-white/10 rounded-full h-2.5 overflow-hidden">
          <div
            className="h-2.5 rounded-full bg-emerald-400 transition-all duration-700"
            style={{ width: `${Math.min(item.progress_pct, 100)}%` }}
          />
        </div>
        <p className="text-xs font-semibold text-emerald-400">
          {item.current_value.toLocaleString()}
        </p>
      </div>
    </div>
  );
}

// ─── Top Performing Month Card ────────────────────────────────────────────────

function TopMonthCard({
  item,
  isFirst,
}: {
  item: TopPerformingMonth;
  isFirst: boolean;
}) {
  const cfg = METRIC_CONFIG[item.metric];
  const label = cfg?.label ?? item.metric;
  const diamondPos = `${Math.min(Math.max(item.progress_pct, 2), 95)}%`;

  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
        isFirst
          ? "border-blue-500/50 bg-blue-500/5 ring-1 ring-blue-500/20"
          : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
      }`}
    >
      <div className="flex items-center gap-3">
        <MetricIcon metric={item.metric} size={44} />
        <div className="flex-1 min-w-0">
          <p className="text-xl font-extrabold text-white leading-none">
            {item.milestone_label}{" "}
            <span className="text-base font-semibold text-slate-300">{label}</span>
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Best month: {item.achieved_date}</p>
        </div>
      </div>

      <p className="text-xs text-slate-400">
        {item.progress_pct}% of the way there this month
      </p>

      <div className="space-y-1">
        <div className="relative w-full h-2.5">
          <div className="w-full bg-white/10 rounded-full h-2.5 overflow-hidden">
            <div
              className="h-2.5 rounded-full bg-emerald-400 transition-all duration-700"
              style={{ width: `${Math.min(item.progress_pct, 100)}%` }}
            />
          </div>
          {/* Diamond indicator */}
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2"
            style={{ left: diamondPos }}
          >
            <div className="w-3 h-3 bg-emerald-400 rotate-45 border-2 border-[#0f172a]" />
          </div>
        </div>
        <p className="text-xs font-semibold text-emerald-400">
          {item.current_value.toLocaleString()}
        </p>
      </div>
    </div>
  );
}

// ─── Section shell ────────────────────────────────────────────────────────────

function SectionHeader({ onRefresh, refreshing }: { onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 flex-1">
        <Trophy size={18} className="text-amber-400" />
        <h2 className="text-sm font-bold tracking-[0.2em] uppercase text-slate-300">
          Achievements
        </h2>
        <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
      </div>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
          title="Refresh Achievements"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin text-blue-400" : ""} />
          <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
        </button>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function YoutubeAchievements() {
  const [data, setData] = useState<AchievementsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAchievements = useCallback((isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    const url = isRefresh
      ? `/youtube-analytics/achievements?refresh=true&_t=${Date.now()}`
      : `/youtube-analytics/achievements?_t=${Date.now()}`;

    return request<AchievementsData>(url)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        setError(err?.message || "Could not load achievements.");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    let ignore = false;
    request<AchievementsData>(`/youtube-analytics/achievements?_t=${Date.now()}`)
      .then((res) => {
        if (!ignore) setData(res);
      })
      .catch((err) => {
        if (!ignore) setError(err?.message || "Could not load achievements.");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-8">
        <SectionHeader />
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin text-red-500">
            <RefreshCw size={32} />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8">
        <SectionHeader onRefresh={() => fetchAchievements(true)} refreshing={refreshing} />
        <div className="flex flex-col items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 py-10 px-4 text-center">
          <AlertTriangle size={22} className="text-red-400" />
          <p className="text-sm font-semibold text-red-300">Could not load your achievements</p>
          <p className="text-xs text-slate-400">{error}</p>
        </div>
      </div>
    );
  }

  const keyAchievements = data?.key_achievements ?? [];
  const topMonths = data?.top_performing_months ?? [];

  if (keyAchievements.length === 0 && topMonths.length === 0) {
    return (
      <div className="space-y-8">
        <SectionHeader onRefresh={() => fetchAchievements(true)} refreshing={refreshing} />
        <div className="flex flex-col items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] py-10 px-4 text-center">
          <Trophy size={22} className="text-slate-500" />
          <p className="text-sm font-semibold text-slate-300">No milestones yet</p>
          <p className="text-xs text-slate-500 max-w-sm">
            Import a YouTube Studio CSV or run a channel sync, and your milestones will
            appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SectionHeader onRefresh={() => fetchAchievements(true)} refreshing={refreshing} />

      {/* Provenance. An approximation must never read as an exact claim. */}
      {data?.basis === "upload_month" && (
        <div className="flex items-start gap-2 py-2 px-4 bg-white/[0.03] border border-white/[0.08] rounded-xl text-slate-400 text-xs">
          <Info size={13} className="mt-0.5 flex-shrink-0 text-slate-500" />
          <span>
            Dates are estimated from each video&apos;s publish month, so they are
            approximate. Connect the YouTube Analytics API for exact milestone dates and
            month-by-month history.
          </span>
        </div>
      )}

      {keyAchievements.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <TrendingUp size={15} className="text-slate-400" />
            <h3 className="text-base font-semibold text-white">Key Achievements</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {keyAchievements.map((item, i) => (
              <KeyAchievementCard key={item.metric} item={item} isFirst={i === 0} />
            ))}
          </div>
        </div>
      )}

      {topMonths.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Trophy size={15} className="text-amber-400" />
            <h3 className="text-base font-semibold text-white">
              {data?.basis === "upload_month" ? "Best Upload Months" : "Top Performing Months"}
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {topMonths.map((item, i) => (
              <TopMonthCard key={item.metric} item={item} isFirst={i === 0} />
            ))}
          </div>
        </div>
      )}

      {data && data.unavailable.length > 0 && (
        <p className="text-xs text-slate-600">
          Not tracked yet:{" "}
          {data.unavailable
            .map((u) => `${METRIC_CONFIG[u.metric]?.label ?? u.metric} (${u.reason})`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}
