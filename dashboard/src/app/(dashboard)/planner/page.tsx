"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarRange, KanbanSquare } from "lucide-react";

import GoogleConnectCard from "@/components/planner/GoogleConnectCard";
import PlanBoard from "@/components/planner/PlanBoard";
import PlanDetail from "@/components/planner/PlanDetail";
import PlanList from "@/components/planner/PlanList";
import PlannerTabs from "@/components/planner/PlannerTabs";
import { PLATFORMS, Platform } from "@/lib/plannerApi";

type View = "list" | "board";

const isPlatform = (value: string | null): value is Platform =>
  PLATFORMS.some((p) => p.value === value);

function PlannerContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [openPlanId, setOpenPlanId] = useState<string | null>(null);

  // Platform and view live in the URL so they survive a reload and can be
  // linked to (e.g. the roadmap's "Open plan" link, or a bookmark).
  const platform: Platform = isPlatform(searchParams.get("platform"))
    ? (searchParams.get("platform") as Platform)
    : "youtube";
  const view: View = searchParams.get("view") === "board" ? "board" : "list";

  // Deep link support: /planner?plan={id} (used by calendar event descriptions).
  useEffect(() => {
    const planParam = searchParams.get("plan");
    if (planParam) setOpenPlanId(planParam);
  }, [searchParams]);

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString());
      next.set(key, value);
      next.delete("plan"); // switching context closes an open plan
      router.replace(`/planner?${next}`);
      setOpenPlanId(null);
    },
    [router, searchParams],
  );

  return (
    <div className="max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 space-y-6">
      <GoogleConnectCard />

      {!openPlanId && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
            Platform
            <select
              value={platform}
              onChange={(e) => setParam("platform", e.target.value)}
              className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50"
            >
              {PLATFORMS.map((p) => (
                <option key={p.value} value={p.value} className="bg-[#0f172a]">
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.02] p-0.5">
            {(
              [
                { value: "list", label: "Plans", Icon: CalendarRange },
                { value: "board", label: "Board", Icon: KanbanSquare },
              ] as const
            ).map(({ value, label, Icon }) => (
              <button
                key={value}
                onClick={() => setParam("view", value)}
                aria-pressed={view === value}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  view === value
                    ? "bg-blue-600/20 text-blue-200"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {openPlanId ? (
        <PlanDetail planId={openPlanId} onBack={() => setOpenPlanId(null)} />
      ) : view === "board" ? (
        <PlanBoard platform={platform} onOpenPlan={setOpenPlanId} />
      ) : (
        <PlanList platform={platform} onOpenPlan={setOpenPlanId} />
      )}
    </div>
  );
}

export default function PlannerPage() {
  return (
    <>
      <PlannerTabs />
      <Suspense
        fallback={
          <div className="py-20 text-center text-slate-500 text-sm">Loading planner…</div>
        }
      >
        <PlannerContent />
      </Suspense>
    </>
  );
}
