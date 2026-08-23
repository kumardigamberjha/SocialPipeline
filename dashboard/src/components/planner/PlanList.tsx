"use client";

import { CalendarRange, Loader2, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Plan, PlanDetail, Platform, plannerApi } from "@/lib/plannerApi";
import PlanWizard from "./PlanWizard";
import PendingIdeasQueue from "./PendingIdeasQueue";

interface Props {
  onOpenPlan: (planId: string) => void;
  platform: Platform;
}

export default function PlanList({ onOpenPlan, platform }: Props) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setPlans(null);
    try {
      setPlans(await plannerApi.listPlans(platform));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plans — is the backend running?");
      setPlans([]);
    }
  }, [platform]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreated = (plan: PlanDetail) => {
    setShowWizard(false);
    onOpenPlan(plan.id);
  };

  return (
    <div>
      {/* Pending Ideas Queue from YouTube Trends — a YouTube-only surface
          (youtube_playlist_items), so it stays hidden on other platforms. */}
      {platform === "youtube" && <PendingIdeasQueue />}

      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-bold uppercase tracking-[0.2em] text-white flex items-center gap-2">
          <CalendarRange className="w-4 h-4 text-blue-400" /> Content Plans
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setShowWizard(true)}
            className="text-xs px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors flex items-center gap-1.5"
          >
            <Plus className="w-3 h-3" /> New Custom Plan
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-400 mb-4">{error}</p>}

      {plans === null && (
        <div className="flex items-center justify-center gap-2 text-slate-500 py-16">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading plans…
        </div>
      )}

      {plans !== null && plans.length === 0 && !error && (
        <div className="text-center py-16 border border-dashed border-white/10 rounded-2xl">
          <p className="text-sm text-slate-500">No content plans for this platform yet.</p>
          <p className="text-xs text-slate-600 mt-1">Create a weekly or monthly plan and let AI suggest the topics.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {plans?.map((plan) => (
          <button
            key={plan.id}
            onClick={() => onOpenPlan(plan.id)}
            className="text-left rounded-xl border border-white/5 bg-white/[0.02] p-4 hover:border-blue-500/40 transition-colors"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-white truncate">{plan.name}</p>
              <span
                className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0 ${
                  plan.status === "active"
                    ? "text-green-400 border-green-400/30"
                    : "text-slate-500 border-white/10"
                }`}
              >
                {plan.status}
              </span>
            </div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500 mt-1">
              {plan.plan_type} · {plan.start_date} → {plan.end_date}
            </p>
            <p className="text-xs text-slate-400 mt-2">
              {plan.item_count ?? 0} topics · {plan.published_count ?? 0} published
            </p>
          </button>
        ))}
      </div>

      {showWizard && (
        <PlanWizard platform={platform} onClose={() => setShowWizard(false)} onCreated={onCreated} />
      )}
    </div>
  );
}
