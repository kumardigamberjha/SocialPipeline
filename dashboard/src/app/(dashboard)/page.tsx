"use client";

import { useState, useCallback } from "react";
import AgentPipeline from "@/components/AgentPipeline";
import ApprovalQueue, { StreamedTask } from "@/components/ApprovalQueue";
import TelemetryLedger from "@/components/TelemetryLedger";
import UncoveredTopicsBanner from "@/components/topics/UncoveredTopicsBanner";

export default function Home() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [completedTasks, setCompletedTasks] = useState<string[]>([]);

  const handleTasksUpdate = useCallback((tasks: StreamedTask[]) => {
    const taskNames = tasks.map((t) => t.task);
    setCompletedTasks((prev) => {
      // Only update if the length changed to avoid redundant renders
      if (prev.length === taskNames.length) return prev;
      return taskNames;
    });
  }, []);

  return (
    <div className="flex-1 flex flex-col gap-8 sm:gap-10 overflow-hidden">
      {/* Backlog nudge: renders nothing unless uncovered topics exist */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
        <UncoveredTopicsBanner />
      </div>

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
  );
}
