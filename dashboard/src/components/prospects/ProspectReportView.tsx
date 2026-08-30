"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import AuditPanel from "@/components/prospects/AuditPanel";
import OutreachLine from "@/components/prospects/OutreachLine";
import RoadmapPanel from "@/components/prospects/RoadmapPanel";
import type { ProspectReport } from "@/lib/youtubeProspectsApi";

/**
 * The two screenshot panels plus the outreach line, shared by the in-dashboard
 * view and the bare shareable report route so the two can never diverge.
 */
export default function ProspectReportView({ report }: { report: ProspectReport }) {
  return (
    <div className="space-y-6">
      {report.tier?.grade === "internal_only" ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 flex items-center justify-between gap-4 print:hidden">
          <div className="flex items-center gap-3">
            <AlertTriangle size={18} className="text-amber-400 flex-shrink-0" />
            <div>
              <p className="text-xs font-semibold text-amber-200">
                Generated on fallback model ({report.tier?.name || report.model || "Fallback"}) · Internal Only
              </p>
              <p className="text-[11px] text-amber-200/80 mt-0.5">
                Client-facing PDF export and sharing are blocked until this audit is regenerated on a primary model.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <OutreachLine line={report.outreach_line} hooks={report.outreach_hooks} />

      {!report.duration_available ? (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 flex gap-3 print:hidden">
          <AlertTriangle size={18} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-amber-100/90 leading-relaxed">
            Only the most recent uploads could be read, without durations, so length-based analysis
            is omitted. Connect your Google account on the YouTube page for the full history.
          </p>
        </div>
      ) : null}

      <AuditPanel
        channel={report.channel}
        metrics={report.metrics}
        audit={report.audit}
        headline={report.headline}
        similarChannels={report.similar_channels}
      />
      <RoadmapPanel channel={report.channel} roadmap={report.roadmap} />
    </div>
  );
}
