"use client";

import { useState } from "react";
import { AlertTriangle, Check, ExternalLink, Loader2, Sparkles, Users, X } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { CompetitorCandidate, DiscoveryRun, competitorsApi } from "@/lib/youtubeCompetitorsApi";

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

const TIER_STYLE: Record<string, string> = {
  peer: "bg-blue-500/10 text-blue-300 border-blue-400/30",
  aspirational: "bg-purple-500/10 text-purple-300 border-purple-400/30",
  adjacent: "bg-slate-500/10 text-slate-300 border-slate-400/30",
};

interface Props {
  onClose: () => void;
  onApplied: () => void;
}

type Phase = "form" | "searching" | "results" | "applying" | "done";

export default function CompetitorDiscoveryModal({ onClose, onApplied }: Props) {
  const [phase, setPhase] = useState<Phase>("form");
  const [niche, setNiche] = useState("");
  const [count, setCount] = useState(20);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [applyResult, setApplyResult] = useState<{ approved: number; rejected: number } | null>(null);

  const runDiscovery = async () => {
    setPhase("searching");
    setError(null);
    try {
      const result = await competitorsApi.discover({ niche: niche.trim(), count });
      setRun(result);
      setSelected(new Set(result.candidates.map((c) => c.channel_id)));
      setPhase("results");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Discovery failed");
      setPhase("form");
    }
  };

  const toggle = (channelId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) next.delete(channelId);
      else next.add(channelId);
      return next;
    });
  };

  const applyDecisions = async () => {
    if (!run) return;
    setPhase("applying");
    setError(null);
    const approved = run.candidates.filter((c) => selected.has(c.channel_id)).map((c) => c.channel_id);
    const rejected = run.candidates.filter((c) => !selected.has(c.channel_id)).map((c) => c.channel_id);
    try {
      const result = await competitorsApi.approve(run.id, approved, rejected);
      setApplyResult(result);
      setPhase("done");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save your decisions");
      setPhase("results");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-8 px-4">
      <div className="w-full max-w-3xl bg-[#0b1120] border border-white/10 rounded-2xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <Sparkles className="text-red-400" size={18} />
            <h3 className="text-white font-semibold text-sm">Find competitors</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-5">
          {error && (
            <div className="mb-4 flex items-start gap-2 px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300 text-sm">
              <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {phase === "form" && (
            <div className="space-y-4">
              <p className="text-slate-400 text-sm">
                Discovers real, active creator channels directly from YouTube in your niche.
                Channels you&apos;ve already approved or rejected are never proposed again.
              </p>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  Niche <span className="text-slate-600">(optional — inferred from your channel if left blank)</span>
                </label>
                <input
                  value={niche}
                  onChange={(e) => setNiche(e.target.value)}
                  placeholder="e.g. AI coding tools, backend engineering"
                  className="w-full px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-red-500/40"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">How many</label>
                <select
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  className="px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-red-500/40"
                >
                  {[10, 15, 20, 25, 30].map((n) => (
                    <option key={n} value={n} className="bg-[#0f172a]">{n} channels</option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                  Cancel
                </button>
                <button
                  onClick={runDiscovery}
                  className="flex items-center gap-2 px-4 py-2 bg-red-500/15 hover:bg-red-500/25 text-red-300 text-sm font-medium rounded-lg transition-colors border border-red-500/20"
                >
                  <Sparkles size={14} /> Discover
                </button>
              </div>
            </div>
          )}

          {phase === "searching" && (
            <div className="py-16 text-center">
              <Loader2 className="animate-spin text-red-400 mx-auto mb-4" size={28} />
              <p className="text-slate-300 text-sm">Searching, proposing and verifying real channels…</p>
              <p className="text-slate-600 text-xs mt-1">This checks each candidate against the live YouTube API — usually 30–60s.</p>
            </div>
          )}

          {phase === "results" && run && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  <span className="text-slate-300 font-medium">{run.candidates.length}</span> verified real channels
                  {run.niche && <> in <span className="text-slate-400">{run.niche}</span></>}
                </span>
                <span>{run.quota_units_spent} YouTube API units spent</span>
              </div>

              {run.candidates.length === 0 ? (
                <div className="py-10 text-center">
                  <Users className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                  <p className="text-slate-400 text-sm">No new competitors found — you may already be tracking everyone relevant, or try a more specific niche.</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <div className="flex gap-2">
                      <button
                        onClick={() => setSelected(new Set(run.candidates.map((c) => c.channel_id)))}
                        className="text-xs text-slate-400 hover:text-slate-200 underline underline-offset-2"
                      >
                        Select all
                      </button>
                      <button
                        onClick={() => setSelected(new Set())}
                        className="text-xs text-slate-400 hover:text-slate-200 underline underline-offset-2"
                      >
                        Select none
                      </button>
                    </div>
                    <span className="text-xs text-slate-500">{selected.size} selected</span>
                  </div>

                  <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                    {run.candidates.map((c: CompetitorCandidate) => {
                      const checked = selected.has(c.channel_id);
                      return (
                        <label
                          key={c.channel_id}
                          className={`flex items-start gap-3 px-3 py-3 rounded-xl border cursor-pointer transition-colors ${
                            checked ? "border-red-500/30 bg-red-500/[0.04]" : "border-white/5 bg-white/[0.02] hover:bg-white/[0.03]"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggle(c.channel_id)}
                            className="mt-1 accent-red-500"
                          />
                          <div className="flex-shrink-0 w-9 h-9">
                            {c.thumbnail_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={c.thumbnail_url} alt="" className="w-9 h-9 rounded-full object-cover" />
                            ) : (
                              <div className="w-9 h-9 rounded-full bg-white/5 flex items-center justify-center text-slate-500">
                                <Users size={14} />
                              </div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <a
                                href={`https://youtube.com/channel/${c.channel_id}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-slate-200 font-medium text-sm hover:text-red-300 flex items-center gap-1"
                              >
                                {c.title}
                                <ExternalLink size={11} className="opacity-40" />
                              </a>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${TIER_STYLE[c.tier] ?? TIER_STYLE.peer}`}>
                                {c.tier}
                              </span>
                            </div>
                            <p className="text-slate-500 text-xs mt-0.5">
                              {fmtNum(c.subscriber_count)} subscribers · {fmtNum(c.video_count)} videos
                            </p>
                            {c.rationale && <p className="text-slate-400 text-xs mt-1">{c.rationale}</p>}
                          </div>
                        </label>
                      );
                    })}
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-white/5">
                    <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
                      Discard
                    </button>
                    <button
                      onClick={applyDecisions}
                      className="flex items-center gap-2 px-4 py-2 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-sm font-medium rounded-lg transition-colors border border-emerald-500/20"
                    >
                      <Check size={14} /> Save decisions
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {phase === "applying" && (
            <div className="py-16 text-center">
              <Loader2 className="animate-spin text-emerald-400 mx-auto mb-3" size={24} />
              <p className="text-slate-300 text-sm">Saving and fetching their latest videos…</p>
            </div>
          )}

          {phase === "done" && applyResult && (
            <div className="py-10 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto">
                <Check className="text-emerald-400" size={22} />
              </div>
              <p className="text-slate-200 text-sm">
                Now tracking <strong className="text-emerald-400">{applyResult.approved}</strong> new competitor
                {applyResult.approved === 1 ? "" : "s"}
                {applyResult.rejected > 0 && <> · {applyResult.rejected} rejected</>}
              </p>
              <button
                onClick={onApplied}
                className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-slate-200 text-sm font-medium rounded-lg transition-colors border border-white/10"
              >
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
