"use client";

import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Calendar,
  CalendarDays,
  CheckCircle2,
  Clock,
  DollarSign,
  Flame,
  Globe,
  ListOrdered,
  Map,
  Puzzle,
  Ruler,
  Sparkles,
  Star,
  Tag,
  Target,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import {
  BUCKET_ORDER,
  fmtCompact,
  fmtDate,
  fmtDuration,
  fmtNum,
  formatModelName,
  type BreakoutVideo,
  type ProspectChannel,
  type ProspectHeadline,
  type ProspectMetrics,
  type ProspectReport,
  type SimilarChannel,
  type Strategy,
} from "@/lib/youtubeProspectsApi";
import { derivePeakTiming } from "@/lib/timingAnalysis";

// ── Print Header & Footer Component ──────────────────────────────────────────

function ReportPageHeader({
  channel,
  pageNumber,
  totalPages,
  report,
}: {
  channel: ProspectChannel;
  pageNumber: number;
  totalPages: number;
  report: ProspectReport;
}) {
  return (
    <header className="border-b-2 border-purple-600/30 pb-3 mb-5 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-sm flex-shrink-0">
          G
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xs font-black tracking-wider uppercase text-purple-950">
              GROWTH INTELLIGENCE
            </h1>
            <span className="text-[10px] font-semibold bg-purple-100 text-purple-800 px-2 py-0.2 rounded-full border border-purple-200">
              Channel Intelligence Audit
            </span>
          </div>
          <p className="text-[11px] font-medium text-slate-600">
            Prepared for <strong className="text-slate-900">{channel.title}</strong>
            {channel.handle ? ` (${channel.handle})` : ""}
          </p>
        </div>
      </div>

      <div className="text-right">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Page {pageNumber} of {totalPages}
        </p>
        <p className="text-[10px] text-slate-500 mt-0.5">
          {fmtDate(report.generated_at)}
        </p>
      </div>
    </header>
  );
}

function ReportPageFooter({
  channel,
  pageNumber,
  totalPages,
}: {
  channel: ProspectChannel;
  pageNumber: number;
  totalPages: number;
}) {
  return (
    <footer className="border-t border-slate-200 pt-2.5 mt-auto flex items-center justify-between text-[10px] text-slate-500">
      <div className="flex items-center gap-2">
        <span className="font-bold text-purple-700 tracking-wide">GROWTH INTELLIGENCE</span>
        <span>·</span>
        <span>Confidential Growth Intelligence Report</span>
      </div>
      <div className="flex items-center gap-2">
        <span>Prepared for {channel.title}</span>
        <span>·</span>
        <span className="font-semibold text-slate-700">
          Page {pageNumber} of {totalPages}
        </span>
      </div>
    </footer>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────────

function SafeAvatar({
  url,
  title,
  size = "lg",
}: {
  url?: string | null;
  title: string;
  size?: "sm" | "md" | "lg";
}) {
  const [error, setError] = useState(false);
  const initial = title ? title.charAt(0).toUpperCase() : "C";
  const sizeClasses = {
    sm: "w-8 h-8 text-xs",
    md: "w-10 h-10 text-sm",
    lg: "w-13 h-13 text-base",
  }[size];

  if (!url || error) {
    return (
      <div
        className={`${sizeClasses} rounded-full bg-gradient-to-tr from-purple-600 to-indigo-600 border border-slate-200 flex items-center justify-center font-bold text-white flex-shrink-0 shadow-sm`}
      >
        {initial}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={title}
      referrerPolicy="no-referrer"
      onError={() => setError(true)}
      className={`${sizeClasses} rounded-full border border-slate-200 flex-shrink-0 object-cover`}
    />
  );
}

function LightStat({
  label,
  value,
  hint,
  accentColor = "text-slate-900",
}: {
  label: string;
  value: string;
  hint?: string;
  accentColor?: string;
}) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200/80 p-2.5 flex flex-col justify-between">
      <p className="text-[9px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-0.5 text-base font-black tabular-nums ${accentColor}`}>{value}</p>
      {hint ? <p className="text-[10px] text-slate-500 mt-0.5 leading-tight">{hint}</p> : null}
    </div>
  );
}

function LightSection({
  icon: Icon,
  title,
  tint,
  items,
  ordered = false,
}: {
  icon: React.ElementType;
  title: string;
  tint: string;
  items: string[];
  ordered?: boolean;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-xs">
      <p className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider mb-2 ${tint}`}>
        <Icon size={13} /> {title}
      </p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-xs text-slate-700 leading-relaxed">
            {ordered ? (
              <span className={`text-[11px] font-bold tabular-nums ${tint} flex-shrink-0 w-3.5`}>
                {i + 1}.
              </span>
            ) : (
              <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${tint.replace("text-", "bg-")}`} />
            )}
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const FORMAT_TINTS: Record<string, string> = {
  tutorial: "bg-blue-100 text-blue-800 border-blue-200",
  shorts: "bg-pink-100 text-pink-800 border-pink-200",
  "deep-dive": "bg-purple-100 text-purple-800 border-purple-200",
  series: "bg-amber-100 text-amber-800 border-amber-200",
  comparison: "bg-teal-100 text-teal-800 border-teal-200",
};

