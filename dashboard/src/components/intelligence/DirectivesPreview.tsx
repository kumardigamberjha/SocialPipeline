"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { DirectivesPreview as PreviewData, RULE_SCOPES, RuleScope, piApi } from "@/lib/personalIntelligenceApi";

export default function DirectivesPreview() {
  const [scope, setScope] = useState<RuleScope>("global");
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (s: RuleScope) => {
    setLoading(true);
    try {
      const data = await piApi.preview(s);
      setPreview(data);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load preview");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(scope);
  }, [scope, load]);

  const budgetPct = preview ? Math.min(100, (preview.char_count / (preview.rules_char_budget * 2.3)) * 100) : 0;

  return (
    <div className="space-y-4 py-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <p className="text-slate-500 text-xs max-w-lg">
          This is the exact text block prepended to every prompt for the selected surface — the
          same thing the model reads before your rules and goals are ever mentioned to it.
        </p>
        <div className="flex items-center gap-2">
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as RuleScope)}
            className="px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 focus:outline-none"
          >
            {RULE_SCOPES.map((s) => (
              <option key={s.value} value={s.value} className="bg-[#0f172a]">{s.label}</option>
            ))}
          </select>
          <button
            onClick={() => load(scope)}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="animate-spin text-slate-500" size={22} />
        </div>
      ) : preview ? (
        preview.directives ? (
          <div className="space-y-3">
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <span>{preview.rule_count} rule{preview.rule_count === 1 ? "" : "s"}</span>
              <span>{preview.goal_count} goal{preview.goal_count === 1 ? "" : "s"}</span>
              <span>{preview.char_count} characters</span>
              <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden max-w-[160px]">
                <div
                  className={`h-full rounded-full ${budgetPct > 90 ? "bg-amber-500" : "bg-violet-500"}`}
                  style={{ width: `${budgetPct}%` }}
                />
              </div>
            </div>
            <pre className="glass-card rounded-xl border border-white/10 bg-black/30 p-4 text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
              {preview.directives}
            </pre>
          </div>
        ) : (
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-12 text-center">
            <p className="text-slate-400 text-sm">Nothing to inject yet for this scope — add a rule or an active goal to see it here.</p>
          </div>
        )
      ) : null}
    </div>
  );
}
