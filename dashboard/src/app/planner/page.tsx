"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Header from "@/components/Header";
import GoogleConnectCard from "@/components/planner/GoogleConnectCard";
import PlanDetail from "@/components/planner/PlanDetail";
import PlanList from "@/components/planner/PlanList";
import PlannerTabs from "@/components/planner/PlannerTabs";

function PlannerContent() {
  const searchParams = useSearchParams();
  const [openPlanId, setOpenPlanId] = useState<string | null>(null);

  // Deep link support: /planner?plan={id} (used by calendar event descriptions).
  useEffect(() => {
    const planParam = searchParams.get("plan");
    if (planParam) setOpenPlanId(planParam);
  }, [searchParams]);

  return (
    <div className="max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <GoogleConnectCard />
      {openPlanId ? (
        <PlanDetail planId={openPlanId} onBack={() => setOpenPlanId(null)} />
      ) : (
        <PlanList onOpenPlan={setOpenPlanId} />
      )}
    </div>
  );
}

export default function PlannerPage() {
  return (
    <main className="flex flex-col min-h-screen">
      <Header />
      <PlannerTabs />
      <Suspense fallback={<div className="py-20 text-center text-slate-500 text-sm">Loading planner…</div>}>
        <PlannerContent />
      </Suspense>
    </main>
  );
}
