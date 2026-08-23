"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Lightbulb } from "lucide-react";
import { savedTopicsApi, type SavedTopic, type SavedTopicStatus } from "@/lib/savedTopicsApi";
import SavedTopicRow from "./SavedTopicRow";

const PROVIDERS = ["nvidia", "groq", "ollama", "openai", "anthropic", "google"];
const POLL_MS = 4000;

const FILTERS: { value: SavedTopicStatus | "all"; label: string }[] = [
  { value: "uncovered", label: "Uncovered" },
  { value: "generated", label: "Generated" },
  { value: "all", label: "All" },
];

export default function SavedTopicList() {
  // null = still loading, so the empty state never flashes first.
  const [topics, setTopics] = useState<SavedTopic[] | null>(null);
  const [filter, setFilter] = useState<SavedTopicStatus | "all">("uncovered");
  const [provider, setProvider] = useState("ollama");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setTopics(await savedTopicsApi.listTopics(filter === "all" ? undefined : filter));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load topics");
      setTopics([]);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll only while something is actually in flight, then stop.
  useEffect(() => {
    const inFlight = topics?.some((t) => t.status === "generating") ?? false;
    if (inFlight && !timer.current) {
      timer.current = setInterval(load, POLL_MS);
    } else if (!inFlight && timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
    return () => {
      if (timer.current) {
        clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [topics, load]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
      <div className="flex items-center gap-3 flex-wrap mb-5">
        <h1 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
          Topic Backlog
        </h1>
        <div className="flex-1" />

        <div className="flex items-center gap-1 rounded-lg border border-white/5 bg-white/[0.02] p-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
                filter === f.value
                  ? "bg-blue-600/20 text-blue-300 border border-blue-500/30"
                  : "text-slate-500 hover:text-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          title="LLM provider used when generating"
          className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-slate-300"
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p} className="bg-slate-900">
              {p}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p className="text-xs text-red-400 mb-4 border border-red-400/20 bg-red-500/5 rounded-lg px-3 py-2">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">
            dismiss
          </button>
        </p>
      )}

      {topics === null ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : topics.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 py-16 text-center">
          <Lightbulb className="w-6 h-6 text-slate-600 mx-auto mb-3" />
          <p className="text-sm text-slate-400">
            {filter === "generated" ? "Nothing generated from the backlog yet." : "No topics waiting."}
          </p>
          <p className="text-xs text-slate-600 mt-1">
            Run Auto-Research Magic on the Nexus page to fill this up.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {topics.map((t) => (
            <SavedTopicRow
              key={t.id}
              topic={t}
              provider={provider}
              onChanged={load}
              onError={setError}
            />
          ))}
        </div>
      )}
    </div>
  );
}
