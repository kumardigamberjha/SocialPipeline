"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  Calendar,
  Check,
  Clock,
  Copy,
  ExternalLink,
  Film,
  Flame,
  Instagram,
  Layers,
  Mail,
  MessageSquare,
  Printer,
  Scissors,
  Share2,
  Sparkles,
  Target,
  TrendingUp,
  Video,
  Youtube,
  Zap,
} from "lucide-react";
import {
  ShortFormAuditReport,
  ReelConversionBlueprint,
  HookTeardown,
  ShortFormSprintDay,
} from "@/lib/shortformProspectsApi";

export default function ShortFormAuditPanel({
  report,
  onPrint,
}: {
  report: ShortFormAuditReport;
  onPrint?: () => void;
}) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"blueprints" | "hooks" | "sprint" | "outreach">("blueprints");
  const [selectedWeek, setSelectedWeek] = useState<number>(1);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const { profile, gap_metrics, blueprints, hook_teardowns, sprint_calendar, outreach_copy } = report;

  // Filter sprint by selected week
  const weekDays = sprint_calendar.filter((d) => d.week_number === selectedWeek);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* ── Top Header Banner ── */}
      <div className="rounded-2xl border border-white/10 bg-gradient-to-r from-slate-900/90 via-[#0e1628]/80 to-purple-950/40 p-5 md:p-6 backdrop-blur-xl shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div className="flex items-center gap-4">
            <div className="relative">
              {profile.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profile.avatar_url}
                  alt={profile.title}
                  className="w-16 h-16 rounded-2xl object-cover border-2 border-purple-500/30 shadow-lg"
                />
              ) : (
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-purple-600 via-pink-600 to-amber-500 flex items-center justify-center font-black text-2xl text-white shadow-lg">
                  {profile.title.charAt(0).toUpperCase()}
                </div>
              )}
              <span className="absolute -bottom-1 -right-1 bg-black/80 p-1 rounded-lg border border-white/10">
                {profile.platform === "instagram" ? (
                  <Instagram size={14} className="text-pink-400" />
                ) : (
                  <Youtube size={14} className="text-red-400" />
                )}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl md:text-2xl font-black text-white tracking-tight">
                  {profile.title}
                </h1>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  {profile.handle}
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wide flex items-center gap-1">
                  <Zap size={10} /> Short-Form Audit Ready
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {profile.followers_or_subs.toLocaleString()} followers/subscribers · {profile.total_videos_or_posts} catalog items
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/shortform-report/print/${report.report_id}`}
              target="_blank"
              className="px-3.5 py-2 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/40 text-purple-200 text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm"
            >
              <Printer size={14} /> Print Client PDF
            </Link>
            {profile.profile_url && (
              <a
                href={profile.profile_url}
                target="_blank"
                rel="noreferrer"
                className="p-2 rounded-xl bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-white border border-white/10 transition-all"
                title="View Creator Profile"
              >
                <ExternalLink size={15} />
              </a>
            )}
          </div>
        </div>
      </div>

      {/* ── Short-Form Gap & Opportunity Hero Card ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Opportunity Score Box */}
        <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/[0.12] via-[#121929] to-[#0c1220] p-5 flex flex-col justify-between shadow-xl">
          <div>
            <span className="text-[10px] font-bold tracking-wider uppercase text-amber-400 flex items-center gap-1 mb-2">
              <Target size={12} /> Short-Form Opportunity Score
            </span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl md:text-5xl font-black text-white tabular-nums tracking-tight">
                {gap_metrics.shortform_opportunity_score}
              </span>
              <span className="text-slate-400 font-bold text-sm">/ 100</span>
            </div>
            <p className="text-xs font-semibold text-amber-300/90 mt-2">
              {gap_metrics.opportunity_verdict}
            </p>
          </div>

          <div className="mt-4 pt-3 border-t border-white/10">
            <div className="flex justify-between text-[11px] text-slate-400 mb-1">
              <span>Shorts Ratio ({gap_metrics.shorts_ratio_pct}%)</span>
              <span className="font-semibold text-slate-200">{gap_metrics.shorts_count} Shorts / {gap_metrics.longform_count} Long</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-amber-400 to-purple-500 h-2 rounded-full"
                style={{ width: `${Math.min(100, Math.max(8, gap_metrics.shorts_ratio_pct))}%` }}
              />
            </div>
          </div>
        </div>

        {/* Missed Reach & Arbitrage Multiplier */}
        <div className="rounded-2xl border border-purple-500/30 bg-gradient-to-br from-purple-500/[0.10] via-[#121929] to-[#0c1220] p-5 flex flex-col justify-between shadow-xl">
          <div>
            <span className="text-[10px] font-bold tracking-wider uppercase text-purple-400 flex items-center gap-1 mb-2">
              <TrendingUp size={12} /> Estimated Top-of-Funnel Deficit
            </span>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl md:text-5xl font-black text-purple-300 tabular-nums tracking-tight">
                ~{(gap_metrics.estimated_missed_views / 1000).toFixed(0)}k+
              </span>
              <span className="text-slate-400 font-bold text-xs">missed views</span>
            </div>
            <p className="text-xs text-slate-300 mt-2 leading-relaxed">
              Based on top viral video interest without dedicated vertical Reel/Short distribution.
            </p>
          </div>

          <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-xs">
            <span className="text-slate-400">Outlier Multiplier</span>
            <span className="font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              {gap_metrics.outlier_multiplier}× above median
            </span>
          </div>
        </div>

        {/* Executive Strategic Diagnostic */}
        <div className="rounded-2xl border border-white/10 bg-[#0f172a]/70 p-5 flex flex-col justify-between shadow-xl backdrop-blur-md">
          <div>
            <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400 flex items-center gap-1 mb-2">
              <Sparkles size={12} className="text-purple-400" /> Strategic Executive Summary
            </span>
            <p className="text-xs text-slate-300 leading-relaxed">
              {report.executive_summary}
            </p>
          </div>

          <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-[11px] text-slate-400">
            <span>Audit Engine: {report.model.replace("gemini/", "")}</span>
            <span className="text-purple-300 font-semibold flex items-center gap-1">
              <Flame size={12} className="text-amber-400" /> 5 Cuts Identified
            </span>
          </div>
        </div>
      </div>

      {/* ── Navigation Tabs ── */}
      <div className="flex items-center gap-1 bg-slate-900/80 p-1.5 rounded-xl border border-white/10 w-fit overflow-x-auto">
        <button
          onClick={() => setActiveTab("blueprints")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            activeTab === "blueprints"
              ? "bg-purple-600 text-white shadow-md"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Scissors size={13} /> 5 Viral Reel Blueprints
        </button>
        <button
          onClick={() => setActiveTab("hooks")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            activeTab === "hooks"
              ? "bg-purple-600 text-white shadow-md"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Zap size={13} /> 3-Sec Hook Teardowns
        </button>
        <button
          onClick={() => setActiveTab("sprint")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            activeTab === "sprint"
              ? "bg-purple-600 text-white shadow-md"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Calendar size={13} /> 30-Day Content Sprint
        </button>
        <button
          onClick={() => setActiveTab("outreach")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            activeTab === "outreach"
              ? "bg-purple-600 text-white shadow-md"
              : "text-slate-400 hover:text-white"
          }`}
        >
          <Mail size={13} /> Cold Outreach Script
        </button>
      </div>

      {/* ── TAB 1: 5 Viral Reel Blueprints ── */}
      {activeTab === "blueprints" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Film size={16} className="text-purple-400" /> Long-Form to Viral Reel Conversion Blueprints
            </h2>
            <span className="text-xs text-slate-400">
              Exact timestamps & 3s hooks mapped from their top uploads
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {blueprints.map((bp, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-white/10 bg-[#0f172a]/80 p-4 flex flex-col justify-between hover:border-purple-500/40 transition-all shadow-lg"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 border border-purple-500/30">
                      <Clock size={10} /> Clip {bp.clip_timestamp_start} – {bp.clip_timestamp_end} ({bp.duration_seconds}s)
                    </span>
                    <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 flex items-center gap-1">
                      <Flame size={10} className="text-orange-400" /> Viral Score: {bp.estimated_viral_score}/100
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-white mb-2 line-clamp-1" title={bp.source_title}>
                    From: {bp.source_title}
                  </h3>

                  {/* 3s Hook Highlight */}
                  <div className="rounded-lg bg-amber-500/[0.08] border border-amber-500/30 p-2.5 mb-3">
                    <p className="text-[9px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1">
                      <Zap size={10} /> 3-Second Spoken Hook
                    </p>
                    <p className="text-xs font-semibold text-amber-200 mt-1 italic">
                      &ldquo;{bp.viral_hook_3s}&rdquo;
                    </p>
                  </div>

                  {/* Visual Hook Prompt */}
                  <div className="text-xs text-slate-300 space-y-1 mb-3">
                    <p className="text-[10px] font-bold text-slate-400 uppercase">Visual & B-Roll Direction:</p>
                    <p className="text-[11px] text-slate-300 bg-slate-800/40 p-2 rounded border border-white/5">
                      {bp.visual_hook_prompt}
                    </p>
                  </div>

                  {/* Pacing & Audio */}
                  <div className="text-[11px] text-slate-400 flex items-center gap-1.5 mb-3">
                    <span className="font-semibold text-slate-300">Pacing & Audio:</span> {bp.pacing_and_sound}
                  </div>
                </div>

                {/* Caption & Copy Button */}
                <div className="pt-3 border-t border-white/10 flex items-center justify-between gap-2">
                  <span className="text-[10px] text-slate-500 truncate max-w-[200px]" title={bp.caption}>
                    {bp.caption}
                  </span>
                  <button
                    onClick={() => copyToClipboard(`HOOK: ${bp.viral_hook_3s}\n\nVISUAL: ${bp.visual_hook_prompt}\n\nCAPTION: ${bp.caption}`, `bp_${idx}`)}
                    className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-[11px] font-medium text-slate-300 hover:text-white border border-white/10 flex items-center gap-1 flex-shrink-0 transition-all"
                  >
                    {copiedKey === `bp_${idx}` ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    {copiedKey === `bp_${idx}` ? "Copied" : "Copy Blueprint"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 2: 3-Second Hook Teardowns ── */}
      {activeTab === "hooks" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Zap size={16} className="text-amber-400" /> 3-Second Hook Teardowns & Viral Rewrites
            </h2>
            <span className="text-xs text-slate-400">
              High-converting retention frameworks applied to passive titles
            </span>
          </div>

          <div className="space-y-3">
            {hook_teardowns.map((ht, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-white/10 bg-[#0f172a]/70 p-4 space-y-3 hover:border-slate-700 transition-all shadow-lg"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-red-500/20 text-red-400 font-bold text-xs flex items-center justify-center border border-red-500/30">
                      ✕
                    </span>
                    <span className="text-xs font-semibold text-slate-400">Weak Original Angle:</span>
                    <span className="text-xs font-bold text-slate-200 line-through">&ldquo;{ht.original_angle}&rdquo;</span>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 w-fit">
                    {ht.framework_used}
                  </span>
                </div>

                <div className="text-xs text-rose-300/80 bg-rose-950/20 border border-rose-900/30 p-2.5 rounded-lg flex items-start gap-2">
                  <AlertCircle size={14} className="flex-shrink-0 mt-0.5 text-rose-400" />
                  <span><strong>Drop-off Diagnosis:</strong> {ht.weakness_diagnosis}</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                  <div className="bg-emerald-950/20 border border-emerald-500/30 p-3 rounded-lg flex flex-col justify-between">
                    <div>
                      <p className="text-[9px] font-bold uppercase text-emerald-400 mb-1">Viral Rewrite Variant A</p>
                      <p className="text-xs font-semibold text-emerald-200">&ldquo;{ht.viral_rewrite_1}&rdquo;</p>
                    </div>
                    <button
                      onClick={() => copyToClipboard(ht.viral_rewrite_1, `hr1_${idx}`)}
                      className="mt-2 text-[10px] text-emerald-400/80 hover:text-emerald-300 flex items-center gap-1 self-end"
                    >
                      {copiedKey === `hr1_${idx}` ? <Check size={10} /> : <Copy size={10} />}
                      {copiedKey === `hr1_${idx}` ? "Copied" : "Copy"}
                    </button>
                  </div>

                  <div className="bg-blue-950/20 border border-blue-500/30 p-3 rounded-lg flex flex-col justify-between">
                    <div>
                      <p className="text-[9px] font-bold uppercase text-blue-400 mb-1">Viral Rewrite Variant B</p>
                      <p className="text-xs font-semibold text-blue-200">&ldquo;{ht.viral_rewrite_2}&rdquo;</p>
                    </div>
                    <button
                      onClick={() => copyToClipboard(ht.viral_rewrite_2, `hr2_${idx}`)}
                      className="mt-2 text-[10px] text-blue-400/80 hover:text-blue-300 flex items-center gap-1 self-end"
                    >
                      {copiedKey === `hr2_${idx}` ? <Check size={10} /> : <Copy size={10} />}
                      {copiedKey === `hr2_${idx}` ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 3: 30-Day Content Sprint ── */}
      {activeTab === "sprint" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Calendar size={16} className="text-purple-400" /> 30-Day Short-Form Publishing Sprint
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Structured into 3 core virality pillars: Authority, Problem-Agitation, and Viral Hacks
              </p>
            </div>

            {/* Week Selector */}
            <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-white/10">
              {[1, 2, 3, 4].map((wk) => (
                <button
                  key={wk}
                  onClick={() => setSelectedWeek(wk)}
                  className={`px-2.5 py-1 rounded text-xs font-bold transition-all ${
                    selectedWeek === wk
                      ? "bg-purple-600 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Week {wk}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {weekDays.map((item, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-white/10 bg-[#0f172a]/70 p-3.5 flex flex-col justify-between hover:border-purple-500/30 transition-all shadow"
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-2">
                    <span className="text-[10px] font-bold text-slate-400 uppercase">
                      Day {item.day_number}
                    </span>
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.2 rounded border ${
                        item.pillar.toLowerCase().includes("authority")
                          ? "bg-purple-500/20 text-purple-300 border-purple-500/30"
                          : item.pillar.toLowerCase().includes("problem")
                          ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                          : "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                      }`}
                    >
                      {item.pillar}
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-white mb-1.5 line-clamp-1">{item.topic}</h4>
                  <p className="text-[11px] text-slate-300 italic mb-2">&ldquo;{item.hook}&rdquo;</p>
                </div>

                <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-400">
                  <span>{item.format_style}</span>
                  <span className="text-purple-300 font-semibold">{item.target_cta}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 4: Turnkey Cold Outreach Script ── */}
      {activeTab === "outreach" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Mail size={16} className="text-emerald-400" /> Turnkey Cold Outreach Copy
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Hyper-personalized with their exact numbers and video timestamps
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Cold Email */}
            <div className="rounded-xl border border-white/10 bg-[#0f172a] p-4 flex flex-col justify-between shadow-lg">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <Mail size={14} className="text-blue-400" /> Cold Email Pitch
                  </span>
                  <button
                    onClick={() =>
                      copyToClipboard(
                        `Subject: ${outreach_copy.cold_email_subject}\n\n${outreach_copy.cold_email_body}`,
                        "email"
                      )
                    }
                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                  >
                    {copiedKey === "email" ? <Check size={12} /> : <Copy size={12} />}
                    {copiedKey === "email" ? "Copied" : "Copy Email"}
                  </button>
                </div>
                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-white/5 mb-2.5">
                  <p className="text-[10px] font-bold text-slate-400 uppercase">Subject Line:</p>
                  <p className="text-xs font-semibold text-white mt-0.5">{outreach_copy.cold_email_subject}</p>
                </div>
                <div className="bg-slate-900/40 p-3 rounded-lg border border-white/5 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {outreach_copy.cold_email_body}
                </div>
              </div>
            </div>

            {/* Direct Message & Follow-up */}
            <div className="space-y-4">
              <div className="rounded-xl border border-white/10 bg-[#0f172a] p-4 flex flex-col justify-between shadow-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <MessageSquare size={14} className="text-pink-400" /> Instagram DM / LinkedIn InMail
                  </span>
                  <button
                    onClick={() => copyToClipboard(outreach_copy.dm_pitch, "dm")}
                    className="text-xs text-pink-400 hover:text-pink-300 flex items-center gap-1"
                  >
                    {copiedKey === "dm" ? <Check size={12} /> : <Copy size={12} />}
                    {copiedKey === "dm" ? "Copied" : "Copy DM"}
                  </button>
                </div>
                <div className="bg-slate-900/40 p-3 rounded-lg border border-white/5 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {outreach_copy.dm_pitch}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#0f172a] p-4 flex flex-col justify-between shadow-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <Share2 size={14} className="text-amber-400" /> Follow-Up Bump Message
                  </span>
                  <button
                    onClick={() => copyToClipboard(outreach_copy.followup_bump, "bump")}
                    className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1"
                  >
                    {copiedKey === "bump" ? <Check size={12} /> : <Copy size={12} />}
                    {copiedKey === "bump" ? "Copied" : "Copy Bump"}
                  </button>
                </div>
                <div className="bg-slate-900/40 p-3 rounded-lg border border-white/5 text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {outreach_copy.followup_bump}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
