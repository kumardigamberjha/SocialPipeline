"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  Printer,
  Search,
  Sparkles,
  Telescope,
  Trash2,
  Users,
} from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import ProspectReportView from "@/components/prospects/ProspectReportView";
import {
  fmtCompact,
  fmtDate,
  formatModelName,
  prospectsApi,
  type ProspectChannel,
  type ProspectReport,
  type ProspectStatus,
  type ProspectSummary,
} from "@/lib/youtubeProspectsApi";

/**
 * Audit any creator's channel and plan their next 30 days.
 *
 * Two-step on purpose: the lookup is free and resolves the channel, then the
 * user confirms the right creator before the report spends two LLM calls.
 */

const STATUS_TINTS: Record<ProspectStatus, string> = {
  new: "bg-slate-500/10 text-slate-300 border-slate-500/20",
  contacted: "bg-blue-500/10 text-blue-300 border-blue-500/20",
  replied: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  archived: "bg-white/5 text-slate-500 border-white/10",
};

const STATUSES: ProspectStatus[] = ["new", "contacted", "replied", "archived"];

function SafeAvatar({
  url,
  title,
  size = "md",
}: {
  url?: string | null;
  title: string;
  size?: "sm" | "md" | "lg";
}) {
  const [err, setErr] = useState(false);
  const initial = title ? title.charAt(0).toUpperCase() : "C";
  const sizeClasses = {
    sm: "w-9 h-9 text-xs",
    md: "w-12 h-12 text-sm",
    lg: "w-14 h-14 text-base",
  }[size];

  if (!url || err) {
    return (
      <div
        className={`${sizeClasses} rounded-full bg-gradient-to-tr from-red-600/30 via-purple-600/20 to-blue-600/30 border border-white/10 flex items-center justify-center font-bold text-white flex-shrink-0 shadow-inner`}
      >
        {initial}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setErr(true)}
      className={`${sizeClasses} rounded-full border border-white/10 flex-shrink-0 object-cover`}
    />
  );
}

