"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  LayoutGrid,
  ListChecks,
  FileStack,
  CheckCircle2,
  ThumbsUp,
  Timer,
  CalendarClock,
  AlertTriangle,
  Rocket,
  RefreshCw,
  BarChart3,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LabelList,
} from "recharts";
import {
  plannerApi,
  PlannerStats,
  Plan,
  PRODUCTION_STATUSES,
  PLATFORMS,
  Platform,
  ContentType,
  ReviewStatus,
} from "@/lib/plannerApi";

// ── Palette (validated against the dark surface via the dataviz skill) ─────────
// Categorical (platform mix): blue / green / magenta — slots 1-3, all-pairs CVD-safe.
const PLATFORM_COLORS: Record<ContentType, string> = {
  linkedin: "#3987e5",
  blog: "#008300",
  youtube_script: "#d55181",
};
const PLATFORM_LABELS: Record<ContentType, string> = {
  linkedin: "LinkedIn",
  blog: "Blog",
  youtube_script: "YouTube Script",
};
// Review status uses the reserved status palette (always with labels + legend).
const REVIEW_COLORS: Record<ReviewStatus, string> = {
  approved: "#0ca30c",
  ready: "#3987e5",
  generating: "#fab219",
  rejected: "#d03b3b",
  failed: "#ec835a",
};
const REVIEW_LABELS: Record<ReviewStatus, string> = {
  approved: "Approved",
  ready: "Ready",
  generating: "Generating",
  rejected: "Rejected",
  failed: "Failed",
};
const ACCENT = "#3987e5"; // sequential blue for funnel + trend

const AXIS = "#898781";
const GRID = "#2c2c2a";
const TOOLTIP_STYLE = {
  background: "#0b1120",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  fontSize: 12,
  color: "#fff",
};

const PROD_LABEL: Record<string, string> = Object.fromEntries(
  PRODUCTION_STATUSES.map((s) => [s.value, s.label])
);

function fmtDuration(seconds: number): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
}

function SectionHeader({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <div className="w-1 h-4 bg-gradient-to-b from-blue-500 to-purple-500 rounded-full" />
      <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">{label}</h2>
      {hint && <span className="text-[10px] text-slate-600 ml-2">{hint}</span>}
      <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  tint,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  tint: string;
}) {
  return (
    <div className="glass-card p-5 rounded-2xl border border-white/5 bg-white/[0.02]">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-xl ${tint}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-slate-400 truncate">{label}</p>
          <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
        </div>
      </div>
    </div>
  );
}

/** "" means every platform. */
type PlatformFilter = Platform | "";

