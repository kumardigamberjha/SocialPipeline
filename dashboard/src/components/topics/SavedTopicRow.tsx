"use client";

import { useState } from "react";
import { Loader2, Zap, Trash2, EyeOff, Lightbulb, Clock, CheckCircle2 } from "lucide-react";
import {
  savedTopicsApi,
  type ContentType,
  type GenerateType,
  type SavedTopic,
  type SavedTopicStatus,
} from "@/lib/savedTopicsApi";

const TYPE_LABELS: { type: ContentType; label: string }[] = [
  { type: "linkedin", label: "LinkedIn" },
  { type: "blog", label: "Blog" },
  { type: "youtube_script", label: "YouTube" },
];

const CHIP_STYLES: Record<string, string> = {
  generating: "bg-amber-500/10 text-amber-400 border-amber-400/30",
  ready: "bg-blue-500/10 text-blue-400 border-blue-400/30",
  approved: "bg-green-500/10 text-green-400 border-green-400/30",
  rejected: "bg-red-500/10 text-red-400 border-red-400/30",
  failed: "bg-red-500/10 text-red-400 border-red-400/30",
};

const STATUS_STYLES: Record<
  SavedTopicStatus,
  { card: string; badge: string; label: string; Icon: typeof Lightbulb }
> = {
  uncovered: {
    card: "border border-white/5 bg-white/[0.02] border-l-4 border-l-slate-500",
    badge: "bg-slate-500/10 text-slate-400 border-slate-400/30",
    label: "Uncovered",
    Icon: Lightbulb,
  },
  generating: {
    card: "border border-white/5 bg-white/[0.02] border-l-4 border-l-amber-500",
    badge: "bg-amber-500/10 text-amber-400 border-amber-400/30",
    label: "Generating",
    Icon: Clock,
  },
  generated: {
    card: "border border-white/5 bg-white/[0.02] border-l-4 border-l-emerald-500",
    badge: "bg-emerald-500/10 text-emerald-400 border-emerald-400/30",
    label: "Generated",
    Icon: CheckCircle2,
  },
};

interface Props {
  topic: SavedTopic;
  provider: string;
  onChanged: () => void;
  onError: (message: string) => void;
}

export default function SavedTopicRow({ topic, provider, onChanged, onError }: Props) {
  const [busy, setBusy] = useState<GenerateType | "dismiss" | "delete" | null>(null);
  const style = STATUS_STYLES[topic.status] ?? STATUS_STYLES.uncovered;
  const { Icon } = style;

  const latestByType = new Map(topic.runs.map((r) => [r.content_type, r]));

  const run = async (key: typeof busy, fn: () => Promise<unknown>, fallback: string) => {
    setBusy(key);
    try {
      await fn();
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : fallback);
    } finally {
      setBusy(null);
    }
  };

  const generate = (type: GenerateType) =>
    run(type, () => savedTopicsApi.generate(topic.id, type, provider), "Generation dispatch failed");

  return (
    <div className={`rounded-xl px-4 py-3.5 transition-all duration-200 ${style.card}`}>
      <div className="flex items-start gap-3">
        <Icon className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200 font-medium break-words">{topic.topic}</p>
          {topic.rationale && (
            <p className="text-xs text-slate-500 mt-1 break-words">{topic.rationale}</p>
          )}
        </div>
        <span
          className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0 ${style.badge}`}
        >
          {style.label}
        </span>
      </div>

      <div className="flex items-center gap-2 flex-wrap mt-3">
        {TYPE_LABELS.map(({ type, label }) => {
          const latest = latestByType.get(type);
          const running = busy === type || latest?.review_status === "generating";
          return (
            <button
              key={type}
              onClick={() => generate(type)}
              disabled={busy !== null || running}
              title={`Generate ${label} content for this topic`}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-blue-400/40 hover:text-blue-300 transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {running ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              {label}
              {latest && (
                <span
                  className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${CHIP_STYLES[latest.review_status]}`}
                >
                  {latest.review_status}
                </span>
              )}
            </button>
          );
        })}

        <button
          onClick={() => generate("all")}
          disabled={busy !== null}
          className="text-xs px-2.5 py-1.5 rounded-lg bg-purple-600/70 hover:bg-purple-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {busy === "all" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
          Generate All
        </button>

        <div className="flex-1" />

        {topic.status === "uncovered" && (
          <button
            onClick={() => run("dismiss", () => savedTopicsApi.dismiss(topic.id), "Dismiss failed")}
            disabled={busy !== null}
            title="Hide this topic without generating"
            className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {busy === "dismiss" ? <Loader2 className="w-3 h-3 animate-spin" /> : <EyeOff className="w-3 h-3" />}
            Dismiss
          </button>
        )}

        <button
          onClick={() => run("delete", () => savedTopicsApi.deleteTopic(topic.id), "Delete failed")}
          disabled={busy !== null}
          title="Delete this topic"
          className="text-xs p-1.5 rounded-lg border border-white/10 text-slate-500 hover:text-red-400 hover:border-red-400/30 transition-colors disabled:opacity-50"
        >
          {busy === "delete" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
        </button>
      </div>
    </div>
  );
}
