"use client";

import { useState, useCallback } from "react";
import Header from "@/components/Header";
import AgentPipeline from "@/components/AgentPipeline";
import ApprovalQueue, { StreamedTask } from "@/components/ApprovalQueue";
import TelemetryLedger from "@/components/TelemetryLedger";

export default function Home() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [completedTasks, setCompletedTasks] = useState<string[]>([]);

  const handleTasksUpdate = useCallback((tasks: StreamedTask[]) => {
    const taskNames = tasks.map(t => t.task);
    setCompletedTasks(prev => {
      // Only update if the length changed to avoid redundant renders
      if (prev.length === taskNames.length) return prev;
      return taskNames;
    });
  }, []);

  return (
    <main className="flex flex-col min-h-screen">
      {/* ── Header ── */}
      <Header />

      {/* ── Content ── */}
      <div className="flex-1 flex flex-col gap-8 sm:gap-10 py-8 sm:py-10 overflow-hidden">
        {/* Section 1: Agent Pipeline */}
        <AgentPipeline isProcessing={isGenerating} completedTasks={completedTasks} />

        {/* Section 2: Approval Queue */}
        <ApprovalQueue 
          onGeneratingChange={setIsGenerating} 
          onTasksUpdate={handleTasksUpdate}
        />

        {/* Section 3: Telemetry Ledger */}
        <TelemetryLedger />
      </div>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <span className="text-[10px] text-slate-600 tracking-[0.2em] uppercase">
            Wings of AI © 2026
          </span>
          <span className="text-[10px] text-slate-700 font-mono">
            v1.0.0-nexus
          </span>
        </div>
      </footer>
    </main>
  );
}
