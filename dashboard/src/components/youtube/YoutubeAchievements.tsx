"use client";

import React, { useState, useEffect } from "react";
import {
  Trophy,
  Share2,
  TrendingUp,
  Users,
  Eye,
  Clock,
  ThumbsUp,
  MessageCircle,
  Upload,
} from "lucide-react";
import { request } from "@/lib/apiClient";

// ─── Types ───────────────────────────────────────────────────────────────────

interface AchievementMilestone {
  metric: string;
  milestone: number;
  milestone_label: string;
  achieved_date: string;
  current_value: number;
  next_milestone: number;
  next_milestone_label: string;
  next_milestone_eta: string;
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
  key_achievements: AchievementMilestone[];
  top_performing_months: TopPerformingMonth[];
}

// ─── Static fallback data (mirrors the screenshots) ──────────────────────────

const FALLBACK: AchievementsData = {
  key_achievements: [
    {
      metric: "subscribers",
      milestone: 1500,
      milestone_label: "1.5K",
      achieved_date: "5th January 2025",
      current_value: 1701,
      next_milestone: 2000,
      next_milestone_label: "2K",
      next_milestone_eta: "9th August 2028",
      progress_pct: Math.round((1701 / 2000) * 100),
    },
    {
      metric: "views",
      milestone: 150000,
      milestone_label: "150K",
      achieved_date: "20th September 2025",
      current_value: 168345,
      next_milestone: 175000,
      next_milestone_label: "175K",
      next_milestone_eta: "18th November 2026",
      progress_pct: Math.round((168345 / 175000) * 100),
    },
    {
      metric: "uploads",
      milestone: 300,
      milestone_label: "300",
      achieved_date: "7th August 2024",
      current_value: 388,
      next_milestone: 400,
      next_milestone_label: "400",
      next_milestone_eta: "21st August 2026",
      progress_pct: Math.round((388 / 400) * 100),
    },
    {
      metric: "likes",
      milestone: 3000,
      milestone_label: "3K",
      achieved_date: "18th October 2024",
      current_value: 3918,
      next_milestone: 4000,
      next_milestone_label: "4K",
      next_milestone_eta: "27th August 2026",
      progress_pct: Math.round((3918 / 4000) * 100),
    },
    {
      metric: "watch_time",
      milestone: 7500,
      milestone_label: "7.5K",
      achieved_date: "27th November 2025",
      current_value: 7820,
      next_milestone: 8000,
      next_milestone_label: "8K",
      next_milestone_eta: "19th September 2026",
      progress_pct: Math.round((7820 / 8000) * 100),
    },
    {
      metric: "comments",
      milestone: 500,
      milestone_label: "500",
      achieved_date: "4th November 2025",
      current_value: 555,
      next_milestone: 600,
      next_milestone_label: "600",
      next_milestone_eta: "13th September 2026",
      progress_pct: Math.round((555 / 600) * 100),
    },
  ],
  top_performing_months: [
    {
      metric: "subscribers",
      milestone: 569,
      milestone_label: "569",
      achieved_date: "April 2023",
      current_value: 5,
      progress_pct: 1,
    },
    {
      metric: "views",
      milestone: 5400,
      milestone_label: "5.4K",
      achieved_date: "February 2025",
      current_value: 522,
      progress_pct: 10,
    },
    {
      metric: "uploads",
      milestone: 41,
      milestone_label: "41",
      achieved_date: "March 2021",
      current_value: 7,
      progress_pct: 17,
    },
    {
      metric: "likes",
      milestone: 295,
      milestone_label: "295",
      achieved_date: "May 2021",
      current_value: 32,
      progress_pct: 11,
    },
    {
      metric: "watch_time",
      milestone: 474.8,
      milestone_label: "474.8",
      achieved_date: "June 2021",
      current_value: 33,
      progress_pct: 7,
    },
    {
      metric: "comments",
      milestone: 60,
      milestone_label: "60",
      achieved_date: "June 2021",
      current_value: 9,
      progress_pct: 15,
    },
  ],
};

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

function ShareButton({ shareText }: { shareText: string }) {
  const handleShare = () => {
    if (navigator.share) {
      navigator.share({ title: "YouTube Achievement", text: shareText }).catch(() => {});
    } else {
      navigator.clipboard.writeText(shareText).catch(() => {});
    }
  };
  return (
    <button
      onClick={handleShare}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors flex-shrink-0"
    >
      <Share2 size={12} />
      Share
    </button>
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
            {item.milestone_label}{" "}
            <span className="text-base font-semibold text-slate-300">{label}</span>
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Achieved on {item.achieved_date}</p>
        </div>
        <ShareButton shareText={`I just hit ${item.milestone_label} ${label} on YouTube! 🎉`} />
      </div>

      <p className="text-xs text-slate-400">
        On pace for{" "}
        <span className="font-semibold text-white">
          {item.next_milestone_label} {label}
        </span>{" "}
        by {item.next_milestone_eta}
      </p>

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
          <p className="text-xs text-slate-500 mt-0.5">Achieved on {item.achieved_date}</p>
        </div>
        <ShareButton shareText={`My best month was ${item.milestone_label} ${label} (${item.achieved_date}) on YouTube! 🏆`} />
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

// ─── Main Component ───────────────────────────────────────────────────────────

export default function YoutubeAchievements() {
  const [data, setData] = useState<AchievementsData>(FALLBACK);

  useEffect(() => {
    request<AchievementsData>("/youtube-analytics/achievements")
      .then((res) => setData(res))
      .catch(() => {
        /* silently use fallback */
      });
  }, []);

  const { key_achievements, top_performing_months } = data;

  return (
    <div className="space-y-8">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <Trophy size={18} className="text-amber-400" />
        <h2 className="text-sm font-bold tracking-[0.2em] uppercase text-slate-300">
          Achievements
        </h2>
        <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
      </div>

      {/* Info banner */}
      <div className="flex items-center justify-center gap-2 py-2 px-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-xs text-center">
        🔥 Let us help you celebrate your milestones! Click{" "}
        <Share2 size={12} className="inline mx-1" />
        Share on these to download a certificate you can share via social media.
      </div>

      {/* Key Achievements */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <TrendingUp size={15} className="text-slate-400" />
          <h3 className="text-base font-semibold text-white">Key Achievements</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {key_achievements.map((item, i) => (
            <KeyAchievementCard key={item.metric} item={item} isFirst={i === 0} />
          ))}
        </div>
      </div>

      {/* Top Performing Months */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Trophy size={15} className="text-amber-400" />
          <h3 className="text-base font-semibold text-white">Top Performing Months</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {top_performing_months.map((item, i) => (
            <TopMonthCard key={item.metric} item={item} isFirst={i === 0} />
          ))}
        </div>
      </div>
    </div>
  );
}
