"use client";

import { useState } from "react";
import { BrainCircuit, Eye, ListChecks, Target } from "lucide-react";
import RuleList from "./RuleList";
import GoalList from "./GoalList";
import DirectivesPreview from "./DirectivesPreview";

type Tab = "rules" | "goals" | "preview";

export default function PersonalIntelligenceDashboard() {
  const [tab, setTab] = useState<Tab>("rules");

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
      <div className="flex items-center gap-3">
        <BrainCircuit className="text-violet-400" size={28} />
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Personal Intelligence</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Rules the model must follow and goals it should work toward — injected into every
            analysis, plan and piece of content it generates for you.
          </p>
        </div>
      </div>

      <div className="border-b border-white/5">
        <nav className="flex items-center gap-1 -mb-px">
          {([
            { key: "rules", label: "Rules", Icon: ListChecks },
            { key: "goals", label: "Goals", Icon: Target },
            { key: "preview", label: "What the model sees", Icon: Eye },
          ] as const).map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === key
                  ? "border-violet-500 text-violet-300"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/10"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "rules" && <RuleList />}
      {tab === "goals" && <GoalList />}
      {tab === "preview" && <DirectivesPreview />}
    </div>
  );
}
