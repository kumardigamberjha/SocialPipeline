"use client";

import React from "react";
import Link from "next/link";
import { Activity, Menu } from "lucide-react";
import { motion } from "framer-motion";

interface TopBarProps {
  onOpenSidebar: () => void;
  title?: string;
}

export default function TopBar({ onOpenSidebar, title }: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 flex h-14 w-full shrink-0 items-center justify-between border-b border-white/5 bg-slate-950/80 px-4 backdrop-blur-md md:hidden">
      {/* Left: Mobile menu trigger + branding */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenSidebar}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 glass-card text-slate-300 hover:bg-white/5 hover:text-white transition-colors"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link href="/" className="flex items-center gap-2">
          <motion.div
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-600 shadow-md shadow-blue-500/20"
            animate={{ rotate: [0, 4, -4, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
          >
            <Activity className="h-3.5 w-3.5 text-white" />
          </motion.div>
          <div className="flex items-center gap-1">
            <span className="text-xs font-bold uppercase tracking-wider text-white">
              Wings of AI
            </span>
            <span className="text-[10px] text-slate-600">//</span>
            <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-xs font-bold uppercase tracking-wider text-transparent">
              {title || "Nexus"}
            </span>
          </div>
        </Link>
      </div>

      {/* Right: Live indicator */}
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500 animate-pulse-green" />
        </span>
        <span className="text-[10px] font-mono tracking-wider text-green-400 uppercase">
          LIVE
        </span>
      </div>
    </header>
  );
}