export default function ProspectsDashboard() {
  const [query, setQuery] = useState("");
  const [candidate, setCandidate] = useState<ProspectChannel | null>(null);
  const [report, setReport] = useState<ProspectReport | null>(null);
  const [saved, setSaved] = useState<ProspectSummary[]>([]);

  const [looking, setLooking] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSaved = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await prospectsApi.list();
      setSaved(data.items ?? []);
    } catch {
      // A failed list must not block a fresh lookup — the primary action here
      // is auditing a new channel, not reviewing old ones.
      setSaved([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadSaved();
  }, [loadSaved]);

  const runLookup = async () => {
    if (!query.trim() || looking) return;
    setLooking(true);
    setError(null);
    setCandidate(null);
    setReport(null);
    try {
      const data = await prospectsApi.lookup(query.trim());
      setCandidate(data.channel);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Channel lookup failed");
    } finally {
      setLooking(false);
    }
  };

  const runReport = async (channelId: string, refresh = false) => {
    setGenerating(true);
    setError(null);
    try {
      const data = await prospectsApi.generateReport(channelId, { weeks: 4, refresh });
      setReport(data);
      setCandidate(data.channel);
      loadSaved();
    } catch (e) {
      // Best-effort recovery: if backend saved the report despite client/proxy timeout, load it
      try {
        const savedData = await prospectsApi.get(channelId);
        if (savedData?.audit && savedData?.roadmap) {
          setReport(savedData);
          setCandidate(savedData.channel);
          loadSaved();
          return;
        }
      } catch {
        /* no saved report yet */
      }
      setError(e instanceof ApiError ? e.message : "Report generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const openSaved = async (channelId: string) => {
    setError(null);
    setReport(null);
    setGenerating(true);
    try {
      const data = await prospectsApi.get(channelId);
      setReport(data);
      setCandidate(data.channel);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load that report");
    } finally {
      setGenerating(false);
    }
  };

  const remove = async (channelId: string) => {
    try {
      await prospectsApi.remove(channelId);
      setSaved((prev) => prev.filter((p) => p.channel_id !== channelId));
      if (report?.channel.channel_id === channelId) setReport(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete that prospect");
    }
  };

  const setStatus = async (channelId: string, status: ProspectStatus) => {
    setSaved((prev) =>
      prev.map((p) => (p.channel_id === channelId ? { ...p, outreach_status: status } : p)),
    );
    try {
      await prospectsApi.setStatus(channelId, status);
    } catch {
      loadSaved(); // put the real value back
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
      <header>
        <p className="flex items-center gap-2 text-[11px] font-bold tracking-[0.25em] uppercase text-red-400">
          <Telescope size={13} /> Prospect Audits
        </p>
        <h1 className="text-2xl font-bold text-white mt-1">Audit any channel</h1>
        <p className="text-sm text-slate-500 mt-1 max-w-2xl">
          Paste a channel name, @handle or YouTube URL. Get a data-grounded audit, a 30-day content
          plan, and an outreach opener with the real numbers already filled in.
        </p>
      </header>

      {/* ── Lookup ────────────────────────────────────────────────────────── */}
      <div className="glass-card rounded-2xl border border-white/5 p-6">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 pointer-events-none"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runLookup()}
              placeholder="Komal Bhojani · @DigitoSpark · youtube.com/@digitospark"
              className="w-full pl-9 pr-3 py-2.5 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-red-500/40"
            />
          </div>
          <button
            onClick={runLookup}
            disabled={looking || !query.trim()}
            className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium bg-red-600/20 text-red-200 border border-red-500/30 hover:bg-red-600/30 transition-colors disabled:opacity-50"
          >
            {looking ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            Find channel
          </button>
        </div>

        {error ? (
          <div className="mt-4 rounded-lg border border-red-500/25 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
            {error}
          </div>
        ) : null}

        {candidate && !report ? (
          <div className="mt-5 rounded-xl bg-[#0f172a] border border-white/10 p-4 flex flex-col sm:flex-row sm:items-center gap-4">
            <SafeAvatar url={candidate.thumbnail_url} title={candidate.title} size="md" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-white truncate">{candidate.title}</p>
              <p className="text-xs text-slate-500 truncate">
                {candidate.handle || candidate.channel_id}
                {candidate.subscriber_count
                  ? ` · ${fmtCompact(candidate.subscriber_count)} subscribers`
                  : ""}
                {candidate.video_count ? ` · ${fmtCompact(candidate.video_count)} videos` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {saved.some((p) => p.channel_id === candidate.channel_id) ? (
                <button
                  onClick={() => openSaved(candidate.channel_id)}
                  disabled={generating}
                  className="flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium bg-white/10 text-white border border-white/15 hover:bg-white/15 transition-colors disabled:opacity-50"
                >
                  View saved audit
                </button>
              ) : null}
              <button
                onClick={() => runReport(candidate.channel_id, saved.some((p) => p.channel_id === candidate.channel_id))}
                disabled={generating}
                className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors disabled:opacity-50"
              >
                {generating ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <Sparkles size={15} />
                )}
                {generating
                  ? "Analysing…"
                  : saved.some((p) => p.channel_id === candidate.channel_id)
                  ? "Re-generate plan"
                  : "Generate audit & 30-day plan"}
              </button>
            </div>
          </div>
        ) : null}

        {generating && !report ? (
          <p className="mt-3 text-xs text-slate-500">
            Pulling public uploads and running both analyses — this usually takes 20–40 seconds.
          </p>
        ) : null}
      </div>

      {/* ── The report ────────────────────────────────────────────────────── */}
      {report ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setReport(null);
                  setCandidate(null);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.05] text-slate-300 border border-white/10 hover:bg-white/[0.1] hover:text-white transition-colors"
              >
                <ArrowLeft size={13} /> Back to saved prospects
              </button>
              <p className="text-xs text-slate-500">
                Generated {fmtDate(report.generated_at)}
                {report.model ? ` · ${formatModelName(report.model)}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {report.tier?.grade === "internal_only" ? (
                <button
                  onClick={async () => {
                    setGenerating(true);
                    setError(null);
                    try {
                      const updated = await prospectsApi.regenerateOnPrimary(report.channel.channel_id);
                      setReport(updated);
                      loadSaved();
                    } catch (e) {
                      setError(e instanceof ApiError ? e.message : "Failed to regenerate on primary");
                    } finally {
                      setGenerating(false);
                    }
                  }}
                  disabled={generating}
                  className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/20 text-amber-200 border border-amber-500/40 hover:bg-amber-500/30 transition-colors disabled:opacity-50"
                >
                  {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  Regenerate on Primary
                </button>
              ) : null}
              <button
                onClick={() => runReport(report.channel.channel_id, true)}
                disabled={generating}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] text-slate-300 border border-white/10 hover:bg-white/[0.06] transition-colors disabled:opacity-50"
              >
                {generating ? <Loader2 size={13} className="animate-spin" /> : null}
                Regenerate
              </button>
              <Link
                href={`/report/print/${report.channel.channel_id}`}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  report.tier?.grade === "internal_only"
                    ? "bg-white/[0.03] text-slate-500 border border-white/10 opacity-60"
                    : "bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30"
                }`}
                title={report.tier?.grade === "internal_only" ? "Regenerate on primary model to enable client PDF export" : "Print-Ready Report"}
              >
                <Printer size={13} /> Print-Ready Report
              </Link>
              <Link
                href={`/prospect-report/${report.channel.channel_id}`}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  report.tier?.grade === "internal_only"
                    ? "bg-white/[0.03] text-slate-500 border border-white/10 opacity-60"
                    : "bg-blue-600/20 text-blue-200 border border-blue-500/30 hover:bg-blue-600/30"
                }`}
                title={report.tier?.grade === "internal_only" ? "Regenerate on primary model to enable client sharing" : "Shareable View"}
              >
                <ExternalLink size={13} /> Shareable View
              </Link>
            </div>
          </div>
          <ProspectReportView report={report} />
        </div>
      ) : null}

      {/* ── Saved prospects (only visible when not viewing an active report) ── */}
      {!report && (
        <section>
          <p className="flex items-center gap-2 text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400 mb-3">
            <Users size={13} /> Saved prospects
          </p>

          {loadingList ? (
            <div className="flex justify-center py-12">
              <Loader2 className="animate-spin text-slate-600" size={22} />
            </div>
          ) : saved.length === 0 ? (
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] py-12 text-center">
              <Telescope size={28} className="mx-auto text-slate-700" />
              <p className="text-sm text-slate-400 mt-3">No prospects audited yet</p>
              <p className="text-xs text-slate-600 mt-1">
                Look up a channel above to create your first audit.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {saved.map((p) => (
                <div
                  key={p.channel_id}
                  className="rounded-xl border border-white/5 bg-white/[0.02] p-4 flex flex-col gap-3"
                >
                  <div className="flex items-start gap-3">
                    <SafeAvatar url={p.thumbnail_url} title={p.title} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white truncate">{p.title}</p>
                      <p className="text-[11px] text-slate-500 truncate">
                        {p.handle || p.channel_id}
                        {p.subscriber_count ? ` · ${fmtCompact(p.subscriber_count)} subs` : ""}
                      </p>
                    </div>
                    <button
                      onClick={() => remove(p.channel_id)}
                      title="Delete prospect"
                      className="text-slate-600 hover:text-red-400 transition-colors flex-shrink-0"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {p.outreach_line ? (
                    <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                      {p.outreach_line}
                    </p>
                  ) : null}

                  <div className="flex items-center justify-between gap-2 mt-auto">
                    <select
                      value={p.outreach_status}
                      onChange={(e) => setStatus(p.channel_id, e.target.value as ProspectStatus)}
                      className={`text-[10px] font-medium px-2 py-1 rounded-full border bg-transparent focus:outline-none ${
                        STATUS_TINTS[p.outreach_status]
                      }`}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s} className="bg-[#0b1120] text-slate-200">
                          {s}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => openSaved(p.channel_id)}
                      className="text-[11px] font-medium text-blue-300 hover:text-blue-200 transition-colors"
                    >
                      Open report →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
