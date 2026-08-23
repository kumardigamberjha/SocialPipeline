"use client";

import { Loader2, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useState } from "react";
import {
  INSTAGRAM_POST_TYPES,
  PLATFORMS,
  isVideoPlatform,
  Platform,
  plannerApi,
  PlanDetail,
  PlanType,
  VideoFormat,
} from "@/lib/plannerApi";

interface DraftItem {
  topic: string;
  scheduled_date: string;
  topic_source: "ai" | "manual";
  notes: string;
  video_format: VideoFormat;
  /** Platform-specific extras — seeded from the AI suggestion, then editable. */
  meta: Record<string, unknown>;
}

interface Props {
  /** The plan's channel. Without it every plan was created as YouTube. */
  platform: Platform;
  onClose: () => void;
  onCreated: (plan: PlanDetail) => void;
}

const PROVIDERS = ["nvidia", "groq", "ollama", "openai", "anthropic", "google"];

export default function PlanWizard({ platform, onClose, onCreated }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  // Only YouTube runs the video pipeline; for everything else a short/full
  // toggle is noise, and Instagram wants a post type instead.
  const isVideo = isVideoPlatform(platform);
  const [name, setName] = useState("");
  const [planType, setPlanType] = useState<PlanType>("weekly");
  const [niche, setNiche] = useState("ai");
  const [startDate, setStartDate] = useState(today);
  const [provider, setProvider] = useState("nvidia");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suggest = async () => {
    setSuggesting(true);
    setError(null);
    try {
      const { topics } = await plannerApi.suggestTopics({
        plan_type: planType,
        niche,
        start_date: startDate,
        platform,
        provider,
      });
      setItems(
        topics.map((t) => ({
          topic: t.topic,
          scheduled_date: t.scheduled_date,
          topic_source: "ai" as const,
          // Seed the editable description with the AI's rationale so it is kept, not lost.
          notes: t.rationale ?? "",
          video_format: "full" as const,
          // Instagram's suggester returns type/caption/image_prompt here; these
          // were previously dropped on the floor.
          meta: t.meta ?? {},
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Topic suggestion failed");
    } finally {
      setSuggesting(false);
    }
  };

  const updateItem = (index: number, patch: Partial<DraftItem>) => {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const addRow = () => {
    setItems((prev) => [
      ...prev,
      {
        topic: "",
        scheduled_date: startDate,
        topic_source: "manual",
        notes: "",
        video_format: "full",
        meta: isVideo ? {} : { type: "reel" },
      },
    ]);
  };

  const removeRow = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const save = async () => {
    const valid = items.filter((i) => i.topic.trim());
    if (!name.trim()) {
      setError("Give the plan a name.");
      return;
    }
    if (valid.length === 0) {
      setError("Add at least one topic (or use Suggest with AI).");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const plan = await plannerApi.createPlan({
        name: name.trim(),
        plan_type: planType,
        niche,
        start_date: startDate,
        platform,
        items: valid.map((i) => ({
          topic: i.topic.trim(),
          scheduled_date: i.scheduled_date,
          topic_source: i.topic_source,
          notes: i.notes.trim() || null,
          // video_format only means something on the video pipeline.
          ...(isVideo ? { video_format: i.video_format } : {}),
          ...(Object.keys(i.meta).length ? { meta: i.meta } : {}),
        })),
      });
      onCreated(plan);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan creation failed");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-10 px-4">
      <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-bold uppercase tracking-[0.2em] text-white">
            New {PLATFORMS.find((p) => p.value === platform)?.label ?? platform} Plan
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Plan settings */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <label className="block sm:col-span-2">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">Plan name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. July video sprint"
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">Period</span>
            <select
              value={planType}
              onChange={(e) => setPlanType(e.target.value as PlanType)}
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50"
            >
              <option value="weekly" className="bg-slate-900">Weekly</option>
              <option value="monthly" className="bg-slate-900">Monthly</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">Start date</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">Niche</span>
            <input
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50"
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider text-slate-500">AI provider</span>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50"
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p} className="bg-slate-900">{p}</option>
              ))}
            </select>
          </label>
        </div>

        {/* Topic rows */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            Topics ({items.filter((i) => i.topic.trim()).length})
          </span>
          <div className="flex gap-2">
            <button
              onClick={suggest}
              disabled={suggesting}
              className="text-xs px-3 py-1.5 rounded-lg bg-purple-600/80 hover:bg-purple-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {suggesting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              {suggesting ? "Thinking…" : "Suggest with AI"}
            </button>
            <button
              onClick={addRow}
              className="text-xs px-3 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-white/30 transition-colors flex items-center gap-1.5"
            >
              <Plus className="w-3 h-3" /> Add topic
            </button>
          </div>
        </div>

        <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
          {items.length === 0 && (
            <p className="text-xs text-slate-600 py-6 text-center border border-dashed border-white/10 rounded-lg">
              No topics yet — use “Suggest with AI” or add them manually.
            </p>
          )}
          {items.map((item, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="flex-1 space-y-1.5">
                <input
                  value={item.topic}
                  onChange={(e) => updateItem(i, { topic: e.target.value, topic_source: item.topic_source })}
                  placeholder={isVideo ? "Video topic / working title" : "Post topic / working title"}
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
                />
                <textarea
                  value={item.notes}
                  onChange={(e) => updateItem(i, { notes: e.target.value })}
                  placeholder="Description (optional) — angle, key points, notes…"
                  rows={2}
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-y"
                />
              </div>
              <input
                type="date"
                value={item.scheduled_date}
                onChange={(e) => updateItem(i, { scheduled_date: e.target.value })}
                className="rounded-lg bg-white/5 border border-white/10 px-2 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
              />
              {isVideo ? (
                <select
                  value={item.video_format}
                  onChange={(e) => updateItem(i, { video_format: e.target.value as VideoFormat })}
                  title="Video format — short (<60s) or full length (7-9 min)"
                  className="rounded-lg bg-white/5 border border-white/10 px-2 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
                >
                  <option value="full" className="bg-slate-900">Full</option>
                  <option value="short" className="bg-slate-900">Short</option>
                </select>
              ) : (
                <select
                  value={(item.meta.type as string) ?? "reel"}
                  onChange={(e) => updateItem(i, { meta: { ...item.meta, type: e.target.value } })}
                  title="Post type"
                  className="rounded-lg bg-white/5 border border-white/10 px-2 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 capitalize"
                >
                  {INSTAGRAM_POST_TYPES.map((t) => (
                    <option key={t} value={t} className="bg-slate-900 capitalize">{t}</option>
                  ))}
                </select>
              )}
              <button onClick={() => removeRow(i)} className="p-2 text-slate-600 hover:text-red-400 transition-colors">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        {error && <p className="text-xs text-red-400 mt-3">{error}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="text-xs px-4 py-2 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="text-xs px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {saving && <Loader2 className="w-3 h-3 animate-spin" />} Create Plan
          </button>
        </div>
      </div>
    </div>
  );
}
