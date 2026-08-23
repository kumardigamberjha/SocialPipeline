"use client";

/**
 * Staged waiting copy.
 *
 * The backend cannot stream: `crewai.LLM.call` is blocking and returns a whole
 * string, so there is no token-level progress to show. What matters instead is
 * that the wait stays explained — cascading to a slower provider genuinely takes
 * 30-60 seconds, and unexplained silence that long reads as a hang.
 */

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

const STAGES: { at: number; text: string }[] = [
  { at: 0, text: "Reading your question…" },
  { at: 2500, text: "Looking through your planner…" },
  { at: 7000, text: "Writing your answer…" },
  { at: 25000, text: "Still working — the AI is on a slower provider…" },
];

export default function ThinkingIndicator() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timers = STAGES.slice(1).map((s, i) =>
      setTimeout(() => setStage(i + 1), s.at),
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="flex items-center gap-2 px-1 py-2 text-xs text-slate-500">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span>{STAGES[stage].text}</span>
    </div>
  );
}
