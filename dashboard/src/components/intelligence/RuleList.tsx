"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import {
  RULE_CATEGORIES,
  RULE_SCOPES,
  Rule,
  RuleCategory,
  RuleScope,
  piApi,
} from "@/lib/personalIntelligenceApi";

const SCOPE_STYLE: Record<RuleScope, string> = {
  global: "bg-violet-500/10 text-violet-300 border-violet-400/30",
  youtube: "bg-red-500/10 text-red-300 border-red-400/30",
  blog: "bg-blue-500/10 text-blue-300 border-blue-400/30",
  linkedin: "bg-sky-500/10 text-sky-300 border-sky-400/30",
  instagram: "bg-pink-500/10 text-pink-300 border-pink-400/30",
};

export default function RuleList() {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [text, setText] = useState("");
  const [scope, setScope] = useState<RuleScope>("global");
  const [category, setCategory] = useState<RuleCategory>("behavior");

  const load = useCallback(async () => {
    try {
      const data = await piApi.listRules({ includeInactive: true });
      setRules(data);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load rules");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addRule = async () => {
    if (!text.trim()) return;
    setSaving(true);
    try {
      await piApi.createRule({ scope, category, rule_text: text.trim() });
      setText("");
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to add rule");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (rule: Rule) => {
    setRules((prev) => prev?.map((r) => (r.id === rule.id ? { ...r, is_active: !r.is_active } : r)) ?? null);
    try {
      await piApi.updateRule(rule.id, { is_active: !rule.is_active });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to update rule");
      load();
    }
  };

  const removeRule = async (ruleId: string) => {
    setRules((prev) => prev?.filter((r) => r.id !== ruleId) ?? null);
    try {
      await piApi.deleteRule(ruleId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete rule");
      load();
    }
  };

  if (rules === null) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="animate-spin text-slate-500" size={22} />
      </div>
    );
  }

  return (
    <div className="space-y-4 py-6">
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">{error}</div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-slate-500 text-xs">
          Active rules are followed by every analysis, plan and generated piece of content —
          global rules apply everywhere, scoped rules apply on top of them for one surface.
        </p>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 text-xs font-medium rounded-lg transition-colors border border-violet-500/20 flex-shrink-0 ml-4"
          >
            <Plus size={14} /> Add rule
          </button>
        )}
      </div>

      {showForm && (
        <div className="glass-card rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Always open with a specific statistic. Never use the word 'unlock'."
            rows={2}
            maxLength={400}
            className="w-full px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-violet-500/40 resize-none"
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as RuleScope)}
              className="px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 focus:outline-none"
            >
              {RULE_SCOPES.map((s) => (
                <option key={s.value} value={s.value} className="bg-[#0f172a]">{s.label}</option>
              ))}
            </select>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as RuleCategory)}
              className="px-2.5 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-300 focus:outline-none"
            >
              {RULE_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value} className="bg-[#0f172a]">{c.label}</option>
              ))}
            </select>
            <div className="flex-1" />
            <button
              onClick={() => { setShowForm(false); setText(""); }}
              className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={addRule}
              disabled={saving || !text.trim()}
              className="px-3.5 py-1.5 bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 text-xs font-medium rounded-lg transition-colors border border-violet-500/20 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save rule"}
            </button>
          </div>
        </div>
      )}

      {rules.length === 0 && !showForm ? (
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-12 text-center">
          <p className="text-slate-400 text-sm">No rules yet — add one to shape how every generation behaves.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl border transition-colors ${
                rule.is_active ? "border-white/10 bg-white/[0.02]" : "border-white/5 bg-white/[0.01] opacity-50"
              }`}
            >
              <button
                onClick={() => toggleActive(rule)}
                title={rule.is_active ? "Active — click to disable" : "Disabled — click to enable"}
                className={`mt-0.5 w-4 h-4 rounded-full border flex-shrink-0 transition-colors ${
                  rule.is_active ? "bg-violet-500 border-violet-500" : "border-slate-600"
                }`}
              />
              <div className="flex-1 min-w-0">
                <p className="text-slate-200 text-sm">{rule.rule_text}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${SCOPE_STYLE[rule.scope]}`}>
                    {RULE_SCOPES.find((s) => s.value === rule.scope)?.label ?? rule.scope}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-600/40 text-slate-500 uppercase tracking-wide">
                    {rule.category}
                  </span>
                </div>
              </div>
              <button
                onClick={() => removeRule(rule.id)}
                className="p-1.5 rounded-lg text-slate-600 hover:text-red-300 hover:bg-red-500/10 transition-colors flex-shrink-0"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
