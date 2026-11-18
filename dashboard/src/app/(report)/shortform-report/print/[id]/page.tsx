"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Loader2, Printer } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { shortformApi, ShortFormAuditReport } from "@/lib/shortformProspectsApi";
import ShortFormPrintReportView from "@/components/prospects/ShortFormPrintReportView";

export default function ShortFormPrintPage() {
  const params = useParams<{ id: string }>();
  const reportId = params?.id;

  const [report, setReport] = useState<ShortFormAuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!reportId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await shortformApi.getReport(reportId);
      setReport(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this report");
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="min-h-screen bg-slate-950 text-white print:bg-white print:text-slate-950">
      {/* ── Print Action Bar (hidden when printing) ── */}
      <nav
        aria-label="Report Actions"
        className="sticky top-0 z-50 border-b border-white/10 bg-slate-900/90 backdrop-blur-md px-6 py-3.5 print:hidden shadow-lg"
      >
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          <Link
            href="/prospects"
            className="flex items-center gap-2 text-xs font-semibold text-slate-300 hover:text-white transition-colors"
          >
            <ArrowLeft size={14} /> Back to Prospects
          </Link>

          <div className="flex items-center gap-3">
            <button
              onClick={() => window.print()}
              disabled={!report || loading}
              className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold text-xs flex items-center gap-2 shadow-lg shadow-purple-600/30 transition-all cursor-pointer"
            >
              <Printer size={15} /> Print / Save as PDF
            </button>
          </div>
        </div>
      </nav>

      {/* ── Report Content ── */}
      <main>
        {loading ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
            <Loader2 size={32} className="animate-spin text-purple-400" />
            <p className="text-xs text-slate-400">Loading Short-Form Deliverable...</p>
          </div>
        ) : error ? (
          <div className="max-w-md mx-auto mt-20 p-6 rounded-2xl border border-red-500/30 bg-red-950/20 text-center">
            <p className="text-sm font-bold text-red-300 mb-2">{error}</p>
            <Link href="/prospects" className="text-xs text-slate-400 underline">
              Return to Prospects
            </Link>
          </div>
        ) : report ? (
          <ShortFormPrintReportView report={report} />
        ) : null}
      </main>
    </div>
  );
}
