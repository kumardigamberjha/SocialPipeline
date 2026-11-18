"use client";

import { Suspense } from "react";
import LinkedinAnalyticsDashboard from "@/components/linkedin/LinkedinAnalyticsDashboard";

export default function LinkedinAnalysisPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-96 text-slate-400 text-sm">
          <div className="flex flex-col items-center gap-2.5">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className="font-mono text-xs text-slate-500">
              Loading LinkedIn Analytics Engine...
            </span>
          </div>
        </div>
      }
    >
      <LinkedinAnalyticsDashboard />
    </Suspense>
  );
}
