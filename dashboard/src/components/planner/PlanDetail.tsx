"use client";

import { ArrowLeft, CalendarPlus, CheckCircle2, Clock, Filter, Layers, Loader2, PlayCircle, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  bucketLabels,
  bucketOf,
  INSTAGRAM_POST_TYPES,
  isVideoPlatform,
  PlanDetail as PlanDetailType,
  PlanItem,
  plannerApi,
  StatusBucket,
  VideoFormat,
} from "@/lib/plannerApi";
import ContentReviewModal from "./ContentReviewModal";
import PlanItemRow from "./PlanItemRow";

const PROVIDERS = ["nvidia", "groq", "ollama", "openai", "anthropic", "google"];
const POLL_MS = 4000;

// Filters work on coarse buckets, not raw statuses, so one set of chips serves
// both the YouTube video pipeline and the generic idea/scheduled/published board.
type FilterStatus = "all" | StatusBucket;

interface Props {
  planId: string;
  onBack: () => void;
}

/** Bucket key for items with no scheduled date. */
const UNDATED = "__undated__";

export default function PlanDetail({ planId, onBack }: Props) {
  const [plan, setPlan] = useState<PlanDetailType | null>(null);
  const [provider, setProvider] = useState("nvidia");
  const [reviewItem, setReviewItem] = useState<PlanItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [newTopic, setNewTopic] = useState("");
  const [newNotes, setNewNotes] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newPublish, setNewPublish] = useState("");
  const [newFormat, setNewFormat] = useState<VideoFormat>("full");
  const [newType, setNewType] = useState<string>("reel");

  // Only YouTube runs the video pipeline. Everything else uses the generic
  // idea/in_production/scheduled/published board and a post type.
  const isVideo = isVideoPlatform(plan?.platform ?? "youtube");
  const [bulkBusy, setBulkBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await plannerApi.getPlan(planId);
      setPlan(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plan");
      return null;
    }
  }, [planId]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is generating — the backend reconciles statuses on read.
  useEffect(() => {
    const anyGenerating = plan?.items.some((i) => i.contents?.some((c) => c.review_status === "generating"));
    if (anyGenerating && !pollRef.current) {
      pollRef.current = setInterval(load, POLL_MS);
    } else if (!anyGenerating && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [plan, load]);

  const addItem = async () => {
    if (!newTopic.trim() || !newDate) return;
    try {
      await plannerApi.addItem(planId, {
        topic: newTopic.trim(),
        scheduled_date: newDate,
        publish_date: newPublish || null,
        notes: newNotes.trim() || null,
        ...(isVideo ? { video_format: newFormat } : { meta: { type: newType } }),
      });
      setNewTopic("");
      setNewNotes("");
      setNewPublish("");
      setNewFormat("full");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add item");
    }
  };

  const addAllToCalendar = async () => {
    const pending = plan?.items.filter((i) => !i.gcal_event_id) ?? [];
    if (pending.length === 0) return;
    setBulkBusy(true);
    setError(null);
    let failed = 0;
    for (const item of pending) {
      try {
        // No time/duration override — the backend falls back to each item's
        // stored event_time / event_duration_minutes, then its own default.
        await plannerApi.addToCalendar(planId, item.id);
      } catch (err) {
        // 409 = already on the calendar; skip it quietly, count the rest.
        const msg = err instanceof Error ? err.message : "";
        if (!msg.toLowerCase().includes("already on the calendar")) failed += 1;
      }
    }
    await load();
    if (failed > 0) {
      setError(`Added ${pending.length - failed} of ${pending.length} topics to calendar; ${failed} failed.`);
    }
    setBulkBusy(false);
  };

  const deletePlan = async () => {
    if (!window.confirm("Delete this plan and all its items?")) return;
    try {
      await plannerApi.deletePlan(planId);
      onBack();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  if (!plan) {
    return (
      <div className="flex items-center justify-center gap-2 text-slate-500 py-20">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading plan…
      </div>
    );
  }

  const pendingCalendarCount = plan.items.filter((i) => !i.gcal_event_id).length;

  const totalCount = plan.items.length;
  const counts: Record<StatusBucket, number> = { todo: 0, in_production: 0, published: 0 };
  for (const item of plan.items) counts[bucketOf(item.production_status)] += 1;
  const labels = bucketLabels(plan.platform);

  const filteredItems =
    filterStatus === "all"
      ? plan.items
      : plan.items.filter((item) => bucketOf(item.production_status) === filterStatus);

  // Group items by scheduled date (already sorted by the backend).
  // Undated backlog ideas share one bucket; the backend sorts them last.
  const groups = new Map<string, PlanItem[]>();
  for (const item of filteredItems) {
    const key = item.scheduled_date ?? UNDATED;
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center gap-3 flex-wrap mb-6">
        <button onClick={onBack} className="p-2 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-[200px]">
          <h2 className="text-base font-bold text-white">{plan.name}</h2>
          <p className="text-xs text-slate-500 uppercase tracking-wider">
            {plan.plan_type} · {plan.start_date} → {plan.end_date} · {plan.niche}
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p} className="bg-slate-900">{p}</option>
            ))}
          </select>
        </label>
        <button
          onClick={addAllToCalendar}
          disabled={bulkBusy || pendingCalendarCount === 0}
          title={pendingCalendarCount === 0 ? "All topics are already on the calendar" : "Add every remaining topic to Google Calendar"}
          className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-300 hover:border-blue-400/40 hover:text-blue-300 transition-colors flex items-center gap-1.5 disabled:opacity-40 disabled:hover:border-white/10 disabled:hover:text-slate-300"
        >
          {bulkBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <CalendarPlus className="w-3 h-3" />}
          Add all to Calendar{pendingCalendarCount > 0 ? ` (${pendingCalendarCount})` : ""}
        </button>
        <button
          onClick={deletePlan}
          className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-500 hover:text-red-400 hover:border-red-400/30 transition-colors flex items-center gap-1.5"
        >
          <Trash2 className="w-3 h-3" /> Delete Plan
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-400 mb-4 border border-red-400/20 bg-red-500/5 rounded-lg px-3 py-2">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
        </p>
      )}

      {/* Pipeline Status Overview Bar & Filters */}
      <div className="mb-5 p-3 rounded-xl border border-white/10 bg-white/[0.02] flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-slate-400 flex items-center gap-1 mr-2 font-medium">
            <Filter className="w-3.5 h-3.5 text-slate-500" /> Filter:
          </span>
          
          <button
            onClick={() => setFilterStatus("all")}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
              filterStatus === "all"
                ? "bg-blue-600/20 border-blue-500/50 text-blue-200 font-semibold"
                : "border-white/10 text-slate-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Layers className="w-3 h-3" /> All ({totalCount})
          </button>

          {(
            [
              { bucket: "todo", Icon: Clock, idle: "border-white/10 text-slate-400 hover:text-white hover:bg-white/5", active: "bg-slate-700/40 border-slate-500/50 text-slate-200 font-semibold", tint: "text-slate-400" },
              { bucket: "in_production", Icon: PlayCircle, idle: "border-white/10 text-slate-400 hover:text-white hover:bg-white/5", active: "bg-purple-600/20 border-purple-500/50 text-purple-200 font-semibold", tint: "text-purple-400" },
              { bucket: "published", Icon: CheckCircle2, idle: "border-emerald-500/30 text-emerald-400/80 hover:text-emerald-300 hover:bg-emerald-500/10", active: "bg-emerald-500/25 border-emerald-400/60 text-emerald-200 font-bold shadow-[0_0_10px_rgba(16,185,129,0.15)]", tint: "text-emerald-400" },
            ] as const
          ).map(({ bucket, Icon, idle, active, tint }) => (
            <button
              key={bucket}
              onClick={() => setFilterStatus(bucket)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                filterStatus === bucket ? active : idle
              }`}
            >
              <Icon className={`w-3 h-3 ${tint}`} /> {labels[bucket]} ({counts[bucket]})
            </button>
          ))}
        </div>

        {counts.published > 0 && (
          <div className="text-[11px] text-emerald-400/90 font-medium flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> {counts.published} of {totalCount} {isVideoPlatform(plan.platform) ? "videos" : "posts"} live
          </div>
        )}
      </div>

      {/* Items grouped by date */}
      <div className="space-y-3">
        {[...groups.entries()].map(([date, items]) => (
          <div key={date} className="space-y-2">
            {items.map((item) => (
              <PlanItemRow
                key={item.id}
                planId={planId}
                item={item}
                provider={provider}
                onChanged={load}
                onReview={setReviewItem}
                onError={setError}
              />
            ))}
          </div>
        ))}
        {filteredItems.length === 0 && (
          <p className="text-sm text-slate-500 py-10 text-center border border-dashed border-white/10 rounded-xl">
            {filterStatus === "all"
              ? "This plan has no items yet — add a topic below."
              : `No items in "${labels[filterStatus]}".`}
          </p>
        )}
      </div>

      {/* Quick add */}
      <div className="mt-4 rounded-xl border border-white/5 bg-white/[0.02] p-3 space-y-2">
        <input
          value={newTopic}
          onChange={(e) => setNewTopic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addItem()}
          placeholder="Add another topic…"
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
        />
        <textarea
          value={newNotes}
          onChange={(e) => setNewNotes(e.target.value)}
          placeholder="Description (optional) — angle, key points, notes…"
          rows={2}
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-y"
        />
        <div className="flex gap-3 flex-wrap items-end">
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            Scheduled
            <input
              type="date"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
              className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
          </label>
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            Publish date
            <input
              type="date"
              value={newPublish}
              onChange={(e) => setNewPublish(e.target.value)}
              className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
          </label>
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            {isVideo ? "Video format" : "Post type"}
            {isVideo ? (
              <select
                value={newFormat}
                onChange={(e) => setNewFormat(e.target.value as VideoFormat)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
              >
                <option value="full" className="bg-slate-900">Full length</option>
                <option value="short" className="bg-slate-900">Short</option>
              </select>
            ) : (
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 capitalize"
              >
                {INSTAGRAM_POST_TYPES.map((t) => (
                  <option key={t} value={t} className="bg-slate-900 capitalize">{t}</option>
                ))}
              </select>
            )}
          </label>
          <div className="flex-1" />
          <button
            onClick={addItem}
            disabled={!newTopic.trim() || !newDate}
            className="text-xs px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
      </div>

      {reviewItem && (
        <ContentReviewModal
          planId={planId}
          item={reviewItem}
          onClose={() => setReviewItem(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}
