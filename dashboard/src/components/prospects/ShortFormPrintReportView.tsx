"use client";

import React from "react";
import {
  Clock,
  ExternalLink,
  Film,
  Flame,
  Instagram,
  Scissors,
  Sparkles,
  Target,
  TrendingUp,
  Youtube,
  Zap,
} from "lucide-react";
import { ShortFormAuditReport } from "@/lib/shortformProspectsApi";

export default function ShortFormPrintReportView({ report }: { report: ShortFormAuditReport }) {
  const { profile, gap_metrics, blueprints, hook_teardowns, sprint_calendar, outreach_copy } = report;

  return (
    <div className="bg-white text-slate-900 min-h-screen p-8 max-w-5xl mx-auto font-sans print:p-4 print:max-w-none">
      {/* ── Document Header ── */}
      <div className="border-b-2 border-slate-900 pb-4 mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="bg-purple-900 text-white text-[10px] font-black uppercase px-2 py-0.5 rounded tracking-wider">
              Institutional Deliverable
            </span>
            <span className="text-xs text-slate-500 font-semibold">
              Short-Form Content & Reels Growth Audit
            </span>
          </div>
          <h1 className="text-2xl font-black text-slate-950 tracking-tight">
            {profile.title} ({profile.handle})
          </h1>
          <p className="text-xs text-slate-600 mt-0.5">
            Platform: {profile.platform.toUpperCase()} · Audience: {profile.followers_or_subs.toLocaleString()} · Catalog: {profile.total_videos_or_posts} items
          </p>
        </div>

        <div className="text-right">
          <p className="text-xs font-bold text-slate-900">Wings of AI (Nexus)</p>
          <p className="text-[10px] text-slate-500">content.codingindia.co.in</p>
          <p className="text-[10px] text-slate-400 mt-1">Audit Date: {new Date(report.generated_at).toLocaleDateString()}</p>
        </div>
      </div>

      {/* ── Executive Score & Gap Matrix ── */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="border border-slate-200 bg-slate-50 p-4 rounded-lg">
          <p className="text-[9px] uppercase font-bold text-slate-500 mb-1">Short-Form Opportunity Score</p>
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-black text-purple-950">{gap_metrics.shortform_opportunity_score}</span>
            <span className="text-xs font-bold text-slate-500">/ 100</span>
          </div>
          <p className="text-[10px] font-bold text-purple-900 mt-1">{gap_metrics.opportunity_verdict}</p>
        </div>

        <div className="border border-slate-200 bg-slate-50 p-4 rounded-lg">
          <p className="text-[9px] uppercase font-bold text-slate-500 mb-1">Estimated Top-of-Funnel Deficit</p>
          <p className="text-3xl font-black text-slate-900">~{(gap_metrics.estimated_missed_views / 1000).toFixed(0)}k+</p>
          <p className="text-[10px] text-slate-600 mt-1">Shorts Ratio: {gap_metrics.shorts_ratio_pct}% ({gap_metrics.shorts_count} Shorts / {gap_metrics.longform_count} Long)</p>
        </div>

        <div className="border border-slate-200 bg-slate-50 p-4 rounded-lg">
          <p className="text-[9px] uppercase font-bold text-slate-500 mb-1">Outlier Velocity</p>
          <p className="text-3xl font-black text-emerald-800">{gap_metrics.outlier_multiplier}×</p>
          <p className="text-[10px] text-slate-600 mt-1">Proven demand for core video themes</p>
        </div>
      </div>

      {/* ── Executive Summary ── */}
      <div className="border border-purple-200 bg-purple-50/50 p-4 rounded-lg mb-6">
        <p className="text-[10px] font-bold uppercase tracking-wider text-purple-950 mb-1">Strategic Audit Assessment</p>
        <p className="text-xs text-slate-800 leading-relaxed">{report.executive_summary}</p>
      </div>

      {/* ── 5 Viral Reel Blueprints ── */}
      <div className="mb-6">
        <h2 className="text-sm font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-3 flex items-center gap-1.5">
          <Film size={14} /> Top 5 Long-Form to Viral Reel Conversion Blueprints
        </h2>

        <div className="space-y-3">
          {blueprints.map((bp, idx) => (
            <div key={idx} className="border border-slate-200 rounded-lg p-3 bg-white">
              <div className="flex items-center justify-between text-[11px] mb-1.5">
                <span className="font-bold text-slate-900">
                  Cut #{idx + 1}: {bp.source_title}
                </span>
                <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono font-bold text-[10px]">
                  Timestamp {bp.clip_timestamp_start} – {bp.clip_timestamp_end} ({bp.duration_seconds}s)
                </span>
              </div>

              <div className="bg-amber-50 border border-amber-200 p-2 rounded mb-2">
                <p className="text-[9px] font-bold text-amber-900 uppercase">3-Second Spoken Hook</p>
                <p className="text-xs font-semibold text-amber-950 italic mt-0.5">&ldquo;{bp.viral_hook_3s}&rdquo;</p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-600">
                <div>
                  <span className="font-bold text-slate-800">Visual & B-Roll:</span> {bp.visual_hook_prompt}
                </div>
                <div>
                  <span className="font-bold text-slate-800">Pacing & Audio:</span> {bp.pacing_and_sound}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Hook Teardowns ── */}
      <div className="mb-6 page-break-before">
        <h2 className="text-sm font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-3 flex items-center gap-1.5">
          <Zap size={14} /> 3-Second Retention Hook Teardowns & Rewrites
        </h2>

        <div className="space-y-2.5">
          {hook_teardowns.map((ht, idx) => (
            <div key={idx} className="border border-slate-200 rounded-lg p-2.5 bg-slate-50/50">
              <div className="flex items-center justify-between text-[10px] mb-1">
                <span className="font-bold text-slate-500 line-through">Original: &ldquo;{ht.original_angle}&rdquo;</span>
                <span className="font-bold text-purple-900 bg-purple-100 px-1.5 py-0.2 rounded text-[9px]">{ht.framework_used}</span>
              </div>
              <p className="text-[10px] text-rose-800 mb-1.5">
                <strong>Drop-off Risk:</strong> {ht.weakness_diagnosis}
              </p>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="bg-white border border-emerald-200 p-1.5 rounded">
                  <span className="font-bold text-emerald-800">Variant A:</span> {ht.viral_rewrite_1}
                </div>
                <div className="bg-white border border-blue-200 p-1.5 rounded">
                  <span className="font-bold text-blue-800">Variant B:</span> {ht.viral_rewrite_2}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── 30-Day Content Sprint ── */}
      <div className="mb-6">
        <h2 className="text-sm font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-3">
          30-Day Short-Form Content Sprint (4-Week Publishing Architecture)
        </h2>

        <div className="grid grid-cols-2 gap-2 text-[10px]">
          {sprint_calendar.slice(0, 14).map((item, idx) => (
            <div key={idx} className="border border-slate-200 p-2 rounded bg-white">
              <div className="flex items-center justify-between font-bold text-slate-700 mb-0.5">
                <span>Day {item.day_number} (Wk {item.week_number})</span>
                <span className="text-[9px] text-purple-900">{item.pillar}</span>
              </div>
              <p className="font-bold text-slate-950 truncate">{item.topic}</p>
              <p className="text-slate-600 italic text-[9px] truncate">&ldquo;{item.hook}&rdquo;</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="border-t border-slate-200 pt-3 text-center text-[10px] text-slate-400">
        Generated by Wings of AI (Nexus) Institutional Audit Suite · confidential client deliverable
      </div>
    </div>
  );
}
