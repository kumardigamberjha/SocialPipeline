"use client";

import { Activity, Radio, Users } from "lucide-react";
import { motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, HealthResponse } from "@/lib/api";

const NAV_LINKS = [
  { href: "/", label: "Nexus" },
  { href: "/topics", label: "Topics" },
  { href: "/planner", label: "Planner" },
  { href: "/youtube-analysis", label: "YouTube" },
  { href: "/instagram-analysis", label: "Instagram" },
];

export default function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isOnline, setIsOnline] = useState(false);
  const pathname = usePathname();

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

        {/* Center — Navigation */}
        <nav className="flex items-center gap-1 rounded-lg border border-white/5 bg-white/[0.02] p-1">
          {NAV_LINKS.map(({ href, label }) => {
            // "/planner" stays active on its sub-pages (e.g. /planner-analysis).
            const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`text-xs px-3 py-1.5 rounded-md uppercase tracking-wider transition-colors ${
                  isActive
                    ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                    : "text-slate-500 hover:text-slate-200"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>

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

          {/* Separator */}
          <div className="w-px h-5 bg-white/10 hidden sm:block" />

          {/* Instagram Social Link */}
          <a
            href="https://instagram.com/codingindiaai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass-card hover:bg-gradient-to-r hover:from-purple-600/30 hover:to-pink-600/30 border border-pink-500/20 text-xs font-mono text-pink-300 hover:text-pink-200 transition-all shadow-[0_0_12px_rgba(236,72,153,0.15)] group"
            title="Follow Coding India AI on Instagram"
          >
            <svg className="w-3.5 h-3.5 text-pink-400 group-hover:scale-110 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="20" height="20" x="2" y="2" rx="5" ry="5"/>
              <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/>
              <line x1="17.5" x2="17.51" y1="6.5" y2="6.5"/>
            </svg>
            <span className="hidden sm:inline font-semibold">@codingindiaai</span>
          </a>
        </div>
      </div>
    </header>
  );
}
