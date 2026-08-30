"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, Loader2, Printer } from "lucide-react";
import { API_BASE_URL } from "@/lib/config";
import { ApiError } from "@/lib/apiClient";
import ProspectPrintReportView from "@/components/prospects/ProspectPrintReportView";
import {
  fmtDate,
  formatModelName,
  prospectsApi,
  type ProspectReport,
} from "@/lib/youtubeProspectsApi";

export default function PrintReportPage() {
  const params = useParams<{ channelId: string }>();
  const channelId = params?.channelId;

  const [report, setReport] = useState<ProspectReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!channelId) return;
    setLoading(true);
    setError(null);
    try {
      setReport(await prospectsApi.get(channelId, "print"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this report");
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDownloadServerPdf = async () => {
    if (!channelId) return;
    setDownloadingPdf(true);
    try {
      const response = await fetch(`${API_BASE_URL}/youtube-prospects/${channelId}/pdf`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Failed to generate PDF (${response.status})`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cleanTitle = (report?.channel?.title || "Channel").replace(/[^a-zA-Z0-9_-]/g, "_");
      a.download = `Growth_Intelligence_Audit_${cleanTitle}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      alert(`Could not download server PDF: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setDownloadingPdf(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 py-8 px-4 sm:px-6 print:bg-white print:p-0">
      <style jsx global>{`
        @media print {
          @page {
            size: A4 portrait;
            margin: 8mm 10mm;
          }
          body {
            background-color: #ffffff !important;
            color: #0f172a !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .print-page {
            page-break-after: always !important;
            break-after: page !important;
            min-height: 270mm !important;
            padding: 0 !important;
            border: none !important;
            margin: 0 !important;
          }
          .page-break-before {
            page-break-before: always !important;
            break-before: page !important;
          }
        }
      `}</style>

      {/* Floating Action Controls (hidden in print) */}
      <div className="max-w-[210mm] mx-auto mb-6 flex flex-wrap items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-sm print:hidden">
        <div className="flex items-center gap-3">
          <Link
            href={`/prospect-report/${channelId}`}
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Web Report
          </Link>
          {report ? (
            <span className="text-xs text-slate-500">
              {report.channel.title} · Generated {fmtDate(report.generated_at)}
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 transition-colors cursor-pointer"
          >
            <Printer size={14} /> Print / Browser PDF
          </button>
          <button
            onClick={handleDownloadServerPdf}
            disabled={downloadingPdf}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-purple-600 text-white hover:bg-purple-700 shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {downloadingPdf ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
            Download PDF
          </button>
        </div>
      </div>

      {/* Document View */}
      <div className="max-w-[210mm] mx-auto print:max-w-none shadow-md print:shadow-none">
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : loading ? (
          <div className="flex flex-col items-center justify-center py-32 bg-white rounded-xl border border-slate-200">
            <Loader2 className="animate-spin text-purple-600 mb-3" size={28} />
            <p className="text-sm font-medium text-slate-600">Formatting print-ready report…</p>
          </div>
        ) : report ? (
          <ProspectPrintReportView report={report} />
        ) : null}
      </div>
    </div>
  );
}
