"use client";

import React from "react";
import Header from "@/components/Header";
import PlannerTabs from "@/components/planner/PlannerTabs";
import PlannerAnalyticsDashboard from "@/components/planner/PlannerAnalyticsDashboard";

export default function PlannerAnalysisPage() {
  return (
    <main className="flex flex-col min-h-screen">
      <Header />
      <PlannerTabs />
      <div className="flex-1 flex flex-col py-8 sm:py-10">
        <PlannerAnalyticsDashboard />
      </div>
      <footer className="border-t border-white/5 py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <span className="text-[10px] text-slate-600 tracking-[0.2em] uppercase">
            Wings of AI © 2026
          </span>
          <span className="text-[10px] text-slate-700 font-mono">v1.0.0-nexus</span>
        </div>
      </footer>
    </main>
  );
}
