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
  Puzzle,
  Ruler,
  Sparkles,
  Star,
  Tag,
  Target,
  Timer,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import { Section } from "@/components/youtube/shared/ReportSections";
import {
  BUCKET_ORDER,
  fmtCompact,
  fmtDuration,
  fmtNum,
  type ProspectChannel,
  type ProspectHeadline,
  type ProspectMetrics,
  type SimilarChannel,
  type Strategy,
} from "@/lib/youtubeProspectsApi";
import { derivePeakTiming } from "@/lib/timingAnalysis";

/**
 * Screenshot target #1: the channel audit with vidIQ-grade channel vitals.
 */

function ChannelAvatar({
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
    lg: "w-14 h-14 text-lg",
  }[size];

  if (!url || error) {
    return (
      <div
        className={`${sizeClasses} rounded-full bg-gradient-to-tr from-red-600/40 via-purple-600/30 to-blue-600/40 border border-white/10 flex items-center justify-center font-bold text-white flex-shrink-0 shadow-inner`}
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
      className={`${sizeClasses} rounded-full border border-white/10 flex-shrink-0 object-cover`}
    />
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-[#0f172a] border border-white/10 px-4 py-3">
      <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-bold text-white tabular-nums">{value}</p>
      {hint ? <p className="text-[11px] text-slate-500 mt-0.5">{hint}</p> : null}
    </div>
  );
}

/**
 * Two things this chart must not do, because a creator reads it next to the
 * headline banner and can point at either:
 *
 * 1. Print a different number for the same bucket than the banner does. The
 *    banner quotes the bucket MEDIAN (that is what the headline gate is struck
 *    on); this used to quote the mean, and both were labelled "avg".
 * 2. Let a one-video bucket set the scale. A single 1.5M-view upload in the
 *    1-5 min bucket rendered as the tallest, greenest bar on the chart —
 *    directly beside a recommendation to publish fewer short videos.
 */
function LengthBars({ metrics }: { metrics: ProspectMetrics }) {
  const minSample = metrics.rules?.min_bucket_sample ?? 3;
  const buckets = metrics.buckets || {};
  const present = BUCKET_ORDER.filter((b) => buckets[b]);
  if (!present.length) {
    return (
      <p className="text-sm text-slate-500 italic">
        Video durations were not available for this channel, so length performance could not be
        measured.
      </p>
    );
  }

  // Scale on the buckets that are actually comparable, so a thin one cannot
  // squash every real bar against the axis.
  const comparable = present.filter((b) => buckets[b].count >= minSample);
  const max = Math.max(...(comparable.length ? comparable : present).map((b) => buckets[b].median_views), 1);
  const channelMedian = metrics.median_views || 0;
  const channelAvg = metrics.avg_views || 0;
  const hasThin = present.some((b) => buckets[b].count < minSample);

  return (
    <div className="space-y-2.5">
      {present.map((bucket) => {
        const stats = buckets[bucket];
        const thin = stats.count < minSample;
        const pct = Math.min(100, (stats.median_views / max) * 100);
        const beatsChannel = !thin && channelMedian > 0 && stats.median_views > channelMedian;
        return (
          <div key={bucket}>
            <div className="flex items-baseline justify-between text-xs mb-1 gap-3">
              <span className={beatsChannel ? "text-emerald-300 font-semibold" : "text-slate-400"}>
                {bucket}
                <span className="text-slate-600"> · n={stats.count}</span>
                {thin ? (
                  <span className="ml-1.5 text-[10px] font-medium text-amber-400/80">
                    too few to compare
                  </span>
                ) : null}
              </span>
              <span
                className={`tabular-nums font-semibold text-right ${
                  beatsChannel ? "text-emerald-300" : thin ? "text-slate-500" : "text-slate-400"
                }`}
              >
                {fmtNum(stats.median_views)} median
                <span className="text-slate-600 font-normal"> · {fmtNum(stats.avg_views)} avg</span>
              </span>
            </div>
            <div className="w-full bg-white/[0.06] rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${
                  beatsChannel
                    ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                    : thin
                    ? "bg-slate-700/60"
                    : "bg-slate-600"
                }`}
                style={{ width: `${Math.max(pct, 2)}%` }}
              />
            </div>
          </div>
        );
      })}
      {channelMedian > 0 || channelAvg > 0 ? (
        <p className="text-[11px] text-slate-500 pt-1">
          Bars are scaled on the median. Across all {metrics.video_count_analyzed} analysed videos
          this channel runs {fmtNum(channelMedian)} median · {fmtNum(channelAvg)} average views.
        </p>
      ) : null}
      {hasThin ? (
        <p className="text-[11px] text-amber-400/70">
          Buckets under {minSample} videos are shown for completeness and are excluded from
          every recommendation — a single upload is not a trend.
        </p>
      ) : null}
    </div>
  );
}

function UploadTimingSection({ metrics }: { metrics: ProspectMetrics }) {
  const timing = metrics.upload_timing;
  if (!timing || !timing.has_timing_data || !timing.days || !timing.days.length) {
    return null;
  }

  const peakTiming = derivePeakTiming(timing);
  const bestWindow = timing.best_window;
  const maxDayAvg = Math.max(...timing.days.map((d) => d.avg_views), 1);
  // The exact list the backend cited and the validator checked — not a fresh
  // slice, which could disagree with what was validated.
  const evidence = timing.evidence_videos ?? timing.top_timing_videos.slice(0, 3);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Clock size={14} className="text-amber-400" /> Best Day & Time to Post
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Calculated from upload timestamps of this channel&apos;s top-performing and breakout videos
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-[#0f172a] border border-white/10 px-2.5 py-1 rounded-lg text-[11px] text-slate-400">
          <Globe size={12} className="text-blue-400" />
          <span>UTC Timestamps</span>
        </div>
      </div>

      {/* Hero Winning Window Card */}
      <div
        className={`rounded-xl border p-4 relative overflow-hidden transition-all ${
          peakTiming.status === "VALID_PEAK"
            ? "border-amber-500/30 bg-gradient-to-r from-amber-500/[0.12] via-purple-500/[0.08] to-blue-500/[0.06]"
            : "border-slate-800 bg-[#0b101e]/80"
        }`}
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full flex items-center gap-1 border ${
                  peakTiming.status === "VALID_PEAK"
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                    : "bg-slate-700/40 text-slate-400 border-slate-600/40"
                }`}
              >
                <Star
                  size={10}
                  className={
                    peakTiming.status === "VALID_PEAK"
                      ? "fill-amber-300 text-amber-300"
                      : "text-slate-400"
                  }
                />{" "}
                {peakTiming.badgeText}
              </span>
              {peakTiming.status === "VALID_PEAK" && peakTiming.multiplier > 1.0 && (
                <span className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
                  <TrendingUp size={10} /> +{Math.round((peakTiming.multiplier - 1.0) * 100)}% on{" "}
                  {peakTiming.peakDay}
                </span>
              )}
            </div>
            <h3 className="text-lg font-bold text-white tracking-tight">
              {peakTiming.cardTitle}
            </h3>
            <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
              {peakTiming.summaryText}
            </p>
            {peakTiming.status === "VALID_PEAK" && bestWindow?.top_video_proof && (
              <p className="text-[11px] text-amber-200/80 font-medium flex items-center gap-1">
                <Flame size={12} className="text-orange-400" /> {bestWindow.top_video_proof}
              </p>
            )}
            {/* One gate, one message. The narrative on the page before reads
                the same flag, so it can no longer recommend an hour while this
                says none can be named. */}
            {peakTiming.status === "VALID_PEAK" && !bestWindow?.slot_confident && (
              <p className="text-[11px] text-slate-400 flex items-center gap-1">
                <Timer size={12} className="text-slate-500" />{" "}
                {timing.time_of_day_allowed === false || !timing.has_hour_data
                  ? "Too few uploads carry a publish time to call a time of day — this recommends a day only."
                  : "No time window survived its evidence check — this recommends a day only."}
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0 bg-[#080d1a]/80 border border-white/10 p-3 rounded-xl">
            {/* Day and time are separate findings with separate samples. They
                are never merged into one "multiplier", because a time claim
                backed by a day statistic is how the wrong window shipped. */}
            <div className="text-center px-2">
              <p className="text-[9px] uppercase font-bold text-slate-500">Best Day</p>
              <p
                className={`text-xl font-bold tabular-nums ${
                  peakTiming.status === "VALID_PEAK" ? "text-amber-300" : "text-slate-400"
                }`}
              >
                {peakTiming.multiplierDisplay}
              </p>
              <p className="text-[9px] text-slate-400">{peakTiming.multiplierSubtext}</p>
            </div>
            <div className="h-8 w-px bg-white/10" />
            <div className="text-center px-2">
              <p className="text-[9px] uppercase font-bold text-slate-500">Best Window</p>
              <p className="text-xl font-bold text-blue-300 tabular-nums">
                {peakTiming.status === "VALID_PEAK" && bestWindow?.slot_multiplier != null
                  ? `${bestWindow.slot_multiplier}×`
                  : "—"}
              </p>
              <p className="text-[9px] text-slate-400">
                {peakTiming.status === "VALID_PEAK" && bestWindow?.slot_multiplier != null
                  ? `n=${bestWindow.slot_sample} · vs median`
                  : "not enough data"}
              </p>
            </div>
            <div className="h-8 w-px bg-white/10" />
            <div className="text-center px-2">
              <p className="text-[9px] uppercase font-bold text-slate-500">Proof</p>
              <p className="text-xs font-bold text-white">
                {peakTiming.status === "VALID_PEAK" && bestWindow
                  ? `${bestWindow.proof_count} of top ${bestWindow.top_tier_count}`
                  : "—"}
              </p>
              <p className="text-[9px] text-slate-400">by views</p>
            </div>
          </div>
        </div>
      </div>

      {/* 7-Day Performance Heatmap & Distribution Bars */}
      <div>
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1">
          <Calendar size={12} className="text-purple-400" /> Day of Week View Velocity
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          {timing.days.map((d) => {
            const pct = maxDayAvg > 0 ? Math.max(6, (d.avg_views / maxDayAvg) * 100) : 6;
            const isPeak = peakTiming.isPeakDay(d.day);
            const isTop = isPeak || (d.video_count >= 3 && d.multiplier >= 1.25);
            const isZero = d.video_count === 0;

            return (
              <div
                key={d.day}
                className={`rounded-xl border p-3 flex flex-col justify-between transition-all ${
                  isPeak
                    ? "bg-amber-500/[0.08] border-amber-500/40 shadow-sm"
                    : isTop
                    ? "bg-emerald-500/[0.05] border-emerald-500/30"
                    : isZero
                    ? "bg-[#0b101e] border-white/5 opacity-50"
                    : "bg-[#0f172a] border-white/10 hover:border-white/20"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span
                      className={`text-xs font-bold ${
                        isPeak
                          ? "text-amber-300"
                          : isTop
                          ? "text-emerald-300"
                          : "text-slate-300"
                      }`}
                    >
                      {d.day_short}
                    </span>
                    {isPeak ? (
                      <span className="bg-amber-500/20 text-amber-300 text-[9px] font-bold px-1 rounded flex items-center gap-0.5">
                        <Star size={9} className="fill-amber-300" /> Best
                      </span>
                    ) : d.multiplier >= 1.1 && d.video_count >= 3 ? (
                      <span className="text-[10px] font-semibold text-emerald-400">
                        {d.multiplier}×
                      </span>
                    ) : d.video_count > 0 ? (
                      <span className="text-[10px] font-medium text-slate-500">
                        {d.multiplier}×
                      </span>
                    ) : null}
                  </div>

                  <p className="text-sm font-bold text-white tabular-nums">
                    {d.video_count > 0 ? fmtNum(d.avg_views) : "—"}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {d.video_count} upload{d.video_count === 1 ? "" : "s"}
                    {d.top_video_count > 0 ? ` · ${d.top_video_count} top` : ""}
                  </p>
                </div>

                {/* Vertical Bar Meter */}
                <div className="mt-2.5 pt-2 border-t border-white/5">
                  <div className="w-full bg-white/[0.06] rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full ${
                        isPeak
                          ? "bg-gradient-to-r from-amber-500 to-yellow-400"
                          : isTop
                          ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                          : isZero
                          ? "bg-transparent"
                          : "bg-slate-600"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Time Slot Windows (if hour data available) */}
      {timing.has_hour_data && timing.time_slots && timing.time_slots.length > 0 && (
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1">
            <Timer size={12} className="text-blue-400" /> Time of Day Windows (UTC)
          </p>
          {/* Ranked by performance, not by clock order. The old filter kept the
              first four chronologically and pinned two period names in even when
              empty, so the window the report recommends need not have appeared
              in the table at all. */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {timing.time_slots
              .filter((s) => s.video_count > 0)
              .sort((a, b) => b.multiplier - a.multiplier)
              .map((slot) => {
                const isBest = bestWindow?.best_slot_key === slot.slot;
                return (
                  <div
                    key={slot.slot}
                    className={`rounded-xl p-2.5 flex flex-col justify-between border transition-colors ${
                      isBest
                        ? "bg-amber-500/[0.08] border-amber-500/40"
                        : "bg-[#0f172a] border-white/10 hover:border-blue-500/30"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between text-[11px] mb-1 gap-1">
                        <span
                          className={`font-semibold truncate ${
                            isBest ? "text-amber-300" : "text-slate-300"
                          }`}
                        >
                          {slot.period}
                        </span>
                        {isBest ? (
                          <span className="bg-amber-500/20 text-amber-300 text-[9px] font-bold px-1 rounded flex items-center gap-0.5 flex-shrink-0">
                            <Star size={9} className="fill-amber-300" /> Best
                          </span>
                        ) : (
                          <span className="text-[10px] text-slate-500 flex-shrink-0">
                            {slot.slot}
                          </span>
                        )}
                      </div>
                      <p className="text-xs font-bold text-white tabular-nums">
                        {fmtNum(slot.avg_views)} avg
                      </p>
                      <p className="text-[10px] text-slate-500">
                        n={slot.video_count} · {slot.multiplier}× median
                      </p>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Top Videos Proof Timeline */}
      {evidence.length > 0 && (
        <div>
          {/* Labelled, not asserted. These are the top videos by views; whether
              each one actually backs the recommended window is stated per card
              rather than implied by the heading. */}
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1">
            <Flame size={12} className="text-orange-400" /> Top Performing Videos & When They Went
            Out
          </p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {evidence.map((v) => (
              <div
                key={v.video_id}
                className={`rounded-xl bg-[#0f172a] p-3 flex items-start gap-3 border transition-colors ${
                  v.in_best_window
                    ? "border-amber-500/40"
                    : "border-white/10 hover:border-amber-500/30"
                }`}
              >
                <div className="relative w-16 h-10 rounded bg-black/40 overflow-hidden flex-shrink-0 border border-white/5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`https://i.ytimg.com/vi/${v.video_id}/hqdefault.jpg`}
                    alt={v.title}
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-medium text-white truncate" title={v.title}>
                    {v.title}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mt-1 gap-2">
                    <span
                      className={`font-semibold ${
                        v.in_best_window ? "text-amber-300" : "text-slate-400"
                      }`}
                    >
                      {v.day_short} {v.time_utc !== "—" ? `· ${v.time_utc}` : ""}
                    </span>
                    <span className="tabular-nums font-semibold text-slate-200">
                      {fmtNum(v.views)} views
                    </span>
                  </div>
                  <p
                    className={`text-[10px] mt-0.5 ${
                      v.in_best_window ? "text-amber-200/70" : "text-slate-500"
                    }`}
                  >
                    {v.in_best_window ? "In the recommended window" : "Outside the recommended window"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AuditPanel({
  channel,
  metrics,
  audit,
  headline,
  similarChannels,
}: {
  channel: ProspectChannel;
  metrics: ProspectMetrics;
  audit: Strategy;
  headline: ProspectHeadline | null;
  similarChannels?: SimilarChannel[];
}) {
  const [filter, setFilter] = useState<"all" | "long" | "shorts">("all");

  const hasLongForm = (metrics.long_form_count ?? 0) > 0;
  const hasShorts = (metrics.shorts_count ?? 0) > 0;

  const currentAvgViews =
    filter === "long"
      ? metrics.long_form_avg_views
      : filter === "shorts"
      ? metrics.shorts_avg_views
      : metrics.avg_views;

  const currentMedianViews =
    filter === "long"
      ? metrics.long_form_median_views
      : filter === "shorts"
      ? metrics.shorts_median_views
      : metrics.median_views;

  const currentVideoCount =
    filter === "long"
      ? metrics.long_form_count
      : filter === "shorts"
      ? metrics.shorts_count
      : metrics.video_count_analyzed;

  const avgDuration =
    filter === "long"
      ? fmtDuration(metrics.avg_long_form_length_seconds)
      : filter === "shorts"
      ? "< 60s"
      : fmtDuration(metrics.avg_video_length_seconds || metrics.avg_long_form_length_seconds);
  const breakoutVideos = metrics.breakout_videos || [];
  const totalUploads = metrics.video_count_analyzed || channel.video_count;

  return (
    <section className="share-card rounded-2xl border border-white/10 bg-[#0b1120] overflow-hidden">
      {/* ── Channel Header ─────────────────────────────────────────────────── */}
      <header className="p-6 border-b border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-4">
          <ChannelAvatar url={channel.thumbnail_url} title={channel.title} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold tracking-[0.25em] uppercase text-red-400">
              Channel Audit
            </p>
            <h2 className="text-xl font-bold text-white truncate">{channel.title}</h2>
            <p className="text-xs text-slate-500 truncate mt-0.5">
              {channel.handle || channel.channel_id}
              {channel.subscriber_count
                ? ` · ${fmtCompact(channel.subscriber_count)} subscribers`
                : ""}
              {totalUploads ? ` · ${fmtCompact(totalUploads)} total uploads` : ""}
            </p>
          </div>
        </div>

        {/* vidIQ Quick Channel Vitals Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-[#080d1a] border border-white/5 p-2.5 rounded-xl">
          <div className="px-2 py-1">
            <p className="text-[9px] uppercase font-bold text-slate-500 flex items-center gap-1">
              <Clock size={10} className="text-blue-400" /> Avg Length
            </p>
            <p className="text-xs font-bold text-slate-200 mt-0.5">{avgDuration}</p>
          </div>
          <div className="px-2 py-1">
            <p className="text-[9px] uppercase font-bold text-slate-500 flex items-center gap-1">
              <Calendar size={10} className="text-purple-400" /> Cadence
            </p>
            <p className="text-xs font-bold text-slate-200 mt-0.5 truncate" title={metrics.upload_frequency}>
              {metrics.upload_frequency || "—"}
            </p>
          </div>
          <div className="px-2 py-1">
            <p className="text-[9px] uppercase font-bold text-slate-500 flex items-center gap-1">
              <DollarSign size={10} className="text-emerald-400" /> Est. Monthly
            </p>
            <p className="text-xs font-bold text-emerald-300 mt-0.5">
              {metrics.est_monthly_earnings || "—"}
            </p>
          </div>
          <div className="px-2 py-1">
            <p className="text-[9px] uppercase font-bold text-slate-500 flex items-center gap-1">
              <Zap size={10} className="text-amber-400" /> Velocity
            </p>
            <p className="text-xs font-bold text-slate-200 mt-0.5">
              {fmtCompact(metrics.est_monthly_views || metrics.views_last_30d)}/mo
            </p>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {/* ── Format Filters & Key Metrics ─────────────────────────────────── */}
        <div>
          <div className="flex items-center justify-between gap-3 mb-3">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Core Performance
            </p>
            {(hasLongForm || hasShorts) && (
              <div className="flex items-center gap-1 bg-[#0f172a] p-0.5 rounded-lg border border-white/5 text-xs">
                <button
                  onClick={() => setFilter("all")}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                    filter === "all"
                      ? "bg-slate-700 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  All ({metrics.video_count_analyzed})
                </button>
                {hasLongForm && (
                  <button
                    onClick={() => setFilter("long")}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                      filter === "long"
                        ? "bg-blue-600/30 text-blue-200 border border-blue-400/30 shadow-sm"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Long-Form ({metrics.long_form_count})
                  </button>
                )}
                {hasShorts && (
                  <button
                    onClick={() => setFilter("shorts")}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                      filter === "shorts"
                        ? "bg-pink-600/30 text-pink-200 border border-pink-400/30 shadow-sm"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Shorts ({metrics.shorts_count})
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat
              label={filter === "long" ? "Long-Form Avg Views" : filter === "shorts" ? "Shorts Avg Views" : "Avg Views"}
              value={fmtNum(currentAvgViews)}
              hint={`across ${currentVideoCount} ${filter === "long" ? "long-form videos" : filter === "shorts" ? "shorts" : "videos"}`}
            />
            <Stat
              label={filter === "long" ? "Long-Form Median" : filter === "shorts" ? "Shorts Median" : "Median Views"}
              value={fmtNum(currentMedianViews)}
            />
            <Stat
              label="Engagement"
              value={metrics.engagement_rate != null ? `${metrics.engagement_rate}%` : "n/a"}
              hint="likes + comments / views"
            />
            <Stat
              label="Last 30 Days"
              value={`${metrics.uploads_last_30 ?? 0} uploads`}
              hint={
                metrics.days_since_upload != null
                  ? `${metrics.days_since_upload}d since last upload`
                  : undefined
              }
            />
          </div>
        </div>

        {/* ── Key Highlight Banner ─────────────────────────────────────────── */}
        {headline ? (
          <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3 flex gap-3">
            <TrendingUp size={18} className="text-emerald-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-emerald-100 leading-relaxed">
              {headline.kind === "cadence" ? (
                <>
                  <strong>{headline.value} days</strong> since the last upload, after{" "}
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
                  <strong>{fmtNum(headline.value)}</strong> views — {headline.multiple}× this
                  channel&apos;s {fmtNum(headline.baseline)} {headline.baseline_kind ?? "median"}
                  <span className="text-emerald-300/60"> (n={headline.sample})</span>.
                  {headline.avg_value != null && headline.channel_avg_views ? (
                    <span className="text-emerald-300/60">
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

        {/* ── Timeframe Performance (7 Days, 28 Days, 1 Year) ──────────────── */}
        {metrics.timeframe_analytics && (
          <div>
            <div className="flex items-center justify-between gap-2 mb-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <BarChart3 size={14} className="text-blue-400" /> Timeframe Analytics (7D · 28D · 1 Year)
              </p>
              <span className="text-[11px] text-slate-500">
                Channel view volume & velocity across library
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {/* 7 Days Card */}
              <div className="rounded-xl bg-[#0f172a] border border-white/10 p-4 flex flex-col justify-between hover:border-blue-500/30 transition-colors">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400 flex items-center gap-1">
                      <Zap size={11} /> Views Gained (7d)
                    </span>
                    <span className="text-[9px] bg-blue-500/10 text-blue-300 px-1.5 py-0.5 rounded font-semibold">
                      Weekly
                    </span>
                  </div>
                  <p className="text-xl font-bold text-white tabular-nums">
                    +{fmtNum(metrics.timeframe_analytics.last_7d.views)} views
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {metrics.timeframe_analytics.last_7d.uploads} new upload
                    {metrics.timeframe_analytics.last_7d.uploads === 1 ? "" : "s"}{" "}
                    <span className="text-slate-500">
                      ({metrics.timeframe_analytics.last_7d.long_form_count} long · {metrics.timeframe_analytics.last_7d.shorts_count} shorts)
                    </span>
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs">
                  <span className="text-slate-500">Est. Revenue</span>
                  <span className="font-semibold text-emerald-400 tabular-nums">
                    {metrics.timeframe_analytics.last_7d.est_earnings || "—"}
                  </span>
                </div>
              </div>

              {/* 28 Days Card */}
              <div className="rounded-xl bg-[#0f172a] border border-white/10 p-4 flex flex-col justify-between hover:border-purple-500/30 transition-colors">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1">
                      <CalendarDays size={11} /> Views Gained (28d)
                    </span>
                    <span className="text-[9px] bg-purple-500/10 text-purple-300 px-1.5 py-0.5 rounded font-semibold">
                      Monthly
                    </span>
                  </div>
                  <p className="text-xl font-bold text-white tabular-nums">
                    +{fmtNum(metrics.timeframe_analytics.last_28d.views)} views
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {metrics.timeframe_analytics.last_28d.uploads} new uploads{" "}
                    <span className="text-slate-500">
                      ({metrics.timeframe_analytics.last_28d.long_form_count} long · {metrics.timeframe_analytics.last_28d.shorts_count} shorts)
                    </span>
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs">
                  <span className="text-slate-500">Est. Revenue</span>
                  <span className="font-semibold text-emerald-400 tabular-nums">
                    {metrics.timeframe_analytics.last_28d.est_earnings || "—"}
                  </span>
                </div>
              </div>

              {/* 1 Year Card */}
              <div className="rounded-xl bg-[#0f172a] border border-white/10 p-4 flex flex-col justify-between hover:border-emerald-500/30 transition-colors">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                      <Activity size={11} /> Views Gained (1y)
                    </span>
                    <span className="text-[9px] bg-emerald-500/10 text-emerald-300 px-1.5 py-0.5 rounded font-semibold">
                      Annual (365d)
                    </span>
                  </div>
                  <p className="text-xl font-bold text-white tabular-nums">
                    +{fmtNum(metrics.timeframe_analytics.last_1y.views)} views
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {metrics.timeframe_analytics.last_1y.uploads} uploads{" "}
                    <span className="text-slate-500">
                      (~{metrics.timeframe_analytics.last_1y.uploads_per_month || 0}/mo pace)
                    </span>
                  </p>
                </div>
                <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs">
                  <span className="text-slate-500">Est. Annual Rev</span>
                  <span className="font-semibold text-emerald-400 tabular-nums">
                    {metrics.timeframe_analytics.last_1y.est_earnings || "—"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}



        {/* ── Top Breakout Outlier Videos (vidIQ Feature) ───────────────────── */}
        {breakoutVideos.length > 0 && (
          <div>
            <div className="flex items-center justify-between gap-2 mb-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Flame size={14} className="text-orange-400" /> Top Breakout Videos
              </p>
              <span className="text-[11px] text-slate-500">
                Videos with extraordinary outlier demand vs channel average
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {breakoutVideos.slice(0, 3).map((v) => (
                <div
                  key={v.video_id}
                  className="rounded-xl bg-[#0f172a] border border-white/10 p-3 flex flex-col gap-2 relative overflow-hidden group hover:border-orange-500/30 transition-colors"
                >
                  <div className="relative aspect-video rounded-lg overflow-hidden bg-black/40 border border-white/5">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`https://i.ytimg.com/vi/${v.video_id}/hqdefault.jpg`}
                      alt={v.title}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                    <div className="absolute top-2 right-2 bg-orange-600/90 text-white font-bold text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1 shadow">
                      <Flame size={10} /> {v.multiplier}× Breakout
                    </div>
                    {v.duration_seconds > 0 && (
                      <div className="absolute bottom-2 right-2 bg-black/80 text-slate-300 text-[10px] px-1.5 py-0.5 rounded tabular-nums">
                        {fmtDuration(v.duration_seconds)}
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-white line-clamp-2 leading-snug" title={v.title}>
                      {v.title}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 mt-2">
                      <span className="font-semibold text-orange-300 tabular-nums">
                        {fmtNum(v.views)} views
                      </span>
                      <span>{v.published_at}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Topic & Keyword Performance (vidIQ Feature) ──────────────────── */}
        {metrics.keyword_analysis &&
          ((metrics.keyword_analysis.top_keywords && metrics.keyword_analysis.top_keywords.length > 0) ||
            (metrics.keyword_analysis.underperforming_keywords &&
              metrics.keyword_analysis.underperforming_keywords.length > 0)) && (
            <div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Target size={14} className="text-emerald-400" /> Topic & Keyword Performance
                </p>
                {metrics.keyword_analysis.avg_seo_score != null && (
                  <span className="text-[11px] text-slate-400 flex items-center gap-1">
                    <Sparkles size={11} className="text-amber-400" /> Title SEO Appeal:{" "}
                    <strong className="text-amber-300 font-semibold">
                      {metrics.keyword_analysis.avg_seo_score}/100
                    </strong>
                  </span>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {metrics.keyword_analysis.top_keywords?.map((k) => (
                  <div
                    key={k.keyword}
                    className="rounded-xl bg-[#0f172a] border border-white/10 p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-colors"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-xs font-bold text-white flex items-center gap-1 truncate">
                          <Tag size={11} className="text-emerald-400 flex-shrink-0" /> {k.keyword}
                        </span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 flex-shrink-0">
                          {k.multiplier}× baseline
                        </span>
                      </div>
                      <div className="flex items-baseline justify-between text-[11px] text-slate-400">
                        <span>{k.video_count} videos</span>
                        <span className="font-semibold text-slate-200 tabular-nums">
                          {fmtNum(k.avg_views)} avg views
                        </span>
                      </div>
                    </div>
                    {k.top_video_title ? (
                      <div
                        className="mt-2.5 pt-2 border-t border-white/5 text-[10px] text-slate-500 truncate"
                        title={k.top_video_title}
                      >
                        Top: <span className="text-slate-400">{k.top_video_title}</span>
                      </div>
                    ) : null}
                  </div>
                ))}

                {metrics.keyword_analysis.underperforming_keywords?.map((k) => (
                  <div
                    key={k.keyword}
                    className="rounded-xl bg-[#0f172a] border border-white/10 p-3 flex flex-col justify-between hover:border-red-500/20 transition-colors opacity-80"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-xs font-medium text-slate-300 flex items-center gap-1 truncate">
                          <Tag size={11} className="text-red-400 flex-shrink-0" /> {k.keyword}
                        </span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20 flex-shrink-0">
                          {k.multiplier}× (Low)
                        </span>
                      </div>
                      <div className="flex items-baseline justify-between text-[11px] text-slate-400">
                        <span>{k.video_count} videos</span>
                        <span className="font-medium text-slate-400 tabular-nums">
                          {fmtNum(k.avg_views)} avg
                        </span>
                      </div>
                    </div>
                    {k.top_video_title ? (
                      <div
                        className="mt-2.5 pt-2 border-t border-white/5 text-[10px] text-slate-500 truncate"
                        title={k.top_video_title}
                      >
                        Sample: <span className="text-slate-500">{k.top_video_title}</span>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          )}

        {/* ── Similar Channels / Benchmark Peers (vidIQ Feature) ───────────── */}
        {similarChannels && similarChannels.length > 0 && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <Users size={14} className="text-purple-400" /> Similar Benchmark Channels
            </p>
            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
              {similarChannels.map((c) => (
                <div
                  key={c.channel_id}
                  className="rounded-xl bg-[#0f172a] border border-white/10 p-3 flex items-center gap-3 hover:border-purple-500/30 transition-colors"
                >
                  <ChannelAvatar url={c.thumbnail_url} title={c.title} size="md" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-white truncate">{c.title}</p>
                    <p className="text-[10px] text-slate-500 truncate">
                      {c.handle || "YouTube Creator"}
                      {c.subscriber_count ? ` · ${fmtCompact(c.subscriber_count)} subs` : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Upload Timing & Best Schedule (vidIQ-style Intelligence) ─────── */}
        <UploadTimingSection metrics={metrics} />

        {/* ── Length Performance ───────────────────────────────────────────── */}
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
            Performance by video length
          </p>
          <LengthBars metrics={metrics} />
        </div>

        {/* ── AI Strategy Analysis ─────────────────────────────────────────── */}
        <div className="grid md:grid-cols-2 gap-3">
          <Section
            icon={CheckCircle2}
            title="What's Working"
            tint="text-green-400"
            items={audit.whats_working}
            solid
          />
          <Section
            icon={AlertTriangle}
            title="Underperforming"
            tint="text-red-400"
            items={audit.underperforming}
            solid
          />
          <Section
            icon={Ruler}
            title="Format & Cadence"
            tint="text-blue-400"
            items={audit.format_insights}
            solid
          />
          <Section
            icon={Puzzle}
            title="Content Gaps"
            tint="text-amber-400"
            items={audit.content_gaps}
            solid
          />
        </div>

        <Section
          icon={ListOrdered}
          title="Do This Next"
          tint="text-purple-400"
          items={audit.priorities}
          ordered
          solid
        />

        <p className="text-[11px] text-slate-600 leading-relaxed border-t border-white/5 pt-4">
          Based on {metrics.video_count_analyzed} public videos. Click-through rate, watch time and
          audience retention are private to the channel owner and are not included.
        </p>
      </div>
    </section>
  );
}

