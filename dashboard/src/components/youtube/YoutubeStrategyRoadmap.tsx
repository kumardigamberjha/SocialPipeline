"use client";

import React, { useState } from "react";
import {
  Compass,
  Map,
  Wand2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Ruler,
  Puzzle,
  ListOrdered,
  CalendarDays,
} from "lucide-react";

const BASE = "http://localhost:8000/api/youtube-analytics";

interface Strategy {
  verdict: string;
  whats_working: string[];
  underperforming: string[];
  format_insights: string[];
  content_gaps: string[];
  priorities: string[];
  model?: string;
}
interface RoadmapItem {
  title: string;
  format: string;
  theme: string;
  rationale: string;
  date?: string;
}
interface RoadmapWeek {
  week_number: number;
  start_date: string;
  focus: string;
  items: RoadmapItem[];
}
interface Roadmap {
  cadence: string;
  weeks: RoadmapWeek[];
  model?: string;
}

function Section({
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
    <div className="rounded-xl bg-white/[0.02] border border-white/5 p-4">
      <p className={`flex items-center gap-2 text-xs font-bold uppercase tracking-wider mb-3 ${tint}`}>
        <Icon size={14} /> {title}
      </p>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-300 leading-relaxed">
            {ordered ? (
              <span className={`text-xs font-bold tabular-nums ${tint} flex-shrink-0 w-4`}>{i + 1}</span>
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

export default function YoutubeStrategyRoadmap({ timeRange = "all_time" }: { timeRange?: string }) {
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [strategyLoading, setStrategyLoading] = useState(false);
  const [strategyError, setStrategyError] = useState("");

  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [roadmapLoading, setRoadmapLoading] = useState(false);
  const [roadmapError, setRoadmapError] = useState("");

  const runStrategy = async (refresh = false) => {
    setStrategyLoading(true);
    setStrategyError("");
    try {
      const res = await fetch(`${BASE}/strategy?time_range=${timeRange}&refresh=${refresh}`, { method: "POST" });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `Failed (${res.status})`);
      }
      setStrategy(await res.json());
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : "Strategy failed");
    } finally {
      setStrategyLoading(false);
    }
  };

  const runRoadmap = async (refresh = false) => {
    setRoadmapLoading(true);
    setRoadmapError("");
    try {
      const res = await fetch(`${BASE}/roadmap?time_range=${timeRange}&weeks=4&refresh=${refresh}`, { method: "POST" });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `Failed (${res.status})`);
      }
      setRoadmap(await res.json());
    } catch (e) {
      setRoadmapError(e instanceof Error ? e.message : "Roadmap failed");
    } finally {
      setRoadmapLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Channel Strategy */}
      <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
        <div className="p-6 border-b border-white/5 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-cyan-500/10 text-cyan-400 rounded-xl">
              <Compass size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Channel Strategy</h2>
              <p className="text-slate-500 text-xs mt-0.5">
                What&apos;s working, what to fix, and what to prioritize{strategy?.model ? ` · ${strategy.model}` : ""}
              </p>
            </div>
          </div>
          <button
            onClick={() => runStrategy(!!strategy)}
            disabled={strategyLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-cyan-600/20 text-cyan-200 border border-cyan-500/30 hover:bg-cyan-600/30 transition-colors disabled:opacity-50"
          >
            <Wand2 size={16} className={strategyLoading ? "animate-pulse" : ""} />
            {strategyLoading ? "Analyzing…" : strategy ? "Regenerate" : "Generate Strategy"}
          </button>
        </div>
        <div className="p-6">
          {!strategy && !strategyLoading && !strategyError && (
            <p className="text-slate-500 text-sm text-center py-8">
              Generate a data-driven strategy brief from your channel + current web trends.
            </p>
          )}
          {strategyLoading && (
            <div className="text-center py-8">
              <div className="animate-spin text-cyan-400 inline-block mb-2">
                <RefreshCw size={24} />
              </div>
              <p className="text-slate-400 text-sm animate-pulse">Researching trends and analyzing your channel… ~20-40s.</p>
            </div>
          )}
          {strategyError && <p className="text-red-400 text-sm py-2">{strategyError}</p>}
          {strategy && !strategyLoading && (
            <div className="space-y-4">
              {strategy.verdict && (
                <div className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                  <p className="text-slate-200 leading-relaxed">{strategy.verdict}</p>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Section icon={CheckCircle2} title="What's Working" tint="text-green-400" items={strategy.whats_working} />
                <Section icon={AlertTriangle} title="Underperforming" tint="text-red-400" items={strategy.underperforming} />
                <Section icon={Ruler} title="Format & Cadence" tint="text-blue-400" items={strategy.format_insights} />
                <Section icon={Puzzle} title="Content Gaps" tint="text-amber-400" items={strategy.content_gaps} />
              </div>
              <Section icon={ListOrdered} title="Do This Next (Priorities)" tint="text-purple-400" items={strategy.priorities} ordered />
            </div>
          )}
        </div>
      </div>

      {/* 30-Day Roadmap */}
      <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
        <div className="p-6 border-b border-white/5 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-purple-500/10 text-purple-400 rounded-xl">
              <Map size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">30-Day Content Roadmap</h2>
              <p className="text-slate-500 text-xs mt-0.5">
                A 4-week posting plan with dates{roadmap?.cadence ? ` · ${roadmap.cadence}` : ""}
              </p>
            </div>
          </div>
          <button
            onClick={() => runRoadmap(!!roadmap)}
            disabled={roadmapLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors disabled:opacity-50"
          >
            <Wand2 size={16} className={roadmapLoading ? "animate-pulse" : ""} />
            {roadmapLoading ? "Planning…" : roadmap ? "Regenerate" : "Generate Roadmap"}
          </button>
        </div>
        <div className="p-6">
          {!roadmap && !roadmapLoading && !roadmapError && (
            <p className="text-slate-500 text-sm text-center py-8">
              Generate a dated 4-week posting plan across your content themes.
            </p>
          )}
          {roadmapLoading && (
            <div className="text-center py-8">
              <div className="animate-spin text-purple-400 inline-block mb-2">
                <RefreshCw size={24} />
              </div>
              <p className="text-slate-400 text-sm animate-pulse">Building your 4-week roadmap… ~30-60s.</p>
            </div>
          )}
          {roadmapError && <p className="text-red-400 text-sm py-2">{roadmapError}</p>}
          {roadmap && !roadmapLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {roadmap.weeks.map((w) => (
                <div key={w.week_number} className="rounded-xl bg-white/[0.02] border border-white/5 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-white">
                      Week {w.week_number}
                      <span className="text-slate-500 font-normal"> — {w.focus}</span>
                    </p>
                  </div>
                  <div className="space-y-2">
                    {w.items.map((it, i) => (
                      <div key={i} className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-white">{it.title}</p>
                          {it.format && (
                            <span className="text-[10px] uppercase tracking-wider text-purple-300 bg-purple-500/10 border border-purple-500/20 rounded px-1.5 py-0.5 flex-shrink-0">
                              {it.format}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1.5 text-[11px] text-slate-500">
                          <CalendarDays size={12} />
                          <span className="tabular-nums">{it.date}</span>
                          {it.theme && <span>· {it.theme}</span>}
                        </div>
                        {it.rationale && <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">{it.rationale}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
