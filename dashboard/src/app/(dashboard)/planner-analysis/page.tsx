"use client";

import PlannerAnalyticsDashboard from "@/components/planner/PlannerAnalyticsDashboard";
import PlannerTabs from "@/components/planner/PlannerTabs";

export default function PlannerAnalysisPage() {
  return (
    <>
      <PlannerTabs />
      <PlannerAnalyticsDashboard />
    </>
  );
}
