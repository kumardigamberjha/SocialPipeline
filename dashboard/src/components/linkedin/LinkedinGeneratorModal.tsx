"use client";

import React, { useState } from "react";
import {
  X,
  Sparkles,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { linkedinApi } from "@/lib/linkedinApi";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const TOPIC_SUGGESTIONS = [
  "Why 90% of Multi-Agent Systems Fail in Production",
  "The 3-Second LinkedIn Hook Rule for B2B Founders",
  "Local-First LLMs vs Cloud APIs: The Data Sovereignty Reality",
  "How We Scaled Our AI Pipeline to 1,000 Verified Leads",
];

export default function LinkedinGeneratorModal({
  isOpen,
  onClose,
  onSuccess,
}: Props) {
  const [topic, setTopic] = useState("");
  const [niche, setNiche] = useState("ai");
  const [provider, setProvider] = useState("nvidia");
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    setStatusMessage("Starting 4-Agent Pipeline (Hook Finder ➔ Post Writer ➔ QA)...");

    try {
      const res = await linkedinApi.generatePost(topic.trim(), niche, provider);
      setRunId(res.run_id);
      setStatusMessage("Pipeline dispatched! The worker is executing QA checks and crafting your post.");
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 2500);
    } catch (err: any) {
      console.error("Generation error:", err);
      setStatusMessage(err?.detail || "Failed to dispatch pipeline. Please verify backend connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl rounded-2xl border border-white/15 bg-slate-900 p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                Generate LinkedIn Post
              </h3>
              <p className="text-[11px] text-slate-400">
                Dispatches the 4-agent pipeline with deterministic Python QA validation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleGenerate} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Topic or Strategic Angle
            </label>
            <textarea
              required
              rows={3}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Why vector databases need hybrid sparse-dense retrieval for high accuracy..."
              className="w-full rounded-xl border border-white/10 bg-slate-950/80 p-3 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Suggested Topic Chips */}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              Suggested High-Converting Angles
            </div>
            <div className="flex flex-wrap gap-1.5">
              {TOPIC_SUGGESTIONS.map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setTopic(t)}
                  className="rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1 text-[11px] text-slate-400 hover:border-blue-500/30 hover:bg-blue-500/10 hover:text-blue-300 transition-all text-left"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Target Niche
              </label>
              <select
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-slate-950/80 p-2.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
              >
                <option value="ai">AI & Machine Learning</option>
                <option value="saas">B2B SaaS Growth</option>
                <option value="engineering">Software Architecture</option>
                <option value="leadership">Tech Leadership & Scaling</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                AI Provider
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-slate-950/80 p-2.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none"
              >
                <option value="nvidia">NVIDIA (Fast Nemotron)</option>
                <option value="groq">Groq (Ultra-low Latency Llama)</option>
                <option value="ollama">Ollama (Local-First Instance)</option>
              </select>
            </div>
          </div>

          {statusMessage && (
            <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-3 text-xs text-blue-300 flex items-start gap-2">
              <Zap className="h-4 w-4 shrink-0 text-blue-400 mt-0.5" />
              <div>
                <p className="font-medium">{statusMessage}</p>
                {runId && (
                  <p className="font-mono text-[10px] text-blue-400/80 mt-0.5">
                    Run ID: {runId}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2.5 border-t border-white/10 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !topic.trim()}
              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 hover:from-blue-500 hover:to-indigo-500 transition-all disabled:opacity-50"
            >
              {loading ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {loading ? "Dispatching Pipeline..." : "Generate LinkedIn Post"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
