"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, RefreshCw, Target, Trash2 } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { GOAL_METRICS, Goal, GoalMetric, piApi } from "@/lib/personalIntelligenceApi";

function fmtNum(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

function daysLeft(deadline: string): number {
  const d = new Date(deadline + "T23:59:59Z").getTime();
  return Math.ceil((d - Date.now()) / 86_400_000);
}

export default function GoalList() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [metric, setMetric] = useState<GoalMetric>("subscribers");
  const [targetValue, setTargetValue] = useState("");
  const [deadline, setDeadline] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await piApi.listGoals("active");
      setGoals(data);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load goals");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addGoal = async () => {
    const value = Number(targetValue);
    if (!title.trim() || !deadline || !value || value <= 0) return;
    setSaving(true);
    try {
      await piApi.createGoal({ title: title.trim(), metric, target_value: value, deadline });
      setTitle("");
      setTargetValue("");
      setDeadline("");
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to add goal");
    } finally {
      setSaving(false);
    }
  };

  const refreshGoal = async (goalId: string) => {
    setRefreshingId(goalId);
    try {
      const progress = await piApi.refreshGoal(goalId);
      setGoals((prev) => prev?.map((g) => (g.id === goalId ? { ...g, progress } : g)) ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to refresh progress");
    } finally {
      setRefreshingId(null);
    }
  };

  const removeGoal = async (goalId: string) => {
    setGoals((prev) => prev?.filter((g) => g.id !== goalId) ?? null);
    try {
      await piApi.deleteGoal(goalId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete goal");
      load();
    }
  };

  if (goals === null) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="animate-spin text-slate-500" size={22} />
      </div>
    );
  }

  return (
    <div className="space-y-4 py-6">
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">{error}</div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-slate-500 text-xs">
          Progress is read from your synced YouTube data. When a goal is active, the planner and
          strategist see how far ahead or behind pace you are.
        </p>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 text-xs font-medium rounded-lg transition-colors border border-violet-500/20 flex-shrink-0 ml-4"
          >
            <Plus size={14} /> Add goal
          </button>
        )}
      </div>

      {showForm && (
        <div className="glass-card rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Gain 2,000 subscribers this month"
            maxLength={200}
            className="w-full px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-violet-500/40"
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as GoalMetric)}
              className="px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 focus:outline-none"
            >
              {GOAL_METRICS.map((m) => (
                <option key={m.value} value={m.value} className="bg-[#0f172a]">{m.label}</option>
              ))}
            </select>
            <input
              type="number"
              value={targetValue}
              onChange={(e) => setTargetValue(e.target.value)}
              placeholder="Target (e.g. 2000)"
              min={1}
              className="w-36 px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none"
            />
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 focus:outline-none"
            />
            <div className="flex-1" />
            <button
              onClick={() => setShowForm(false)}
              className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={addGoal}
              disabled={saving || !title.trim() || !deadline || !targetValue}
              className="px-3.5 py-1.5 bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 text-xs font-medium rounded-lg transition-colors border border-violet-500/20 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save goal"}
            </button>
          </div>
        </div>
      )}

      {goals.length === 0 && !showForm ? (
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-12 text-center">
          <Target className="w-6 h-6 text-slate-600 mx-auto mb-2" />
          <p className="text-slate-400 text-sm">No active goals — set one to get goal-aware plans and progress tracking.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {goals.map((goal) => {
            const pct = goal.progress?.pct;
            const known = pct !== null && pct !== undefined;
            const onTrack = goal.progress?.on_track;
            const remaining = daysLeft(goal.deadline);

            return (
              <div key={goal.id} className="glass-card rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-slate-200 text-sm font-medium truncate">{goal.title}</p>
                    <p className="text-slate-500 text-xs mt-0.5">
                      {GOAL_METRICS.find((m) => m.value === goal.metric)?.label} · target {fmtNum(goal.target_value)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => refreshGoal(goal.id)}
                      disabled={refreshingId === goal.id}
                      title="Refresh progress"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-blue-300 hover:bg-blue-500/10 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw size={13} className={refreshingId === goal.id ? "animate-spin" : ""} />
                    </button>
                    <button
                      onClick={() => removeGoal(goal.id)}
                      className="p-1.5 rounded-lg text-slate-600 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {known ? (
                  <>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${onTrack ? "bg-emerald-500" : "bg-amber-500"}`}
                        style={{ width: `${Math.min(100, Math.max(0, pct!))}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">
                        {fmtNum(goal.progress.current_value)} <span className="text-slate-600">of</span> {fmtNum(goal.target_value)}
                        <span className="text-slate-600"> ({pct!.toFixed(0)}%)</span>
                      </span>
                      <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-wide ${
                        onTrack ? "bg-emerald-500/10 text-emerald-300 border-emerald-400/30" : "bg-amber-500/10 text-amber-300 border-amber-400/30"
                      }`}>
                        {onTrack ? "On track" : "Behind"}
                      </span>
                    </div>
                  </>
                ) : (
                  <p className="text-slate-500 text-xs">Progress not available yet — connect YouTube and sync to start tracking.</p>
                )}

                <p className="text-slate-600 text-[11px]">
                  {remaining > 0 ? `${remaining} days left` : remaining === 0 ? "Due today" : "Past deadline"} · {goal.deadline}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
