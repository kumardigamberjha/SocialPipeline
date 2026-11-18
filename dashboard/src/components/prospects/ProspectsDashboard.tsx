"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ExternalLink,
  Film,
  Instagram,
  Loader2,
  Printer,
  Scissors,
  Search,
  Sparkles,
  Telescope,
  Trash2,
  Users,
  Video,
  Youtube,
  Zap,
} from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import ProspectReportView from "@/components/prospects/ProspectReportView";
import ShortFormAuditPanel from "@/components/prospects/ShortFormAuditPanel";
import {
  shortformApi,
  type ShortFormAuditReport,
  type ShortFormLookupResponse,
  type ShortFormPlatform,
} from "@/lib/shortformProspectsApi";
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
  const [auditMode, setAuditMode] = useState<"shortform_reels" | "youtube_channel">("shortform_reels");

  // YouTube Channel Audit State
  const [query, setQuery] = useState("");
  const [candidate, setCandidate] = useState<ProspectChannel | null>(null);
  const [report, setReport] = useState<ProspectReport | null>(null);
  const [saved, setSaved] = useState<ProspectSummary[]>([]);
  const [looking, setLooking] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Short-Form & Reels Audit State
  const [sfPlatform, setSfPlatform] = useState<ShortFormPlatform>("youtube");
  const [sfQuery, setSfQuery] = useState("");
  const [sfCandidate, setSfCandidate] = useState<ShortFormLookupResponse | null>(null);
  const [sfReport, setSfReport] = useState<ShortFormAuditReport | null>(null);
  const [sfSaved, setSfSaved] = useState<ShortFormAuditReport[]>([]);
  const [sfLooking, setSfLooking] = useState(false);
  const [sfGenerating, setSfGenerating] = useState(false);
  const [sfLoadingList, setSfLoadingList] = useState(true);
  const [sfError, setSfError] = useState<string | null>(null);

  const loadSaved = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await prospectsApi.list();
      setSaved(data.items ?? []);
    } catch {
      setSaved([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadSfSaved = useCallback(async () => {
    setSfLoadingList(true);
    try {
      const data = await shortformApi.list();
      setSfSaved(data.items ?? []);
    } catch {
      setSfSaved([]);
    } finally {
      setSfLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadSaved();
    loadSfSaved();
  }, [loadSaved, loadSfSaved]);

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

  const runSfLookup = async () => {
    if (!sfQuery.trim() || sfLooking) return;
    setSfLooking(true);
    setSfError(null);
    setSfCandidate(null);
    setSfReport(null);
    try {
      const data = await shortformApi.lookup(sfPlatform, sfQuery.trim());
      setSfCandidate(data);
    } catch (e) {
      setSfError(e instanceof ApiError ? e.message : "Creator lookup failed");
    } finally {
      setSfLooking(false);
    }
  };

  const runSfGenerate = async () => {
    if (!sfCandidate || sfGenerating) return;
    setSfGenerating(true);
    setSfError(null);
    try {
      const rep = await shortformApi.generate(sfCandidate.profile.platform, sfCandidate.profile.identifier);
      setSfReport(rep);
      loadSfSaved();
    } catch (e) {
      setSfError(e instanceof ApiError ? e.message : "Short-form audit generation failed");
    } finally {
      setSfGenerating(false);
    }
  };

  const openSavedSf = async (reportId: string) => {
    setSfGenerating(true);
    setSfError(null);
    try {
      const rep = await shortformApi.getReport(reportId);
      setSfReport(rep);
    } catch (e) {
      setSfError(e instanceof ApiError ? e.message : "Could not load that audit");
    } finally {
      setSfGenerating(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
      {/* ── Mode Switcher ── */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => {
              setAuditMode("shortform_reels");
              setError(null);
              setSfError(null);
            }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-xs md:text-sm transition-all cursor-pointer ${
              auditMode === "shortform_reels"
                ? "bg-gradient-to-r from-purple-600 via-pink-600 to-indigo-600 text-white shadow-lg shadow-purple-600/30 border border-purple-400/40"
                : "bg-white/[0.04] text-slate-400 hover:text-white border border-white/5"
            }`}
          >
            <Scissors size={15} /> Short-Form & Reels Audit
            <span className="text-[9px] uppercase font-black px-1.5 py-0.2 rounded bg-amber-400 text-slate-950">
              NEW
            </span>
          </button>

          <button
            onClick={() => {
              setAuditMode("youtube_channel");
              setError(null);
              setSfError(null);
            }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold text-xs md:text-sm transition-all cursor-pointer ${
              auditMode === "youtube_channel"
                ? "bg-red-600/30 border border-red-500/40 text-red-200 shadow-lg"
                : "bg-white/[0.04] text-slate-400 hover:text-white border border-white/5"
            }`}
          >
            <Youtube size={15} className="text-red-400" /> YouTube Channel Audit
          </button>
        </div>

        <p className="text-xs text-slate-500 hidden sm:block">
          {auditMode === "shortform_reels"
            ? "Viral Hook Teardowns & 30-Day Sprint Roadmaps"
            : "Channel Vitals & Publishing Roadmaps"}
        </p>
      </div>

      {/* ── HEADER ── */}
      <header>
        <p className="flex items-center gap-2 text-[11px] font-bold tracking-[0.25em] uppercase text-purple-400">
          {auditMode === "shortform_reels" ? (
            <>
              <Film size={13} /> Short-Form Repurposing & Virality Engine
            </>
          ) : (
            <>
              <Telescope size={13} className="text-red-400" /> YouTube Channel Audits
            </>
          )}
        </p>
        <h1 className="text-2xl font-bold text-white mt-1">
          {auditMode === "shortform_reels"
            ? "Audit Short-Form & Viral Reels Potential"
            : "Audit any YouTube channel"}
        </h1>
        <p className="text-sm text-slate-500 mt-1 max-w-2xl">
          {auditMode === "shortform_reels"
            ? "Audit any YouTube channel or Instagram creator. Uncover high-retention viral moments from long-form videos, diagnose 3-second hook leaks, and generate an institutional 30-day Short-Form sprint deliverable."
            : "Paste a channel name, @handle or YouTube URL. Get a data-grounded audit, a 30-day content plan, and an outreach opener with the real numbers already filled in."}
        </p>
      </header>

      {/* ── SECTION: Short-Form & Reels Mode ── */}
      {auditMode === "shortform_reels" && (
        <div className="space-y-6">
          {/* Active Short-Form Report View */}
          {sfReport ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <button
                  onClick={() => {
                    setSfReport(null);
                    setSfCandidate(null);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.05] text-slate-300 border border-white/10 hover:bg-white/[0.1] hover:text-white transition-colors cursor-pointer"
                >
                  <ArrowLeft size={13} /> Back to Search & Saved Audits
                </button>
              </div>

              <ShortFormAuditPanel report={sfReport} />
            </div>
          ) : (
            <>
              {/* Lookup Card */}
              <div className="glass-card rounded-2xl border border-white/10 bg-[#0f172a]/80 p-6 space-y-4">
                {/* Platform selector */}
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-400 mr-1">Platform:</span>
                  <button
                    onClick={() => {
                      setSfPlatform("youtube");
                      setSfCandidate(null);
                    }}
                    className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 border transition-all cursor-pointer ${
                      sfPlatform === "youtube"
                        ? "bg-red-500/20 text-red-200 border-red-500/40"
                        : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
                    }`}
                  >
                    <Youtube size={13} className="text-red-400" /> YouTube (Long-to-Shorts Repurposing)
                  </button>
                  <button
                    onClick={() => {
                      setSfPlatform("instagram");
                      setSfCandidate(null);
                    }}
                    className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 border transition-all cursor-pointer ${
                      sfPlatform === "instagram"
                        ? "bg-pink-500/20 text-pink-200 border-pink-500/40"
                        : "bg-white/5 text-slate-400 border-white/5 hover:text-white"
                    }`}
                  >
                    <Instagram size={13} className="text-pink-400" /> Instagram (@handle / Reels)
                  </button>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <div className="relative flex-1">
                    <Search
                      size={15}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 pointer-events-none"
                    />
                    <input
                      value={sfQuery}
                      onChange={(e) => setSfQuery(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && runSfLookup()}
                      placeholder={
                        sfPlatform === "youtube"
                          ? "Fireship · @fireship · youtube.com/@fireship"
                          : "@codingindiaai · instagram.com/codingindiaai"
                      }
                      className="w-full pl-9 pr-3 py-2.5 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-purple-500/40"
                    />
                  </div>
                  <button
                    onClick={runSfLookup}
                    disabled={sfLooking || !sfQuery.trim()}
                    className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold bg-purple-600/30 text-purple-200 border border-purple-500/40 hover:bg-purple-600/40 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {sfLooking ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
                    Audit Creator
                  </button>
                </div>

                {sfError && (
                  <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
                    {sfError}
                  </div>
                )}

                {/* Candidate Resolution Preview */}
                {sfCandidate && !sfReport && (
                  <div className="mt-4 rounded-xl bg-[#0b101e] border border-purple-500/30 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      {sfCandidate.profile.avatar_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={sfCandidate.profile.avatar_url}
                          alt=""
                          className="w-12 h-12 rounded-xl object-cover border border-white/10"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-xl bg-purple-600/20 text-purple-300 font-bold flex items-center justify-center border border-purple-500/30">
                          {sfCandidate.profile.title.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <p className="text-sm font-bold text-white flex items-center gap-2">
                          {sfCandidate.profile.title}
                          <span className="text-xs font-normal text-slate-400">
                            {sfCandidate.profile.handle}
                          </span>
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                            Live Profile
                          </span>
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {sfCandidate.profile.followers_or_subs.toLocaleString()} followers/subs · {sfCandidate.sample_videos_count} catalog videos found
                        </p>
                        {sfCandidate.profile.bio && (
                          <p className="text-xs text-slate-300/90 italic mt-1 max-w-md line-clamp-2">
                            &ldquo;{sfCandidate.profile.bio}&rdquo;
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                      <div className="text-left sm:text-right">
                        <p className="text-[10px] uppercase font-bold text-purple-400">Opportunity Score</p>
                        <p className="text-base font-black text-amber-300">
                          {sfCandidate.gap_metrics.shortform_opportunity_score} / 100
                        </p>
                        <p className="text-[10px] text-slate-400 max-w-[200px] truncate sm:text-right">
                          {sfCandidate.gap_metrics.opportunity_verdict}
                        </p>
                      </div>

                      <button
                        onClick={runSfGenerate}
                        disabled={sfGenerating}
                        className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30 transition-all cursor-pointer disabled:opacity-50"
                      >
                        {sfGenerating ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Sparkles size={14} />
                        )}
                        {sfGenerating ? "Extracting Viral Cuts…" : "Generate Short-Form & Reels Audit"}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Saved Short-Form Audits List */}
              <section className="space-y-3">
                <p className="flex items-center gap-2 text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
                  <Film size={13} /> Saved Short-Form & Reels Audits
                </p>

                {sfLoadingList ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="animate-spin text-slate-600" size={20} />
                  </div>
                ) : sfSaved.length === 0 ? (
                  <div className="rounded-2xl border border-white/5 bg-white/[0.02] py-8 text-center">
                    <Film size={24} className="mx-auto text-slate-700" />
                    <p className="text-xs text-slate-400 mt-2">No Short-Form audits generated yet</p>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      Audit a creator above to extract your first 5 viral Reel blueprints.
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {sfSaved.map((r) => (
                      <div
                        key={r.report_id}
                        className="rounded-xl border border-white/5 bg-white/[0.02] p-4 flex flex-col justify-between gap-3 hover:border-purple-500/30 transition-all"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-white flex items-center gap-1.5">
                            {r.profile.platform === "instagram" ? (
                              <Instagram size={14} className="text-pink-400" />
                            ) : (
                              <Youtube size={14} className="text-red-400" />
                            )}
                            {r.profile.title}
                          </span>
                          <span className="text-[10px] font-bold text-amber-300 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20">
                            {r.gap_metrics.shortform_opportunity_score}/100
                          </span>
                        </div>

                        <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                          {r.executive_summary}
                        </p>

                        <div className="flex items-center justify-between pt-2 border-t border-white/5 text-[10px]">
                          <span className="text-slate-500">{new Date(r.generated_at).toLocaleDateString()}</span>
                          <button
                            onClick={() => openSavedSf(r.report_id)}
                            className="text-purple-300 hover:text-purple-200 font-bold transition-colors cursor-pointer"
                          >
                            Open Short-Form Report →
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      )}

      {/* ── SECTION: YouTube Long-Form Channel Mode ── */}
      {auditMode === "youtube_channel" && (
        <div className="space-y-6">

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
      )}
    </div>
  );
}
