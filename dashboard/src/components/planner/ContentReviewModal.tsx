"use client";

import { CheckCircle2, Loader2, RefreshCw, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ContentDetail, ContentType, PlanItem, plannerApi } from "@/lib/plannerApi";

const TYPE_LABELS: Record<ContentType, string> = {
  linkedin: "LinkedIn Post",
  blog: "Blog",
  youtube_script: "YouTube Script",
};

const STATUS_STYLES: Record<string, string> = {
  generating: "text-amber-400 border-amber-400/30",
  ready: "text-blue-400 border-blue-400/30",
  approved: "text-green-400 border-green-400/30",
  rejected: "text-red-400 border-red-400/30",
  failed: "text-red-400 border-red-400/30",
};

interface Props {
  planId: string;
  item: PlanItem;
  onClose: () => void;
  onChanged: () => void; // parent refetches the plan
}

export default function ContentReviewModal({ planId, item, onClose, onChanged }: Props) {
  const [contents, setContents] = useState<ContentDetail[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await plannerApi.getItemContent(planId, item.id);
      setContents(data);
      setActiveId((prev) => prev && data.some((c) => c.id === prev) ? prev : data[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load content");
    } finally {
      setLoading(false);
    }
  }, [planId, item.id]);

  useEffect(() => {
    load();
  }, [load]);

  const active = contents.find((c) => c.id === activeId) ?? null;

  const review = async (action: "approve" | "reject", regenerate = false) => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await plannerApi.reviewContent(active.id, action, regenerate);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-8 px-4">
      <div className="w-full max-w-3xl rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
        <div className="flex items-start justify-between mb-4 gap-4">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-[0.2em] text-white">Review Content</h2>
            <p className="text-xs text-slate-500 mt-1">{item.topic}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs — newest per content type first (backend orders newest-first) */}
        <div className="flex gap-2 flex-wrap mb-4">
          {contents.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                c.id === activeId
                  ? "border-blue-500/60 bg-blue-500/10 text-white"
                  : "border-white/10 text-slate-400 hover:border-white/30"
              }`}
            >
              {TYPE_LABELS[c.content_type]}
              <span className={`ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${STATUS_STYLES[c.review_status]}`}>
                {c.review_status}
              </span>
            </button>
          ))}
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-10 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading content…
          </div>
        )}

        {!loading && contents.length === 0 && (
          <p className="text-sm text-slate-500 py-10 text-center">Nothing generated for this item yet.</p>
        )}

        {active && (
          <>
            {active.review_status === "generating" && (
              <p className="text-sm text-amber-400 py-8 text-center flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Still generating — check back shortly.
              </p>
            )}
            {active.review_status === "failed" && (
              <p className="text-sm text-red-400 py-8 text-center">Generation failed. You can dispatch a fresh run from the plan row.</p>
            )}
            {active.body && (
              <div className="rounded-xl border border-white/5 bg-black/30 p-4 max-h-[50vh] overflow-y-auto">
                {active.title && <h3 className="text-base font-semibold text-white mb-3">{active.title}</h3>}
                <div className="prose prose-invert prose-sm max-w-none prose-headings:text-slate-200 prose-p:text-slate-300 whitespace-pre-wrap">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{active.body}</ReactMarkdown>
                </div>
              </div>
            )}

            {error && <p className="text-xs text-red-400 mt-3">{error}</p>}

            {(active.review_status === "ready" || active.review_status === "approved" || active.review_status === "rejected") && (
              <div className="flex justify-end gap-2 mt-4 flex-wrap">
                {active.review_status === "approved" && (
                  <span className="text-xs text-green-400 flex items-center gap-1.5 mr-auto">
                    <CheckCircle2 className="w-4 h-4" /> Approved
                  </span>
                )}
                <button
                  onClick={() => review("reject", true)}
                  disabled={busy}
                  className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-300 hover:border-amber-400/40 hover:text-amber-400 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  <RefreshCw className="w-3 h-3" /> Reject & Regenerate
                </button>
                <button
                  onClick={() => review("reject")}
                  disabled={busy || active.review_status === "rejected"}
                  className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-300 hover:border-red-400/40 hover:text-red-400 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  <ThumbsDown className="w-3 h-3" /> Reject
                </button>
                <button
                  onClick={() => review("approve")}
                  disabled={busy || active.review_status === "approved"}
                  className="text-xs px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3 h-3" />} Approve
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
