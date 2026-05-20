"use client";

import { Activity, Radio, Users } from "lucide-react";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, HealthResponse } from "@/lib/api";

export default function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOnline, setIsOnline] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        console.log("Checking backend health...");
        const data = await api.getHealth();
        console.log("Health check success:", data);
        setHealth(data);
        setIsOnline(true);
      } catch (err) {
        console.error("Health check failed:", err);
        setIsOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="w-full border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
        {/* Left — Branding */}
        <div className="flex items-center gap-3">
          <motion.div
            className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center"
            animate={{ rotate: [0, 5, -5, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          >
            <Activity className="w-4 h-4 text-white" />
          </motion.div>
          <div>
            <h1 className="text-sm sm:text-base font-bold tracking-[0.2em] uppercase text-white">
              Wings of AI{" "}
              <span className="text-slate-500 mx-1">//</span>{" "}
              <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                Command Nexus
              </span>
            </h1>
            <p className="text-[10px] tracking-[0.3em] uppercase text-slate-600 hidden sm:block">
              Autonomous Agent Syndicate
            </p>
          </div>
        </div>

        {/* Right — Status Indicators */}
        <div className="flex items-center gap-4 sm:gap-6">
          {/* System Status */}
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isOnline ? "bg-green-400" : "bg-red-400"} opacity-75`}></span>
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isOnline ? "bg-green-500 animate-pulse-green" : "bg-red-500"}`}></span>
            </span>
            <span className={`text-xs font-medium tracking-wider uppercase ${isOnline ? "text-green-400" : "text-red-400"}`}>
              {isOnline ? "System Online" : "System Offline"}
            </span>
          </div>

          {/* Separator */}
          <div className="w-px h-5 bg-white/10 hidden sm:block" />

          {/* Active Agents */}
          <div className="flex items-center gap-2 glass-card rounded-full px-3 py-1.5 hidden sm:flex">
            <Users className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-xs font-mono text-blue-300">
              {health?.agents_available || 0} Agents Active
            </span>
          </div>

          {/* Radio pulse */}
          <motion.div
            className="flex items-center gap-1.5 hidden md:flex"
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <Radio className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-[10px] font-mono text-purple-400/70 tracking-wider">
              LIVE
            </span>
          </motion.div>
        </div>
      </div>
    </header>
  );
}