export default function PlannerAnalyticsDashboard() {
  const [stats, setStats] = useState<PlannerStats | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [platform, setPlatform] = useState<PlatformFilter>("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Both calls take the same filter, so the KPI tiles and the plan list
      // never disagree about which platform they are describing.
      const scope = platform || undefined;
      const [s, p] = await Promise.all([
        plannerApi.getStats(scope),
        plannerApi.listPlans(scope),
      ]);
      setStats(s);
      setPlans(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [platform]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center text-slate-500 animate-pulse">
        Loading planner analytics…
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
        <p className="text-red-400 text-sm mb-4">{error}</p>
        <button
          onClick={load}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-white/10 text-sm text-slate-300 hover:bg-white/[0.05] transition-colors"
        >
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
      </div>
    );
  }

  if (!stats || stats.kpis.total_plans === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
        <BarChart3 className="w-10 h-10 text-slate-600 mx-auto mb-4" />
        <p className="text-slate-400 text-sm mb-2">
          No planner data{platform ? ` for ${platform}` : ""} yet.
        </p>
        {platform && (
          <button
            onClick={() => setPlatform("")}
            className="text-xs text-blue-300 hover:text-blue-200 underline underline-offset-2 mb-4 block mx-auto"
          >
            Show all platforms
          </button>
        )}
        <p className="text-slate-600 text-xs mb-6">
          Create a content plan and generate some content to see analytics here.
        </p>
        <Link
          href="/planner"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-blue-500/30 bg-blue-600/20 text-sm text-blue-300 hover:bg-blue-600/30 transition-colors"
        >
          Go to Planner
        </Link>
      </div>
    );
  }

  const k = stats.kpis;

  const funnelData = stats.items_funnel.map((f) => ({
    label: PROD_LABEL[f.status] ?? f.status,
    count: f.count,
  }));

  const platformData = (Object.keys(stats.content_by_type) as ContentType[])
    .map((t) => ({ key: t, name: PLATFORM_LABELS[t], value: stats.content_by_type[t] }))
    .filter((d) => d.value > 0);

  const reviewData = (Object.keys(stats.content_by_review) as ReviewStatus[])
    .map((s) => ({ key: s, name: REVIEW_LABELS[s], value: stats.content_by_review[s] }))
    .filter((d) => d.value > 0);

  const volumeData = stats.volume_over_time.map((v) => ({
    day: v.day.slice(5), // MM-DD
    count: v.n,
  }));

  const wordData = (Object.keys(stats.word_metrics) as ContentType[])
    .map((t) => ({
      name: PLATFORM_LABELS[t],
      key: t,
      avg: Math.round(stats.word_metrics[t].avg_words),
      count: stats.word_metrics[t].count,
    }))
    .filter((d) => d.count > 0);

  const gen = stats.generation;
  const genCompleted = gen.completed?.count ?? 0;
  const genFailed = gen.failed?.count ?? 0;
  const genTotal = Object.values(gen).reduce((a, b) => a + b.count, 0);
  const successRate = genTotal ? Math.round((100 * genCompleted) / genTotal) : 0;

  const sched = stats.schedule;
  const schedTotal = sched.published + sched.overdue + sched.upcoming || 1;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
      {/* Platform filter. Unfiltered totals span every platform, and the funnel
          below then lists only one status vocabulary — so it will not sum to
          the Topics tile. Picking a platform makes the two agree. */}
      <div className="flex items-center justify-end">
        <label className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
          Platform
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value as PlatformFilter)}
            className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50"
          >
            <option value="" className="bg-[#0f172a]">All platforms</option>
            {PLATFORMS.map((p) => (
              <option key={p.value} value={p.value} className="bg-[#0f172a]">
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* KPI row */}
      <section>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <KpiCard icon={LayoutGrid} label="Plans" value={k.total_plans} tint="bg-blue-500/10 text-blue-400" />
          <KpiCard icon={ListChecks} label="Topics" value={k.total_items} tint="bg-purple-500/10 text-purple-400" />
          <KpiCard icon={FileStack} label="Content Pieces" value={k.total_content} tint="bg-cyan-500/10 text-cyan-400" />
          <KpiCard icon={CheckCircle2} label="Published" value={k.published_items} tint="bg-green-500/10 text-green-400" />
          <KpiCard icon={ThumbsUp} label="Approval Rate" value={`${k.approval_rate}%`} tint="bg-emerald-500/10 text-emerald-400" />
          <KpiCard icon={Timer} label="Avg Gen Time" value={fmtDuration(k.avg_gen_seconds)} tint="bg-amber-500/10 text-amber-400" />
        </div>
      </section>

      {/* Production funnel */}
      <section>
        <SectionHeader label="Production Pipeline" hint="Topics by stage" />
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={funnelData} layout="vertical" margin={{ left: 24, right: 24 }}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" stroke={AXIS} fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="label" stroke={AXIS} fontSize={12} width={150} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="count" fill={ACCENT} radius={[0, 4, 4, 0]} barSize={22}>
                <LabelList dataKey="count" position="right" fill="#c3c2b7" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Distributions: platform mix + review status */}
      <section>
        <SectionHeader label="Content Distribution" hint="Platform & review status" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Platform Mix</p>
            {platformData.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={platformData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={95} paddingAngle={2} stroke="#0b1120" strokeWidth={2}>
                    {platformData.map((d) => (
                      <Cell key={d.key} fill={PLATFORM_COLORS[d.key]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 12, color: "#c3c2b7" }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-600 text-sm py-16 text-center">No content generated yet.</p>
            )}
          </div>

          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Review Status</p>
            {reviewData.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={reviewData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={95} paddingAngle={2} stroke="#0b1120" strokeWidth={2}>
                    {reviewData.map((d) => (
                      <Cell key={d.key} fill={REVIEW_COLORS[d.key]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 12, color: "#c3c2b7" }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-600 text-sm py-16 text-center">No content generated yet.</p>
            )}
          </div>
        </div>
      </section>

      {/* Volume over time */}
      <section>
        <SectionHeader label="Content Volume" hint="Pieces generated over time" />
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={volumeData} margin={{ left: 8, right: 16 }}>
              <defs>
                <linearGradient id="volFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={ACCENT} stopOpacity={0.5} />
                  <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="day" stroke={AXIS} fontSize={12} />
              <YAxis stroke={AXIS} fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: ACCENT, strokeOpacity: 0.3 }} />
              <Area type="monotone" dataKey="count" stroke={ACCENT} strokeWidth={2} fill="url(#volFill)" dot={{ r: 3, fill: ACCENT, strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Schedule adherence + generation reliability + word metrics */}
      <section>
        <SectionHeader label="Health & Output" hint="Schedule, generation, volume" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Schedule adherence */}
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">Schedule Adherence</p>
            <div className="space-y-3">
              <ScheduleRow icon={Rocket} label="Published" value={sched.published} total={schedTotal} color="bg-green-500" tint="text-green-400" />
              <ScheduleRow icon={CalendarClock} label="Upcoming" value={sched.upcoming} total={schedTotal} color="bg-blue-500" tint="text-blue-400" />
              <ScheduleRow icon={AlertTriangle} label="Overdue" value={sched.overdue} total={schedTotal} color="bg-red-500" tint="text-red-400" />
            </div>
          </div>

          {/* Generation reliability */}
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">Generation Reliability</p>
            <div className="flex items-baseline gap-2 mb-4">
              <span className="text-3xl font-bold text-white tabular-nums">{successRate}%</span>
              <span className="text-xs text-slate-500">success rate</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-white/[0.03] p-3">
                <p className="text-[11px] text-slate-500">Completed</p>
                <p className="text-green-400 font-semibold tabular-nums">{genCompleted}</p>
              </div>
              <div className="rounded-lg bg-white/[0.03] p-3">
                <p className="text-[11px] text-slate-500">Failed</p>
                <p className="text-red-400 font-semibold tabular-nums">{genFailed}</p>
              </div>
            </div>
            <p className="text-[11px] text-slate-600 mt-3">Avg latency {fmtDuration(k.avg_gen_seconds)} · {genTotal} runs</p>
          </div>

          {/* Word metrics */}
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Avg Words / Piece</p>
            {wordData.length ? (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={wordData} margin={{ left: -8, right: 8 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="name" stroke={AXIS} fontSize={11} />
                  <YAxis stroke={AXIS} fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="avg" radius={[4, 4, 0, 0]} barSize={40}>
                    {wordData.map((d) => (
                      <Cell key={d.key} fill={PLATFORM_COLORS[d.key]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-600 text-sm py-12 text-center">No content yet.</p>
            )}
          </div>
        </div>
      </section>

      {/* Per-plan table */}
      <section>
        <SectionHeader label="Plans" hint={`${plans.length} total`} />
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-bold tracking-[0.15em] uppercase text-slate-500 border-b border-white/5">
                  <th className="text-left px-5 py-3">Plan</th>
                  <th className="text-left px-5 py-3">Type</th>
                  <th className="text-center px-5 py-3">Topics</th>
                  <th className="text-center px-5 py-3">Published</th>
                  <th className="text-left px-5 py-3 w-48">Completion</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((p) => {
                  const items = p.item_count ?? 0;
                  const pub = p.published_count ?? 0;
                  const pct = items ? Math.round((100 * pub) / items) : 0;
                  return (
                    <tr key={p.id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03] transition-colors">
                      <td className="px-5 py-3">
                        <Link href={`/planner?plan=${p.id}`} className="text-white hover:text-blue-300 transition-colors font-medium">
                          {p.name}
                        </Link>
                        <span className="ml-2 text-[10px] uppercase tracking-wider text-slate-600">{p.status}</span>
                      </td>
                      <td className="px-5 py-3 text-slate-400 capitalize">{p.plan_type}</td>
                      <td className="px-5 py-3 text-center text-slate-300 tabular-nums">{items}</td>
                      <td className="px-5 py-3 text-center text-slate-300 tabular-nums">{pub}</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-white/10 rounded-full h-2 overflow-hidden">
                            <div className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-green-500" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-[11px] text-slate-500 tabular-nums w-9 text-right">{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}

function ScheduleRow({
  icon: Icon,
  label,
  value,
  total,
  color,
  tint,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  total: number;
  color: string;
  tint: string;
}) {
  const pct = total ? Math.round((100 * value) / total) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className={`flex items-center gap-1.5 text-xs ${tint}`}>
          <Icon className="w-3.5 h-3.5" />
          {label}
        </span>
        <span className="text-xs text-slate-400 tabular-nums">
          {value} <span className="text-slate-600">({pct}%)</span>
        </span>
      </div>
      <div className="bg-white/10 rounded-full h-2 overflow-hidden">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
