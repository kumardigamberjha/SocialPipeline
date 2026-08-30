"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Sparkles } from "lucide-react";
import { api, type HealthResponse } from "@/lib/api";

export default function LlmCascadeBanner() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let mounted = true;

    const checkHealth = async () => {
      try {
        const data = await api.getHealth();
        if (mounted) setHealth(data);
      } catch {
        // Ignore health check failures
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (!health) return null;

  const isPrimaryExhausted =
    health.active_tier_index !== undefined &&
    health.active_tier_index !== null &&
    health.active_tier_index > 1;

  const isClientGradeUnavailable = health.client_grade_available === false;

  if (!isPrimaryExhausted && !isClientGradeUnavailable) return null;

  return (
    <div className="w-full bg-amber-500/10 border-b border-amber-500/20 px-4 py-2.5 text-xs text-amber-200 flex items-center justify-between gap-3 sticky top-0 z-20 backdrop-blur-md">
      <div className="flex items-center gap-2 max-w-5xl mx-auto w-full">
        <AlertTriangle size={15} className="text-amber-400 flex-shrink-0" />
        <div>
          <span className="font-semibold text-amber-300">
            {isClientGradeUnavailable
              ? "No Client-Grade AI Tier Available: "
              : "Primary AI Key (Gemini) Exhausted: "}
          </span>
          <span className="text-amber-200/90">
            {isClientGradeUnavailable
              ? "All primary keys have exhausted quota. Deliverables will be marked internal-only until quota resets."
              : `Running on fallback tier (${health.active_tier_name || "Fallback Model"}). Client-grade PDF exports will require regeneration once quota resets.`}
          </span>
        </div>
      </div>
    </div>
  );
}