function FormatBadge({ format }: { format: string }) {
  if (!format) return null;
  const tint =
    FORMAT_TINTS[format.toLowerCase().trim()] ||
    "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold border ${tint}`}
    >
      {format}
    </span>
  );
}

// ── Main Paginated Print Component ───────────────────────────────────────────

export default function ProspectPrintReportView({ report }: { report: ProspectReport }) {
  const { channel, metrics, audit, roadmap, headline, similar_channels } = report;
  const breakoutVideos = metrics.breakout_videos || [];
  const weeks = roadmap.weeks || [];
  const totalUploads = metrics.video_count_analyzed || channel.video_count;

  const avgDuration =
    metrics.avg_video_length_seconds && metrics.avg_video_length_seconds > 0
      ? fmtDuration(metrics.avg_video_length_seconds)
      : metrics.avg_long_form_length_seconds && metrics.avg_long_form_length_seconds > 0
      ? fmtDuration(metrics.avg_long_form_length_seconds)
      : "—";

  // Calculate total pages dynamically:
  // Page 1 = Audit & Core Performance
  // Page 2 = Breakout Videos & Topic/Timing Intelligence
  // Page 3+ = Roadmap (2 weeks per page)
  const roadmapPages = Math.max(1, Math.ceil(weeks.length / 2));
  const totalPages = 2 + roadmapPages;

  return (
    <div className="print-document bg-white text-slate-900 antialiased">
      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* PAGE 1: Channel Overview + Core Performance + Timeframe + Strategy     */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      <section className="print-page min-h-[270mm] p-6 flex flex-col justify-between bg-white border border-slate-200 mb-8 print:border-0 print:mb-0 print:p-0">
        <div>
          <ReportPageHeader
            channel={channel}
            pageNumber={1}
            totalPages={totalPages}
            report={report}
          />

          {/* Channel Identity & Vitals Strip */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 mb-3.5">
            <div className="flex items-center justify-between gap-3 mb-2.5 pb-2.5 border-b border-slate-200">
              <div className="flex items-center gap-3">
                <SafeAvatar url={channel.thumbnail_url} title={channel.title} size="md" />
                <div>
                  <h2 className="text-base font-black text-slate-900 leading-tight">
                    {channel.title}
                  </h2>
                  <p className="text-[11px] text-slate-600">
                    {channel.handle || channel.channel_id}
                    {channel.country ? ` · ${channel.country}` : ""}
                    {channel.subscriber_count ? ` · ${fmtCompact(channel.subscriber_count)} subscribers` : ""}
                    {channel.view_count ? ` · ${fmtCompact(channel.view_count)} total views` : ""}
                    {totalUploads ? ` · ${fmtCompact(totalUploads)} uploads` : ""}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-200">
                  <Sparkles size={10} /> Full Growth Audit
                </span>
              </div>
            </div>

            {/* Quick Vitals Strip */}
            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="bg-white rounded-lg border border-slate-200/80 p-2">
                <p className="text-[8px] uppercase font-bold text-slate-500">Avg Duration</p>
                <p className="text-xs font-black text-blue-700 mt-0.5">{avgDuration}</p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200/80 p-2">
                <p className="text-[8px] uppercase font-bold text-slate-500">Upload Cadence</p>
                <p className="text-xs font-black text-purple-700 mt-0.5 truncate" title={metrics.upload_frequency}>
                  {metrics.upload_frequency || "—"}
                </p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200/80 p-2">
                <p className="text-[8px] uppercase font-bold text-slate-500">Est. Monthly</p>
                <p className="text-xs font-black text-emerald-700 mt-0.5">
                  {metrics.est_monthly_earnings || "—"}
                </p>
              </div>
              <div className="bg-white rounded-lg border border-slate-200/80 p-2">
                <p className="text-[8px] uppercase font-bold text-slate-500">30d Velocity</p>
                <p className="text-xs font-black text-slate-900 mt-0.5">
                  {fmtCompact(metrics.est_monthly_views || metrics.views_last_30d)}/mo
                </p>
              </div>
            </div>
          </div>

          {/* Core Performance Stats */}
          <div className="mb-3.5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1">
              <Activity size={12} className="text-purple-600" /> Core Channel Benchmarks
            </p>
            <div className="grid grid-cols-4 gap-2">
              <LightStat
                label="Average Views"
                value={fmtNum(metrics.avg_views)}
                hint={`across ${metrics.video_count_analyzed} uploads`}
                accentColor="text-purple-900"
              />
              <LightStat
                label="Median Views"
                value={fmtNum(metrics.median_views)}
                hint="typical upload baseline"
              />
              <LightStat
                label="Engagement"
                value={metrics.engagement_rate != null ? `${metrics.engagement_rate}%` : "n/a"}
                hint="likes + comments / views"
                accentColor="text-emerald-700"
              />
              <LightStat
                label="Upload Frequency"
                value={`${metrics.uploads_last_30 ?? 0} in 30d`}
                hint={
                  metrics.days_since_upload != null
                    ? `${metrics.days_since_upload}d since last upload`
                    : undefined
                }
              />
            </div>
          </div>

          {/* Key Highlight Banner */}
          {headline ? (
            <div className="rounded-lg border border-emerald-300 bg-emerald-50/70 p-2.5 flex items-start gap-2 mb-3.5 text-xs text-emerald-950">
              <TrendingUp size={15} className="text-emerald-600 flex-shrink-0 mt-0.5" />
              <p className="leading-snug">
                {headline.kind === "cadence" ? (
                  <>
                    <strong>{headline.value} days</strong> since last upload, following{" "}
                    <strong>{headline.baseline}</strong> in the previous 90.
                  </>
                ) : (
                  <>
                    <strong>
                      {headline.kind === "duration_bucket"
                        ? `${headline.label} videos`
                        : `Videos about "${headline.label}"`}
                    </strong>{" "}
                    have a {headline.value_kind ?? "median"} of{" "}
                    <strong>{fmtNum(headline.value)}</strong> views —{" "}
                    <strong className="text-emerald-800">
                      {headline.multiple}× the channel {headline.baseline_kind ?? "median"} of{" "}
                      {fmtNum(headline.baseline)}
                    </strong>
                    <span className="text-emerald-700"> (n={headline.sample})</span>.
                    {headline.avg_value != null && headline.channel_avg_views ? (
                      <span className="text-emerald-700">
                        {" "}
                        Mean {fmtNum(headline.avg_value)} vs channel average{" "}
                        {fmtNum(headline.channel_avg_views)}.
                      </span>
                    ) : null}
                  </>
                )}
              </p>
            </div>
          ) : null}

          {/* Timeframe Analytics Strip */}
          {metrics.timeframe_analytics && (
            <div className="mb-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1">
                <BarChart3 size={12} className="text-blue-600" /> Timeframe Analytics
              </p>
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2">
                  <div className="flex justify-between items-center text-[9px] font-bold text-blue-700 uppercase">
                    <span>Last 7 Days</span>
                    <span className="bg-blue-100 text-blue-800 px-1 rounded">Weekly</span>
                  </div>
                  <p className="text-sm font-black text-slate-900 mt-1">
                    +{fmtNum(metrics.timeframe_analytics.last_7d.views)} views
                  </p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {metrics.timeframe_analytics.last_7d.uploads} uploads · {metrics.timeframe_analytics.last_7d.est_earnings || "—"}
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2">
                  <div className="flex justify-between items-center text-[9px] font-bold text-purple-700 uppercase">
                    <span>Last 28 Days</span>
                    <span className="bg-purple-100 text-purple-800 px-1 rounded">Monthly</span>
                  </div>
                  <p className="text-sm font-black text-slate-900 mt-1">
                    +{fmtNum(metrics.timeframe_analytics.last_28d.views)} views
                  </p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {metrics.timeframe_analytics.last_28d.uploads} uploads · {metrics.timeframe_analytics.last_28d.est_earnings || "—"}
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2">
                  <div className="flex justify-between items-center text-[9px] font-bold text-emerald-700 uppercase">
                    <span>Annual (365 Days)</span>
                    <span className="bg-emerald-100 text-emerald-800 px-1 rounded">1 Year</span>
                  </div>
                  <p className="text-sm font-black text-slate-900 mt-1">
                    +{fmtNum(metrics.timeframe_analytics.last_1y.views)} views
                  </p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {metrics.timeframe_analytics.last_1y.uploads} uploads · {metrics.timeframe_analytics.last_1y.est_earnings || "—"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* AI Strategy Insights Grid */}
          <div className="grid grid-cols-2 gap-2.5 mb-2.5">
            <LightSection
              icon={CheckCircle2}
              title="What's Working"
              tint="text-emerald-700"
              items={audit.whats_working}
            />
            <LightSection
              icon={AlertTriangle}
              title="Underperforming Formats"
              tint="text-rose-700"
              items={audit.underperforming}
            />
            <LightSection
              icon={Ruler}
              title="Format & Cadence"
              tint="text-blue-700"
              items={audit.format_insights}
            />
            <LightSection
              icon={Puzzle}
              title="Identified Content Gaps"
              tint="text-amber-700"
              items={audit.content_gaps}
            />
          </div>

          {/* Priority Actions */}
          {audit.priorities && audit.priorities.length > 0 && (
            <LightSection
              icon={ListOrdered}
              title="Strategic Priorities & Next Steps"
              tint="text-purple-800"
              items={audit.priorities}
              ordered
            />
          )}
        </div>

        <ReportPageFooter channel={channel} pageNumber={1} totalPages={totalPages} />
      </section>

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* PAGE 2: Breakout Videos, Winning Formula, Keywords & Best Timing       */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      <section className="print-page min-h-[270mm] p-6 flex flex-col justify-between bg-white border border-slate-200 mb-8 print:border-0 print:mb-0 print:p-0 page-break-before">
        <div>
          <ReportPageHeader
            channel={channel}
            pageNumber={2}
            totalPages={totalPages}
            report={report}
          />


          {/* Top Breakout Videos Grid */}
          {breakoutVideos.length > 0 && (
            <div className="mb-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1">
                <Flame size={12} className="text-orange-600" /> Top Breakout Outlier Videos
              </p>
              <div className="grid grid-cols-3 gap-2.5">
                {breakoutVideos.slice(0, 3).map((v) => (
                  <div
                    key={v.video_id}
                    className="rounded-lg border border-slate-200 bg-slate-50/70 p-2 flex flex-col justify-between"
                  >
                    <div className="relative aspect-video rounded overflow-hidden bg-slate-200 mb-1.5">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`https://i.ytimg.com/vi/${v.video_id}/hqdefault.jpg`}
                        alt={v.title}
                        referrerPolicy="no-referrer"
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute top-1 right-1 bg-orange-600 text-white font-bold text-[9px] px-1.5 py-0.5 rounded shadow">
                        {v.multiplier}× Breakout
                      </div>
                      {v.duration_seconds > 0 && (
                        <div className="absolute bottom-1 right-1 bg-black/80 text-white text-[8px] px-1 rounded">
                          {fmtDuration(v.duration_seconds)}
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="text-[11px] font-bold text-slate-900 line-clamp-2 leading-tight">
                        {v.title}
                      </p>
                      <div className="flex justify-between items-center text-[10px] text-slate-500 mt-1">
                        <span className="font-bold text-orange-700">{fmtNum(v.views)} views</span>
                        <span>{v.published_at}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SEO & Topic Performance */}
          {metrics.keyword_analysis?.top_keywords && (
            <div className="mb-3.5">
              <div className="flex justify-between items-center mb-1.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Target size={12} className="text-emerald-600" /> Topic & Keyword Performance
                </p>
                {metrics.keyword_analysis.avg_seo_score != null && (
                  <span className="text-[10px] text-slate-600">
                    Title SEO Score:{" "}
                    <strong className="text-emerald-700">{metrics.keyword_analysis.avg_seo_score}/100</strong>
                  </span>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2">
                {metrics.keyword_analysis.top_keywords.slice(0, 3).map((k) => (
                  <div
                    key={k.keyword}
                    className="rounded-lg border border-slate-200 bg-white p-2 flex flex-col justify-between"
                  >
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-slate-900 truncate">{k.keyword}</span>
                      <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                        {k.multiplier}×
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      {k.video_count} videos · {fmtNum(k.avg_views)} avg
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upload Timing & Best Slot */}
          {metrics.upload_timing?.has_timing_data && (() => {
            const peakTiming = derivePeakTiming(metrics.upload_timing);
            return (
              <div className="mb-3.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1">
                  <Clock size={12} className="text-amber-600" /> Optimal Upload Timing & Day Velocity
                </p>

                <div
                  className={`rounded-lg border p-2.5 mb-2 flex items-center justify-between gap-3 ${
                    peakTiming.status === "VALID_PEAK"
                      ? "border-amber-300 bg-amber-50/70"
                      : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          peakTiming.status === "VALID_PEAK"
                            ? "bg-amber-200 text-amber-900"
                            : "bg-slate-200 text-slate-700"
                        }`}
                      >
                        {peakTiming.badgeText}
                      </span>
                      <p className="text-xs font-bold text-slate-900">
                        {peakTiming.cardTitle}
                      </p>
                      {peakTiming.status === "VALID_PEAK" && peakTiming.multiplier > 1.0 && (
                        <span className="text-[9px] font-bold text-emerald-700">
                          +{Math.round((peakTiming.multiplier - 1.0) * 100)}% on {peakTiming.peakDay}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-slate-600 mt-0.5">
                      {peakTiming.summaryText}
                    </p>
                    {peakTiming.status === "VALID_PEAK" && metrics.upload_timing?.best_window?.top_video_proof && (
                      <p className="text-[10px] text-amber-800 mt-0.5">
                        {metrics.upload_timing.best_window.top_video_proof}
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0 bg-white border border-slate-200 px-2 py-1 rounded text-center">
                    <p className="text-[8px] uppercase font-bold text-slate-500">Day Velocity</p>
                    <p
                      className={`text-sm font-black ${
                        peakTiming.status === "VALID_PEAK" ? "text-amber-800" : "text-slate-600"
                      }`}
                    >
                      {peakTiming.multiplierDisplay}
                    </p>
                    <p className="text-[8px] text-slate-500">{peakTiming.multiplierSubtext}</p>
                  </div>
                </div>

                {/* 7-Day Velocity Bars */}
                <div className="grid grid-cols-7 gap-1 text-center">
                  {metrics.upload_timing.days.map((d) => {
                    const isPeak = peakTiming.isPeakDay(d.day);
                    return (
                      <div
                        key={d.day}
                        className={`rounded border p-1.5 ${
                          isPeak
                            ? "bg-amber-100 border-amber-400 font-bold"
                            : "bg-slate-50 border-slate-200"
                        }`}
                      >
                        <p className="text-[9px] text-slate-600 uppercase">{d.day_short}</p>
                        <p className="text-[11px] font-bold text-slate-900 mt-0.5">{d.multiplier}×</p>
                        <p className="text-[8px] text-slate-500">n={d.video_count}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Similar Benchmark Channels */}
          {similar_channels && similar_channels.length > 0 && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1">
                <Users size={12} className="text-purple-600" /> Benchmark Peer Channels
              </p>
              <div className="grid grid-cols-4 gap-2">
                {similar_channels.slice(0, 4).map((c) => (
                  <div
                    key={c.channel_id}
                    className="rounded-lg border border-slate-200 bg-white p-2 flex items-center gap-2"
                  >
                    <SafeAvatar url={c.thumbnail_url} title={c.title} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] font-bold text-slate-900 truncate">{c.title}</p>
                      <p className="text-[9px] text-slate-500 truncate">
                        {c.subscriber_count ? `${fmtCompact(c.subscriber_count)} subs` : "Creator"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <ReportPageFooter channel={channel} pageNumber={2} totalPages={totalPages} />
      </section>

      {/* ────────────────────────────────────────────────────────────────────── */}
      {/* PAGES 3+: 30-Day Content Roadmap (2 Weeks Per Page)                    */}
      {/* ────────────────────────────────────────────────────────────────────── */}
      {Array.from({ length: roadmapPages }).map((_, pageIdx) => {
        const pageNum = 3 + pageIdx;
        const pageWeeks = weeks.slice(pageIdx * 2, pageIdx * 2 + 2);

        return (
          <section
            key={`roadmap-page-${pageIdx}`}
            className="print-page min-h-[270mm] p-6 flex flex-col justify-between bg-white border border-slate-200 mb-8 print:border-0 print:mb-0 print:p-0 page-break-before"
          >
            <div>
              <ReportPageHeader
                channel={channel}
                pageNumber={pageNum}
                totalPages={totalPages}
                report={report}
              />

              {/* Roadmap Header */}
              <div className="rounded-xl border border-purple-200 bg-purple-50/70 p-3.5 mb-4 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Map size={16} className="text-purple-700" />
                    <h2 className="text-sm font-black text-purple-950">
                      30-Day Content Roadmap {roadmapPages > 1 ? `(Part ${pageIdx + 1})` : ""}
                    </h2>
                  </div>
                  <p className="text-xs text-purple-900 mt-0.5">
                    Recommended schedule and strategic video concepts based on breakout signals
                  </p>
                </div>
                {roadmap.cadence ? (
                  <div className="text-right bg-white border border-purple-200 px-3 py-1 rounded-lg">
                    <p className="text-[8px] uppercase font-bold text-slate-500">Cadence</p>
                    <p className="text-xs font-bold text-purple-800">{roadmap.cadence}</p>
                  </div>
                ) : null}
              </div>

              {/* Weekly Cards (2 per page) */}
              <div className="space-y-4">
                {pageWeeks.map((week) => (
                  <div
                    key={week.week_number}
                    className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs"
                  >
                    <div className="flex items-baseline justify-between border-b border-slate-100 pb-2 mb-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-black uppercase tracking-wider text-purple-700 bg-purple-100 px-2 py-0.5 rounded">
                          Week {week.week_number}
                        </span>
                        {week.focus ? (
                          <p className="text-xs font-bold text-slate-900">{week.focus}</p>
                        ) : null}
                      </div>
                      <p className="text-[11px] font-medium text-slate-500 flex items-center gap-1">
                        <CalendarDays size={11} className="text-purple-600" />
                        {fmtDate(week.start_date)}
                      </p>
                    </div>

                    <ul className="space-y-2.5">
                      {(week.items || []).map((item, i) => (
                        <li
                          key={i}
                          className="border-l-2 border-purple-500 pl-3 py-0.5 bg-slate-50/50 rounded-r p-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-bold text-slate-900 leading-snug">
                              {item.title}
                            </p>
                            <FormatBadge format={item.format} />
                          </div>

                          <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-1">
                            {item.date ? (
                              <span className="font-semibold text-slate-700">
                                📅 {fmtDate(item.date)}
                              </span>
                            ) : null}
                            {item.theme ? (
                              <span>· Focus: <strong>{item.theme}</strong></span>
                            ) : null}
                          </div>

                          {item.rationale ? (
                            <p className="text-[11px] text-slate-600 mt-1 leading-relaxed">
                              {item.rationale}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              {/* End of plan summary if last page */}
              {pageNum === totalPages && (
                <div className="mt-4 rounded-xl border border-purple-200 bg-gradient-to-r from-purple-50 via-indigo-50 to-blue-50 p-3 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold text-purple-950 flex items-center gap-1.5">
                      <Sparkles size={13} className="text-purple-700" /> Ready to Execute this Plan?
                    </p>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      Automated scriptwriting, visual asset creation, and optimal scheduling.
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-black text-purple-700 tracking-wider">
                      GROWTH INTELLIGENCE
                    </span>
                  </div>
                </div>
              )}
            </div>

            <ReportPageFooter channel={channel} pageNumber={pageNum} totalPages={totalPages} />
          </section>
        );
      })}
    </div>
  );
}
