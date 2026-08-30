"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Loader2, Printer } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import ProspectReportView from "@/components/prospects/ProspectReportView";
import {
  fmtDate,
  formatModelName,
  prospectsApi,
  type ProspectReport,
} from "@/lib/youtubeProspectsApi";

/**
 * The shareable report: two clean panels, no dashboard chrome.
 *
 * Everything outside the panels carries `print:hidden`, so Cmd/Ctrl-P produces
 * a PDF of just the audit and the plan — and the panels themselves screenshot
 * without a sidebar creeping into frame.
 */
export default function ProspectReportPage() {
  const params = useParams<{ channelId: string }>();
  const channelId = params?.channelId;

  const [report, setReport] = useState<ProspectReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!channelId) return;
    setLoading(true);
    setError(null);
    try {
      setReport(await prospectsApi.get(channelId, "share"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this report");
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 print:px-0 print:py-0 print:max-w-none">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6 print:hidden">
        <Link
          href="/prospects"
          className="flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft size={14} /> Back to prospects
        </Link>
        {report ? (
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">
              Generated {fmtDate(report.generated_at)}
            </span>
            <Link
              href={`/report/print/${channelId}`}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors"
            >
              <Printer size={13} /> Print-Ready Report (Light)
            </Link>
          </div>
        ) : null}
      </header>

      {error ? (
        <div className="rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Loader2 className="animate-spin text-slate-600" size={24} />
        </div>
      ) : report ? (
        <ProspectReportView report={report} />
      ) : null}
    </div>
  );
}

