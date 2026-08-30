"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Trophy,
  TrendingUp,
  Users,
  Image as ImageIcon,
  Heart,
  MessageCircle,
  Eye,
  Play,
  Bookmark,
  Share2,
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

interface Coverage {
  media_fetched?: number;
  media_total?: number;
  media_complete?: boolean;
  insights_requested?: number;
  insights_measured?: number;
}

interface AchievementsData {
  /** Always "post_month" today — see the provenance caption below. */
  basis: string;
  as_of: string;
  synced_at: string | null;
  /** The snapshot predates insights provenance — engagement history is thin. */
  stale: boolean;
  months_of_history: number;
  coverage: Coverage;
  key_achievements: AchievementMilestone[];
  top_performing_months: TopPerformingMonth[];
  unavailable: { metric: string; reason: string }[];
}

// ─── Metric config ────────────────────────────────────────────────────────────

const METRIC_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; iconBg: string }
> = {
  followers: { label: "Followers", icon: Users,         iconBg: "bg-pink-500"    },
  posts:     { label: "Posts",     icon: ImageIcon,     iconBg: "bg-purple-500"  },
  likes:     { label: "Likes",     icon: Heart,         iconBg: "bg-rose-500"    },
  comments:  { label: "Comments",  icon: MessageCircle, iconBg: "bg-fuchsia-500" },
  // Never milestone cards (insights cover a recent window only), but they do
  // appear in the "not tracked yet" line, which reads their label.
  reach:     { label: "Reach",     icon: Eye,           iconBg: "bg-indigo-500"  },
  views:     { label: "Views",     icon: Play,          iconBg: "bg-amber-500"   },
  saves:     { label: "Saves",     icon: Bookmark,      iconBg: "bg-blue-500"    },
  shares:    { label: "Shares",    icon: Share2,        iconBg: "bg-teal-500"    },
  // Not a card at all — only ever named in the "not tracked yet" line, when a
  // truncated post history cannot support a "best month ever" claim.
  best_months: { label: "Best months", icon: Trophy,     iconBg: "bg-amber-500"   },
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

function KeyAchievementCard({
  item,
  isFirst,
}: {
  item: AchievementMilestone;
  isFirst: boolean;
}) {
  const label = METRIC_CONFIG[item.metric]?.label ?? item.metric;

  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
        isFirst
          ? "border-pink-500/50 bg-pink-500/5 ring-1 ring-pink-500/20"
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
            className="h-2.5 rounded-full bg-gradient-to-r from-pink-500 to-purple-500 transition-all duration-700"
            style={{ width: `${Math.min(item.progress_pct, 100)}%` }}
          />
        </div>
        <p className="text-xs font-semibold text-pink-300">
          {item.current_value.toLocaleString()}
        </p>
      </div>
    </div>
  );
}

function TopMonthCard({
  item,
  isFirst,
}: {
  item: TopPerformingMonth;
  isFirst: boolean;
}) {
  const label = METRIC_CONFIG[item.metric]?.label ?? item.metric;
  const diamondPos = `${Math.min(Math.max(item.progress_pct, 2), 95)}%`;

  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-all ${
        isFirst
          ? "border-pink-500/50 bg-pink-500/5 ring-1 ring-pink-500/20"
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
              className="h-2.5 rounded-full bg-gradient-to-r from-pink-500 to-purple-500 transition-all duration-700"
              style={{ width: `${Math.min(item.progress_pct, 100)}%` }}
            />
          </div>
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2"
            style={{ left: diamondPos }}
          >
            <div className="w-3 h-3 bg-pink-400 rotate-45 border-2 border-[#0f172a]" />
          </div>
        </div>
        <p className="text-xs font-semibold text-pink-300">
          {item.current_value.toLocaleString()}
        </p>
      </div>
    </div>
  );
}

function SectionHeader({
  onRefresh,
  refreshing,
}: {
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
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
          title="Recompute from the latest synced data"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin text-pink-400" : ""} />
          <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
        </button>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function InstagramAchievements() {
  const [data, setData] = useState<AchievementsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Computed from the already-synced snapshot, so this re-reads that snapshot;
  // pulling new numbers from Meta is what "Sync Metrics" does.
  const load = useCallback((alive: () => boolean = () => true) => {
    return request<AchievementsData>(`/instagram-analytics/achievements?_t=${Date.now()}`)
      .then((res) => {
        if (alive()) setData(res);
      })
      .catch((err) => {
        if (alive()) setError(err?.message || "Could not load achievements.");
      })
      .finally(() => {
        if (!alive()) return;
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    setError(null);
    load();
  };

  useEffect(() => {
    let cancelled = false;
    load(() => !cancelled);
    return () => {
      cancelled = true;
    };
  }, [load]);

  if (loading) {
    return (
      <div className="space-y-8">
        <SectionHeader />
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin text-pink-500">
            <RefreshCw size={32} />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8">
        <SectionHeader onRefresh={handleRefresh} refreshing={refreshing} />
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
  const coverage = data?.coverage ?? {};

  if (keyAchievements.length === 0 && topMonths.length === 0) {
    return (
      <div className="space-y-8">
        <SectionHeader onRefresh={handleRefresh} refreshing={refreshing} />
        <div className="flex flex-col items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] py-10 px-4 text-center">
          <Trophy size={22} className="text-slate-500" />
          <p className="text-sm font-semibold text-slate-300">No milestones yet</p>
          <p className="text-xs text-slate-500 max-w-sm">
            Connect your Instagram account and run Sync Metrics, and your milestones will
            appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SectionHeader onRefresh={handleRefresh} refreshing={refreshing} />

      {data?.stale && (
        <div className="flex items-start gap-2 py-2.5 px-4 rounded-xl border border-sky-500/20 bg-sky-500/[0.06] text-xs text-sky-200/90">
          <Info size={13} className="mt-0.5 flex-shrink-0 text-sky-400" />
          <span>
            Based on a snapshot taken before per-post metrics were verifiable. Run{" "}
            <span className="font-semibold text-sky-100">Sync Metrics</span> on the
            Analytics tab to rebuild these milestones from measured data.
          </span>
        </div>
      )}

      {/* Provenance. An approximation must never read as an exact claim. */}
      <div className="flex items-start gap-2 py-2 px-4 bg-white/[0.03] border border-white/[0.08] rounded-xl text-slate-400 text-xs">
        <Info size={13} className="mt-0.5 flex-shrink-0 text-slate-500" />
        <span>
          Follower and post counts come straight from your profile. Engagement dates are
          credited to each post&apos;s publish month, so likes a post earned later are
          counted in the month it went up — the months are indicative, the totals are exact.
          {coverage.media_complete === false && coverage.media_fetched && coverage.media_total ? (
            <>
              {" "}
              Only your {coverage.media_fetched.toLocaleString()} most recent posts of{" "}
              {coverage.media_total.toLocaleString()} are synced, so lifetime engagement
              totals are held back rather than under-reported.
            </>
          ) : null}
        </span>
      </div>

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
            <h3 className="text-base font-semibold text-white">Best Posting Months</h3>
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
