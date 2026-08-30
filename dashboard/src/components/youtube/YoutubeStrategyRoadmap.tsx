"use client";

import React, { useCallback, useEffect, useState } from "react";
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
  CalendarPlus,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";
import AnalysisHistoryPicker, {
  formatRunTime,
  type HistoryEntry,
} from "@/components/analysis/AnalysisHistoryPicker";
import { Section } from "@/components/youtube/shared/ReportSections";
import {
  youtubeAnalyticsApi,
  normalizeRun,
  isRoadmapEmpty,
  isStrategyEmpty,
  type AnalysisRun,
  type AddToPlanResult,
  type Roadmap,
  type RoadmapItemPayload,
  type Strategy,
} from "@/lib/youtubeAnalyticsApi";

const ROADMAP_WEEKS = 4;

/** "Generated 22 Aug 2026, 14:32 · gemini/gemini-2.5-flash" */
function RunStamp({ createdAt, model }: { createdAt: string | null; model?: string }) {
  const when = formatRunTime(createdAt);
  if (!when && !model) return null;
  return (
    <>
      {when ? ` · Generated ${when}` : ""}
      {model ? ` · ${model}` : ""}
    </>
  );
}

export default function YoutubeStrategyRoadmap({ timeRange = "all_time" }: { timeRange?: string }) {
  const [strategy, setStrategy] = useState<AnalysisRun<Strategy> | null>(null);
  const [strategyLoading, setStrategyLoading] = useState(false);
  const [strategyError, setStrategyError] = useState("");
  const [strategyHistory, setStrategyHistory] = useState<HistoryEntry[]>([]);

  const [roadmap, setRoadmap] = useState<AnalysisRun<Roadmap> | null>(null);
  const [roadmapLoading, setRoadmapLoading] = useState(false);
  const [roadmapError, setRoadmapError] = useState("");
  const [roadmapHistory, setRoadmapHistory] = useState<HistoryEntry[]>([]);

  // Roadmap → planner. Keys are `${week_number}-${index}`; an empty set means
  // "add everything", which is the common case.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [addResult, setAddResult] = useState<AddToPlanResult | null>(null);

  const toEntries = (rows: { id: string; created_at: string; model: string | null; weeks: number | null }[]) =>
    rows.map((row) => ({
      id: row.id,
      created_at: row.created_at,
      model: row.model,
      detail: row.weeks ? `${row.weeks} weeks` : undefined,
    }));

  const loadHistory = useCallback(async () => {
    const [strategyRows, roadmapRows] = await Promise.allSettled([
      youtubeAnalyticsApi.history("strategy"),
      youtubeAnalyticsApi.history("roadmap"),
    ]);
    if (strategyRows.status === "fulfilled") setStrategyHistory(toEntries(strategyRows.value));
    if (roadmapRows.status === "fulfilled") setRoadmapHistory(toEntries(roadmapRows.value));
  }, []);

  // Restore the last saved run on mount. Both reports are persisted server-side
  // the moment they are generated, so a reload (or a tab switch, which unmounts
  // this component) must not send the user back to an empty "Generate" state.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const [savedStrategy, savedRoadmap] = await Promise.allSettled([
        youtubeAnalyticsApi.latest("strategy", timeRange),
        youtubeAnalyticsApi.latest("roadmap", timeRange),
      ]);
      if (cancelled) return;

      if (savedStrategy.status === "fulfilled") {
        const run = normalizeRun<Strategy>(savedStrategy.value, isStrategyEmpty);
        if (run) setStrategy(run);
      }
      if (savedRoadmap.status === "fulfilled") {
        const run = normalizeRun<Roadmap>(savedRoadmap.value, isRoadmapEmpty);
        if (run) setRoadmap(run);
      }
    })();

    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [timeRange, loadHistory]);

  const runStrategy = async (refresh = false) => {
    setStrategyLoading(true);
    setStrategyError("");
    try {
      const raw = await youtubeAnalyticsApi.generateStrategy(timeRange, refresh);
      const run = normalizeRun<Strategy>(raw, isStrategyEmpty);
      if (run) setStrategy(run);
      loadHistory();
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
      const raw = await youtubeAnalyticsApi.generateRoadmap(timeRange, ROADMAP_WEEKS, refresh);
      const run = normalizeRun<Roadmap>(raw, isRoadmapEmpty);
      if (run) setRoadmap(run);
      resetSelection();
      loadHistory();
    } catch (e) {
      setRoadmapError(e instanceof Error ? e.message : "Roadmap failed");
    } finally {
      setRoadmapLoading(false);
    }
  };

  const openStrategyRun = async (id: string) => {
    setStrategyLoading(true);
    setStrategyError("");
    try {
      const run = normalizeRun<Strategy>(await youtubeAnalyticsApi.byId(id), isStrategyEmpty);
      if (run) setStrategy(run);
    } catch (e) {
      setStrategyError(e instanceof Error ? e.message : "Could not load that run");
    } finally {
      setStrategyLoading(false);
    }
  };

  const resetSelection = () => {
    setSelected(new Set());
    setAddResult(null);
    setAddError("");
  };

  const toggleItem = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  /** Flatten the weeks, keeping only what the user picked (or all of it). */
  const itemsToAdd = (): RoadmapItemPayload[] => {
    if (!roadmap) return [];
    const out: RoadmapItemPayload[] = [];
    roadmap.data.weeks.forEach((week) => {
      week.items.forEach((item, index) => {
        const key = `${week.week_number}-${index}`;
        if (selected.size === 0 || selected.has(key)) {
          out.push({ ...item, week_number: week.week_number });
        }
      });
    });
    return out;
  };

  const addToPlanner = async () => {
    const items = itemsToAdd();
    if (!items.length) return;
    setAdding(true);
    setAddError("");
    setAddResult(null);
    try {
      setAddResult(
        await youtubeAnalyticsApi.addRoadmapToPlan({
          items,
          plan_name: `Roadmap — ${new Date().toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}`,
        }),
      );
      setSelected(new Set());
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Could not add to the planner");
    } finally {
      setAdding(false);
    }
  };

  const openRoadmapRun = async (id: string) => {
    setRoadmapLoading(true);
    setRoadmapError("");
    try {
      const run = normalizeRun<Roadmap>(await youtubeAnalyticsApi.byId(id), isRoadmapEmpty);
      if (run) setRoadmap(run);
      resetSelection();
    } catch (e) {
      setRoadmapError(e instanceof Error ? e.message : "Could not load that run");
    } finally {
      setRoadmapLoading(false);
    }
  };

  const deleteRun = async (id: string, kind: "strategy" | "roadmap") => {
    try {
      await youtubeAnalyticsApi.remove(id);
    } catch {
      return; // Leave the list as-is; the row is still there.
    }
    if (kind === "strategy") {
      setStrategyHistory((rows) => rows.filter((r) => r.id !== id));
      if (strategy?.analysisId === id) setStrategy(null);
    } else {
      setRoadmapHistory((rows) => rows.filter((r) => r.id !== id));
      if (roadmap?.analysisId === id) setRoadmap(null);
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
                What&apos;s working, what to fix, and what to prioritize
                <RunStamp createdAt={strategy?.createdAt ?? null} model={strategy?.data.model} />
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <AnalysisHistoryPicker
              entries={strategyHistory}
              currentId={strategy?.analysisId ?? null}
              loading={strategyLoading}
              onSelect={openStrategyRun}
              onDelete={(id) => deleteRun(id, "strategy")}
              tint="text-cyan-200"
            />
            <button
              onClick={() => runStrategy(!!strategy)}
              disabled={strategyLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-cyan-600/20 text-cyan-200 border border-cyan-500/30 hover:bg-cyan-600/30 transition-colors disabled:opacity-50"
            >
              <Wand2 size={16} className={strategyLoading ? "animate-pulse" : ""} />
              {strategyLoading ? "Analyzing…" : strategy ? "Regenerate" : "Generate Strategy"}
            </button>
          </div>
        </div>
        <div className="p-6">
          {!strategy && !strategyLoading && !strategyError && (
            <p className="text-slate-400 text-sm text-center py-8">
              Click &quot;Generate Strategy&quot; to build an AI Growth Strategy Brief powered by Gemini 3.6 Flash and live search trends.
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
              {strategy.data.verdict && (
                <div className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                  <p className="text-slate-200 leading-relaxed">{strategy.data.verdict}</p>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Section icon={CheckCircle2} title="What's Working" tint="text-green-400" items={strategy.data.whats_working} />
                <Section icon={AlertTriangle} title="Underperforming" tint="text-red-400" items={strategy.data.underperforming} />
                <Section icon={Ruler} title="Format & Cadence" tint="text-blue-400" items={strategy.data.format_insights} />
                <Section icon={Puzzle} title="Content Gaps" tint="text-amber-400" items={strategy.data.content_gaps} />
              </div>
              <Section icon={ListOrdered} title="Do This Next (Priorities)" tint="text-purple-400" items={strategy.data.priorities} ordered />
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
                A 4-week posting plan with dates
                {roadmap?.data.cadence ? ` · ${roadmap.data.cadence}` : ""}
                <RunStamp createdAt={roadmap?.createdAt ?? null} model={roadmap?.data.model} />
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <AnalysisHistoryPicker
              entries={roadmapHistory}
              currentId={roadmap?.analysisId ?? null}
              loading={roadmapLoading}
              onSelect={openRoadmapRun}
              onDelete={(id) => deleteRun(id, "roadmap")}
              tint="text-purple-200"
            />
            {roadmap && (
              <button
                onClick={addToPlanner}
                disabled={adding || roadmapLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600/20 text-emerald-200 border border-emerald-500/30 hover:bg-emerald-600/30 transition-colors disabled:opacity-50"
              >
                <CalendarPlus size={16} className={adding ? "animate-pulse" : ""} />
                {adding
                  ? "Scheduling…"
                  : selected.size
                    ? `Add ${selected.size} to Planner`
                    : "Add all to Planner"}
              </button>
            )}
            <button
              onClick={() => runRoadmap(!!roadmap)}
              disabled={roadmapLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors disabled:opacity-50"
            >
              <Wand2 size={16} className={roadmapLoading ? "animate-pulse" : ""} />
              {roadmapLoading ? "Planning…" : roadmap ? "Regenerate" : "Generate Roadmap"}
            </button>
          </div>
        </div>
        <div className="p-6">
          {!roadmap && !roadmapLoading && !roadmapError && (
            <p className="text-slate-400 text-sm text-center py-8">
              Click &quot;Generate Roadmap&quot; to build a dated 4-week publishing schedule tailored to your content topics.
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
          {addError && <p className="text-red-400 text-sm py-2">{addError}</p>}

          {addResult && (
            <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.07] p-4 space-y-2">
              <p className="text-sm text-emerald-200">
                Scheduled <strong>{addResult.created.length}</strong>{" "}
                {addResult.created.length === 1 ? "item" : "items"}
                {addResult.profile?.source === "channel_data"
                  ? " on your best-performing weekdays"
                  : " on the roadmap's own dates"}
                .
                {addResult.plan_id && (
                  <Link
                    href={`/planner?plan=${addResult.plan_id}`}
                    className="inline-flex items-center gap-1 ml-2 text-emerald-300 underline underline-offset-2 hover:text-emerald-200"
                  >
                    Open plan <ExternalLink size={12} />
                  </Link>
                )}
              </p>
              {addResult.skipped.length > 0 && (
                <div className="text-xs text-slate-400">
                  <p className="mb-1">
                    Skipped {addResult.skipped.length}{" "}
                    {addResult.skipped.length === 1 ? "item" : "items"}:
                  </p>
                  <ul className="space-y-0.5">
                    {addResult.skipped.map((s, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-slate-600">·</span>
                        <span>
                          {s.title} <span className="text-slate-600">— {s.reason}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {roadmap && !roadmapLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {roadmap.data.weeks.map((w) => (
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
                          <label className="flex items-start gap-2 cursor-pointer min-w-0">
                            <input
                              type="checkbox"
                              checked={selected.has(`${w.week_number}-${i}`)}
                              onChange={() => toggleItem(`${w.week_number}-${i}`)}
                              aria-label={`Select "${it.title}"`}
                              className="mt-0.5 flex-shrink-0 accent-emerald-500"
                            />
                            <p className="text-sm font-medium text-white">{it.title}</p>
                          </label>
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
