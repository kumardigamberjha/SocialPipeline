"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

interface SidebarTooltipProps {
  label: string;
  subLabel?: string;
  shortcut?: string;
  isCollapsed: boolean;
  children: React.ReactNode;
  sideOffset?: number;
}

export default function SidebarTooltip({
  label,
  subLabel,
  shortcut,
  isCollapsed,
  children,
  sideOffset = 12,
}: SidebarTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  if (!isCollapsed) {
    return <>{children}</>;
  }

  return (
    <div
      className="relative flex items-center"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      <AnimatePresence>
        {isVisible && (
          <motion.div
            initial={{ opacity: 0, x: -6, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            style={{ left: `calc(100% + ${sideOffset}px)` }}
            className="absolute top-1/2 -translate-y-1/2 z-50 pointer-events-none flex items-center gap-2 rounded-lg border border-white/10 bg-slate-900/95 px-3 py-1.5 shadow-2xl backdrop-blur-md whitespace-nowrap"
          >
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-slate-100 tracking-wide">
                {label}
              </span>
              {subLabel && (
                <span className="text-[10px] text-slate-400 font-normal">
                  {subLabel}
                </span>
              )}
            </div>

            {shortcut && (
              <kbd className="rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                {shortcut}
              </kbd>
            )}

            {/* Small arrow indicator */}
            <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 rotate-45 border-l border-b border-white/10 bg-slate-900" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
