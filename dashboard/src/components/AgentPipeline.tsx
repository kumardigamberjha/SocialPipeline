"use client";

import { motion } from "framer-motion";
import {
  Search,
  PenTool,
  ShieldCheck,
  Send,
  ChevronRight,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type AgentStatus = "complete" | "active" | "idle";

interface AgentNode {
  name: string;
  role: string;
  icon: LucideIcon;
}

const ALL_AGENTS: AgentNode[] = [
  { name: "Trend Analysis", role: "Viral Discovery", icon: Search },
  { name: "Script Writing", role: "YouTube Scripts", icon: PenTool },
  { name: "SEO Optimization", role: "Meta & Tags", icon: ShieldCheck },
  { name: "Thumbnail Design", role: "CTR Visuais", icon: Send },
  { name: "Shorts Scripting", role: "Short Form", icon: PenTool },
  { name: "LinkedIn Content", role: "Professional", icon: PenTool },
  { name: "Twitter Thread", role: "Micro-blogging", icon: PenTool },
  { name: "Blog Article", role: "Long Form", icon: PenTool },
  { name: "Course Outline", role: "Education", icon: PenTool },
  { name: "Idea Generation", role: "Creative Strategy", icon: Search },
];

const statusConfig: Record<
  AgentStatus,
  {
    borderClass: string;
    iconColor: string;
    bgGlow: string;
    dotColor: string;
    label: string;
    labelColor: string;
  }
> = {
  complete: {
    borderClass: "border-green-500/50",
    iconColor: "text-green-400",
    bgGlow: "shadow-[0_0_20px_rgba(34,197,94,0.15)]",
    dotColor: "bg-green-500",
    label: "COMPLETE",
    labelColor: "text-green-400",
  },
  active: {
    borderClass: "border-blue-500/60",
    iconColor: "text-blue-400",
    bgGlow: "",
    dotColor: "bg-blue-500",
    label: "ACTIVE",
    labelColor: "text-blue-400",
  },
  idle: {
    borderClass: "border-white/10",
    iconColor: "text-slate-600",
    bgGlow: "",
    dotColor: "bg-slate-600",
    label: "IDLE",
    labelColor: "text-slate-500",
  },
};

export default function AgentPipeline({ 
  completedTasks = [],
  isProcessing = false
}: { 
  completedTasks?: string[];
  isProcessing?: boolean;
}) {
  // Determine status of each agent
  const currentAgents = ALL_AGENTS.map((agent, idx) => {
    let status: AgentStatus = "idle";
    
    // Check if it's in the completed list passed from WebSocket
    if (completedTasks.includes(agent.name)) {
      status = "complete";
    } else if (isProcessing) {
      // It's the first one that is NOT complete
      const isNextActive = !completedTasks.includes(agent.name) && 
        (idx === 0 || completedTasks.includes(ALL_AGENTS[idx - 1].name));
      if (isNextActive) {
        status = "active";
      }
    }

    return { ...agent, status };
  });

  return (
    <section className="w-full">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="flex items-center gap-2 mb-6">
          <div className="w-1 h-4 bg-gradient-to-b from-blue-500 to-purple-500 rounded-full" />
          <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
            Agent Pipeline
          </h2>
          <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
        </div>

        {/* Pipeline row */}
        <div className="flex overflow-x-auto custom-scrollbar pb-4 items-center gap-2 sm:gap-0">
          {currentAgents.map((agent, index) => {
            const config = statusConfig[agent.status];
            const Icon = agent.icon;
            const isActive = agent.status === "active";

            return (
              <div
                key={agent.name}
                className="flex items-center shrink-0 w-44 lg:w-52"
              >
                {/* Agent Card */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05, duration: 0.3 }}
                  className={`
                    relative flex-1 
                    glass-card rounded-xl p-4 border-2 transition-all
                    ${config.borderClass} ${config.bgGlow}
                    ${isActive ? "animate-pulse-blue" : ""}
                  `}
                >
                  {/* Active scanning line effect */}
                  {isActive && (
                    <div className="absolute inset-0 overflow-hidden rounded-xl pointer-events-none">
                      <motion.div
                        className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-blue-400/40 to-transparent"
                        animate={{ top: ["0%", "100%"] }}
                        transition={{
                          duration: 2,
                          repeat: Infinity,
                          ease: "linear",
                        }}
                      />
                    </div>
                  )}

                  {/* Icon + Status Dot */}
                  <div className="flex items-center justify-between mb-3">
                    <div
                      className={`
                      w-9 h-9 rounded-lg flex items-center justify-center
                      ${agent.status === "complete" ? "bg-green-500/10" : ""}
                      ${agent.status === "active" ? "bg-blue-500/10" : ""}
                      ${agent.status === "idle" ? "bg-white/5" : ""}
                    `}
                    >
                      <Icon className={`w-4 h-4 ${config.iconColor}`} />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${config.dotColor} ${isActive ? "animate-pulse" : ""}`}
                      />
                      <span
                        className={`text-[9px] font-bold tracking-[0.15em] uppercase ${config.labelColor}`}
                      >
                        {config.label}
                      </span>
                    </div>
                  </div>

                  {/* Name + Role */}
                  <h3
                    className={`text-sm font-semibold truncate ${agent.status === "idle" ? "text-slate-500" : "text-white"}`}
                  >
                    {agent.name}
                  </h3>
                  <p className="text-[10px] text-slate-500 mt-0.5 tracking-wide truncate">
                    {agent.role}
                  </p>

                  {/* Progress bar for active */}
                  {isActive && (
                    <div className="mt-3 h-0.5 bg-white/5 rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full"
                        animate={{ width: ["20%", "70%", "45%", "85%"] }}
                        transition={{
                          duration: 4,
                          repeat: Infinity,
                          ease: "easeInOut",
                        }}
                      />
                    </div>
                  )}
                </motion.div>

                {/* Arrow connector */}
                {index < ALL_AGENTS.length - 1 && (
                  <div className="flex items-center justify-center w-8 sm:w-10">
                    <div className="relative flex items-center">
                      <div
                        className={`
                        w-4 lg:w-6 h-px
                        ${agent.status === "complete" ? "bg-green-500/40" : "bg-white/10"}
                      `}
                      />
                      <ChevronRight
                        className={`w-4 h-4 ${
                          agent.status === "complete" ? "text-green-500/60" : "text-white/20"
                        }`}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
