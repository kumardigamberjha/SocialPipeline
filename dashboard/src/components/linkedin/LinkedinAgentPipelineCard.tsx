"use client";

import React from "react";
import {
  Sparkles,
  PenTool,
  CheckCircle2,
  ShieldCheck,
  Zap,
  ArrowRight,
  AlertTriangle,
  Cpu,
  Clock,
  Check,
} from "lucide-react";
import { PipelineHealth } from "@/lib/linkedinApi";

interface Props {
  pipelineHealth: PipelineHealth;
}

export default function LinkedinAgentPipelineCard({ pipelineHealth }: Props) {
  const steps = [
    {
      step: 1,
      name: "Hook Finder",
      tagline: "Angle & Hook Synthesis",
      desc: "Analyzes topic dynamics, finds 3 high-voltage angles (Contrarian, Step-by-Step, Story, Data, Framework).",
      icon: Sparkles,
      color: "from-blue-500/20 to-cyan-500/20 text-cyan-400 border-cyan-500/30",
      pill: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20",
      latency: "1.4s",
      success: "99.2%",
    },
    {
      step: 2,
      name: "Post Writer",
      tagline: "Single-Shot Anti-AI Draft",
      desc: "Strictly called once. Zero section loops. Writes with high-contrast cadence and punchy lineation.",
      icon: PenTool,
      color: "from-indigo-500/20 to-purple-500/20 text-indigo-400 border-indigo-500/30",
      pill: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20",
      latency: "2.8s",
      success: "98.5%",
    },
    {
      step: 3,
      name: "Python QA Checker",
      tagline: "Deterministic Rule Engine",
      desc: "Zero LLM hallucinations. Audits word count, banned words (delve, supercharge), line lengths & hashtags.",
      icon: ShieldCheck,
      color: "from-emerald-500/20 to-green-500/20 text-emerald-400 border-emerald-500/30",
      pill: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
      latency: "0.04s",
      success: "100%",
    },
    {
      step: 4,
      name: "Editor & Approver",
      tagline: "Targeted Fix & Sign-Off",
      desc: "Max 2 targeted rewrite cycles triggered only on QA violation. Accepts as-is or approves with confidence score.",
      icon: CheckCircle2,
      color: "from-amber-500/20 to-orange-500/20 text-amber-400 border-amber-500/30",
      pill: "bg-amber-500/10 text-amber-300 border-amber-500/20",
      latency: "1.9s",
      success: "96.8%",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* ── Visual 4-Agent Pipeline Topology ── */}
      <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400">
              <Cpu className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white tracking-wide">
                4-Agent Production Pipeline Architecture
              </h3>
              <p className="text-[11px] text-slate-400">
                Lean multi-agent orchestration with deterministic Python validation gates
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-mono font-medium text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Pipeline Online
            </span>
          </div>
        </div>

        {/* Pipeline Step Flow */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-5">
          {steps.map((s, idx) => {
            const Icon = s.icon;
            return (
              <div key={s.step} className="relative group">
                <div
                  className={`h-full flex flex-col justify-between rounded-xl border p-4 transition-all duration-200 bg-white/[0.02] hover:bg-white/[0.05] ${s.color}`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-white/10 text-[11px] font-mono font-bold text-white">
                          {s.step}
                        </span>
                        <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${s.pill}`}>
                          {s.name}
                        </span>
                      </div>
                      <Icon className="h-4.5 w-4.5" />
                    </div>
                    <h4 className="text-xs font-semibold text-white mb-1.5">{s.tagline}</h4>
                    <p className="text-[11px] text-slate-400 leading-relaxed mb-3">{s.desc}</p>
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-white/5 text-[10px] font-mono text-slate-400">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-slate-500" />
                      {s.latency}
                    </span>
                    <span className="text-emerald-400 font-semibold">{s.success} pass</span>
                  </div>
                </div>

                {/* Flow arrow on desktop */}
                {idx < steps.length - 1 && (
                  <div className="hidden md:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10 h-5 w-5 items-center justify-center rounded-full bg-slate-900 border border-white/20 text-slate-400">
                    <ArrowRight className="h-3 w-3" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Telemetry & Rules Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* QA Pass Rates & Cycles */}
        <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-amber-400" />
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Rewrite Cycle Distribution
            </h4>
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-slate-300 font-medium">Cycle 1 (First-Pass Clean)</span>
                <span className="font-mono font-bold text-emerald-400">
                  {pipelineHealth.cycle_1_pass_rate}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                  style={{ width: `${pipelineHealth.cycle_1_pass_rate}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500 mt-1">
                Post Writer drafted cleanly without requiring editor rewrite
              </p>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-slate-300 font-medium">Cycle 2 (Single Targeted Polish)</span>
                <span className="font-mono font-bold text-cyan-400">
                  {pipelineHealth.cycle_2_pass_rate}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-500"
                  style={{ width: `${pipelineHealth.cycle_2_pass_rate}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500 mt-1">
                Corrected line breaks, trimmed buzzwords, or adjusted word length
              </p>
            </div>

            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 flex items-center justify-between">
              <span className="text-xs text-slate-400">Average Cycles per Run</span>
              <span className="font-mono text-sm font-bold text-white">
                {pipelineHealth.avg_rewrite_cycles} cycles
              </span>
            </div>
          </div>
        </div>

        {/* Deterministic QA Rule Audits */}
        <div className="lg:col-span-2 rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Deterministic Anti-AI Quality Guardrails
              </h4>
            </div>
            <span className="text-[10px] font-mono text-slate-500">
              Enforced by Python Regex & Rule Gates
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {pipelineHealth.qa_rules_enforced.map((rule) => (
              <div
                key={rule.rule}
                className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 flex flex-col justify-between hover:border-white/10 transition-colors"
              >
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                      <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                      {rule.rule}
                    </span>
                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-mono font-medium text-emerald-400 border border-emerald-500/20">
                      {rule.violations_prevented} Caught
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    {rule.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
