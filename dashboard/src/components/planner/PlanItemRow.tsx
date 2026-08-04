"use client";

import { Calendar, CalendarCheck, Check, Eye, Loader2, Pencil, Trash2, X, Zap } from "lucide-react";
import { useState } from "react";
import {
  ContentType,
  GenerateType,
  PlanItem,
  PRODUCTION_STATUSES,
  plannerApi,
  ProductionStatus,
  VideoFormat,
} from "@/lib/plannerApi";

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

const DURATION_PRESETS = [15, 30, 45, 60, 90, 120, 180, 240];

function formatDuration(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`;
}

/** Duration selector: presets plus a "Custom…" numeric input (in minutes). */
function DurationPicker({ value, onChange }: { value: number; onChange: (m: number) => void }) {
  const [custom, setCustom] = useState(!DURATION_PRESETS.includes(value));
  const inputClass =
    "rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50";

  if (custom) {
    return (
      <span className="inline-flex items-center gap-1" title="Custom event length in minutes">
        <input
          type="number"
          min={5}
          max={1440}
          value={value}
          onChange={(e) => onChange(Math.max(5, Math.min(1440, Number(e.target.value) || 60)))}
          className={`w-16 ${inputClass}`}
        />
        <span className="text-[10px] text-slate-500">min</span>
        <button
          type="button"
          onClick={() => { setCustom(false); onChange(60); }}
          className="text-[10px] text-slate-500 hover:text-slate-300 px-1"
          title="Back to presets"
        >
          presets
        </button>
      </span>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => {
        if (e.target.value === "custom") { setCustom(true); return; }
        onChange(Number(e.target.value));
      }}
      title="Event length"
      className={inputClass}
    >
      {DURATION_PRESETS.map((m) => (
        <option key={m} value={m} className="bg-slate-900">{formatDuration(m)}</option>
      ))}
      <option value="custom" className="bg-slate-900">Custom…</option>
    </select>
  );
}

interface Props {
  planId: string;
  item: PlanItem;
  provider: string;
  onChanged: () => void;
  onReview: (item: PlanItem) => void;
  onError: (message: string) => void;
}

export default function PlanItemRow({ planId, item, provider, onChanged, onReview, onError }: Props) {
  const [generating, setGenerating] = useState<GenerateType | null>(null);
  const [calendarBusy, setCalendarBusy] = useState(false);
  const [calTime, setCalTime] = useState(item.event_time ?? "09:00");
  const [calDuration, setCalDuration] = useState(item.event_duration_minutes ?? 60);

  const [editing, setEditing] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editTopic, setEditTopic] = useState(item.topic);
  const [editNotes, setEditNotes] = useState(item.notes ?? "");
  const [editScheduled, setEditScheduled] = useState(item.scheduled_date);
  const [editPublish, setEditPublish] = useState(item.publish_date ?? "");
  const [editTime, setEditTime] = useState(item.event_time ?? "");
  const [editDuration, setEditDuration] = useState(item.event_duration_minutes ?? 60);
  const [editFormat, setEditFormat] = useState<VideoFormat>(item.video_format ?? "full");

  const startEdit = () => {
    setEditTopic(item.topic);
    setEditNotes(item.notes ?? "");
    setEditScheduled(item.scheduled_date);
    setEditPublish(item.publish_date ?? "");
    setEditTime(item.event_time ?? "");
    setEditDuration(item.event_duration_minutes ?? 60);
    setEditFormat(item.video_format ?? "full");
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!editTopic.trim() || !editScheduled) return;
    setSavingEdit(true);
    try {
      await plannerApi.updateItem(planId, item.id, {
        topic: editTopic.trim(),
        scheduled_date: editScheduled,
        publish_date: editPublish || null,
        event_time: editTime || null,
        event_duration_minutes: editDuration,
        notes: editNotes.trim(),
        video_format: editFormat,
      });
      setEditing(false);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSavingEdit(false);
    }
  };

  const setFormat = async (fmt: VideoFormat) => {
    try {
      await plannerApi.updateItem(planId, item.id, { video_format: fmt });
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Format update failed");
    }
  };

  // Latest content row per type (backend returns newest first).
  const latestByType = new Map<ContentType, PlanItem["contents"][number]>();
  for (const c of item.contents ?? []) {
    if (!latestByType.has(c.content_type)) latestByType.set(c.content_type, c);
  }
  const hasAnyContent = (item.contents ?? []).length > 0;

  const generate = async (type: GenerateType) => {
    setGenerating(type);
    try {
      await plannerApi.generateContent(planId, item.id, type, provider);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Generation dispatch failed");
    } finally {
      setGenerating(null);
    }
  };

  const setStatus = async (status: ProductionStatus) => {
    try {
      await plannerApi.updateItem(planId, item.id, { production_status: status });
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Status update failed");
    }
  };

  const remove = async () => {
    try {
      await plannerApi.deleteItem(planId, item.id);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const addToCalendar = async () => {
    setCalendarBusy(true);
    try {
      await plannerApi.addToCalendar(planId, item.id, calTime, calDuration);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Calendar add failed");
    } finally {
      setCalendarBusy(false);
    }
  };

  const fmtDate = (d: string) =>
    new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 hover:border-white/10 transition-colors">
      {editing ? (
        /* ── Edit form ── */
        <div className="space-y-2">
          <input
            value={editTopic}
            onChange={(e) => setEditTopic(e.target.value)}
            placeholder="Topic / working title"
            className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
          />
          <textarea
            value={editNotes}
            onChange={(e) => setEditNotes(e.target.value)}
            placeholder="Description (optional) — angle, key points, notes…"
            rows={2}
            className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-y"
          />
          <div className="flex gap-3 flex-wrap items-end">
            <label className="text-[10px] uppercase tracking-wider text-slate-500">
              Scheduled
              <input
                type="date"
                value={editScheduled}
                onChange={(e) => setEditScheduled(e.target.value)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
              />
            </label>
            <label className="text-[10px] uppercase tracking-wider text-slate-500">
              Publish date
              <input
                type="date"
                value={editPublish}
                onChange={(e) => setEditPublish(e.target.value)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
              />
            </label>
            <label className="text-[10px] uppercase tracking-wider text-slate-500">
              Reminder time
              <input
                type="time"
                value={editTime}
                onChange={(e) => setEditTime(e.target.value)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
              />
            </label>
            <label className="text-[10px] uppercase tracking-wider text-slate-500">
              Duration
              <span className="mt-1 block">
                <DurationPicker value={editDuration} onChange={setEditDuration} />
              </span>
            </label>
            <label className="text-[10px] uppercase tracking-wider text-slate-500">
              Video format
              <select
                value={editFormat}
                onChange={(e) => setEditFormat(e.target.value as VideoFormat)}
                className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
              >
                <option value="full" className="bg-slate-900">Full length</option>
                <option value="short" className="bg-slate-900">Short</option>
              </select>
            </label>
            <div className="flex-1" />
            <button
              onClick={() => setEditing(false)}
              className="text-xs px-3 py-1.5 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
            >
              <X className="w-3 h-3" /> Cancel
            </button>
            <button
              onClick={saveEdit}
              disabled={savingEdit || !editTopic.trim() || !editScheduled}
              className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {savingEdit ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Save
            </button>
          </div>
        </div>
      ) : (
        /* ── Read-only view ── */
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1 min-w-[220px]">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              {fmtDate(item.scheduled_date)}
              {item.publish_date && (
                <span className="text-blue-400/80"> · publishes {fmtDate(item.publish_date)}</span>
              )}
            </p>
            <button
              onClick={startEdit}
              className="text-sm text-white mt-0.5 text-left hover:text-blue-300 transition-colors"
              title="Click to edit"
            >
              {item.topic}
            </button>
            {item.notes && <p className="text-xs text-slate-500 mt-0.5">{item.notes}</p>}
          </div>

          {/* Video format */}
          <select
            value={item.video_format ?? "full"}
            onChange={(e) => setFormat(e.target.value as VideoFormat)}
            className="rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
            title="Video format — drives YouTube script length (short = <60s, full = 7-9 min)"
          >
            <option value="full" className="bg-slate-900">Full length</option>
            <option value="short" className="bg-slate-900">Short</option>
          </select>

          {/* Production status */}
          <select
            value={item.production_status}
            onChange={(e) => setStatus(e.target.value as ProductionStatus)}
            className="rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
            title="Production stage — script_generated is set automatically when a YouTube script completes"
          >
            {PRODUCTION_STATUSES.map((s) => (
              <option key={s.value} value={s.value} className="bg-slate-900">
                {s.label}
              </option>
            ))}
          </select>

          <button onClick={startEdit} className="p-1.5 text-slate-600 hover:text-blue-400 transition-colors" title="Edit item">
            <Pencil className="w-4 h-4" />
          </button>
          <button onClick={remove} className="p-1.5 text-slate-600 hover:text-red-400 transition-colors" title="Delete item">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Generation buttons + chips */}
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        {TYPE_LABELS.map(({ type, label }) => {
          const latest = latestByType.get(type);
          return (
            <button
              key={type}
              onClick={() => generate(type)}
              disabled={generating !== null || latest?.review_status === "generating"}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-blue-400/40 hover:text-blue-300 transition-colors flex items-center gap-1.5 disabled:opacity-50"
              title={`Generate ${label} content for this topic`}
            >
              {generating === type || latest?.review_status === "generating" ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : null}
              {label}
              {latest && (
                <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${CHIP_STYLES[latest.review_status]}`}>
                  {latest.review_status}
                </span>
              )}
            </button>
          );
        })}

        <button
          onClick={() => generate("all")}
          disabled={generating !== null}
          className="text-xs px-2.5 py-1.5 rounded-lg bg-purple-600/70 hover:bg-purple-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {generating === "all" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
          Generate All
        </button>

        <div className="flex-1" />

        {hasAnyContent && (
          <button
            onClick={() => onReview(item)}
            className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-white/30 transition-colors flex items-center gap-1.5"
          >
            <Eye className="w-3 h-3" /> Review
          </button>
        )}

        {item.gcal_event_id ? (
          <a
            href={item.gcal_event_link ?? "#"}
            target="_blank"
            rel="noreferrer"
            className="text-xs px-2.5 py-1.5 rounded-lg border border-green-400/30 text-green-400 flex items-center gap-1.5 hover:bg-green-500/10 transition-colors"
            title="Open the calendar event"
          >
            <CalendarCheck className="w-3 h-3" /> On Calendar{item.event_time ? ` · ${item.event_time}` : ""}
            {item.event_duration_minutes ? ` · ${formatDuration(item.event_duration_minutes)}` : ""}
          </a>
        ) : (
          <div className="flex items-center gap-1.5">
            <input
              type="time"
              value={calTime}
              onChange={(e) => setCalTime(e.target.value)}
              title="Time of day for the calendar reminder"
              className="rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
            <DurationPicker value={calDuration} onChange={setCalDuration} />
            <button
              onClick={addToCalendar}
              disabled={calendarBusy}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-blue-400/40 hover:text-blue-300 transition-colors flex items-center gap-1.5 disabled:opacity-40"
              title="Create a Google Calendar reminder on this item's date and time"
            >
              {calendarBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Calendar className="w-3 h-3" />}
              Add to Calendar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
