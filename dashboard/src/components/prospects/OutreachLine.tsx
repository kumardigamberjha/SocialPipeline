"use client";

import React, { useState } from "react";
import { Check, Copy, Flame, Info, MessageSquareQuote, Sparkles, Timer, Video } from "lucide-react";
import type { OutreachHooks } from "@/lib/youtubeProspectsApi";

/**
 * Copy-ready outreach openers with multi-angle hooks (Duration, Breakout Topic, Cadence, Timing).
 */
export default function OutreachLine({
  line,
  hooks,
}: {
  line: string;
  hooks?: OutreachHooks;
}) {
  const availableHooks: Array<{ id: string; label: string; text: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = [];

  const primaryText = line || hooks?.primary || "";
  if (primaryText) {
    availableHooks.push({ id: "primary", label: "Recommended Hook", text: primaryText, icon: Sparkles });
  }
  if (hooks?.duration_hook && hooks.duration_hook !== primaryText) {
    availableHooks.push({ id: "duration", label: "Video Length Hook", text: hooks.duration_hook, icon: Video });
  }
  if (hooks?.breakout_hook && hooks.breakout_hook !== primaryText) {
    availableHooks.push({ id: "breakout", label: "Breakout Video Hook", text: hooks.breakout_hook, icon: Flame });
  }
  if (hooks?.timing_hook && hooks.timing_hook !== primaryText) {
    availableHooks.push({ id: "timing", label: "Timing Hook", text: hooks.timing_hook, icon: Timer });
  }
  if (hooks?.cadence_hook && hooks.cadence_hook !== primaryText) {
    availableHooks.push({ id: "cadence", label: "Publishing Cadence Hook", text: hooks.cadence_hook, icon: Timer });
  }

  const [activeTab, setActiveTab] = useState<string>(availableHooks[0]?.id || "primary");
  const [copied, setCopied] = useState(false);

  const currentText =
    availableHooks.find((h) => h.id === activeTab)?.text || primaryText;

  const copy = async () => {
    if (!currentText) return;
    try {
      await navigator.clipboard.writeText(currentText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  if (!primaryText && availableHooks.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#0b1120] p-5 flex gap-3 print:hidden">
        <Info size={18} className="text-slate-500 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm text-slate-300 font-medium">No outreach hook generated</p>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            This channel&apos;s videos perform too evenly for an honest standout comparison. The
            audit and plan below still apply — write your own opener rather than quoting a
            difference the numbers don&apos;t support.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-blue-500/25 bg-blue-500/[0.06] p-5 print:hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-300">
            <MessageSquareQuote size={14} /> Outreach opener
          </p>
          {availableHooks.length > 1 && (
            <div className="flex items-center gap-1 bg-black/30 p-0.5 rounded-lg border border-white/5">
              {availableHooks.map((h) => {
                const Icon = h.icon;
                const isActive = activeTab === h.id;
                return (
                  <button
                    key={h.id}
                    onClick={() => setActiveTab(h.id)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
                      isActive
                        ? "bg-blue-600/30 text-blue-200 border border-blue-400/30 shadow-sm"
                        : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
                    }`}
                  >
                    <Icon size={12} className={isActive ? "text-blue-300" : "text-slate-500"} />
                    {h.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <button
          onClick={copy}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600/20 text-blue-200 border border-blue-500/30 hover:bg-blue-600/30 transition-colors shadow-sm"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          {copied ? "Copied to clipboard" : "Copy opener"}
        </button>
      </div>

      <p className="text-sm text-slate-100 leading-relaxed font-medium bg-black/20 p-3.5 rounded-xl border border-white/5">
        {currentText}
      </p>

      <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2.5">
        <span>
          Every figure here is measured from public uploads, not hallucinated — 100% safe to send to creators.
        </span>
        {activeTab !== "primary" && (
          <button
            onClick={() => setActiveTab("primary")}
            className="text-blue-400 hover:underline"
          >
            Reset to default
          </button>
        )}
      </div>
    </div>
  );
}

