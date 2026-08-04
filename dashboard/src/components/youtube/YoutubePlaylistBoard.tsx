"use client";

import React, { useEffect, useState } from "react";
import {
  ListVideo,
  RefreshCw,
  ChevronDown,
  PlugZap,
  AlertTriangle,
  ClipboardList,
  Pencil,
  Trash2,
  Check,
  X,
  Plus,
  Loader2,
} from "lucide-react";
import {
  playlistItemsApi,
  PRODUCTION_STATUSES,
  ProductionStatus,
  VideoFormat,
  YoutubePlaylistItem,
} from "@/lib/youtubePlaylistItemsApi";

const BASE = "http://localhost:8000/api/youtube-analytics";

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const t = window.localStorage.getItem("token");
    if (t) h["Authorization"] = `Bearer ${t}`;
  }
  return h;
}

interface Playlist {
  id: string;
  title: string;
  description: string;
  item_count: number;
  thumbnail: string | null;
}
interface Video {
  video_id: string;
  title: string;
  published_at: string | null;
  views: number | null;
  impressions_ctr: number | null;
  watch_time_hours: number | null;
}

type Status = "loading" | "need_connect" | "need_reconnect" | "error" | "ready";

function fmtViews(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

const STATUS_STYLE: Record<ProductionStatus, string> = {
  pending: "bg-slate-500/10 text-slate-300 border-slate-400/30",
  script_generated: "bg-blue-500/10 text-blue-300 border-blue-400/30",
  presentation_created: "bg-indigo-500/10 text-indigo-300 border-indigo-400/30",
  video_created: "bg-amber-500/10 text-amber-300 border-amber-400/30",
  video_edited: "bg-purple-500/10 text-purple-300 border-purple-400/30",
  video_published: "bg-green-500/10 text-green-400 border-green-400/30",
};

function statusLabel(s: ProductionStatus): string {
  return PRODUCTION_STATUSES.find((x) => x.value === s)?.label ?? s;
}

export default function YoutubePlaylistBoard() {
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [channelTitle, setChannelTitle] = useState("");
  const [uploadsId, setUploadsId] = useState("");
  const [playlists, setPlaylists] = useState<Playlist[]>([]);

  const loadPlaylists = async () => {
    setStatus("loading");
    setErrorMsg("");
    try {
      const res = await fetch(`${BASE}/playlists`, { headers: authHeaders() });
      if (res.status === 403) {
        setStatus("need_reconnect");
        return;
      }
      if (res.status === 401 || res.status === 400) {
        const b = await res.json().catch(() => ({}));
        setErrorMsg(b.detail || "");
        setStatus("need_connect");
        return;
      }
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        setErrorMsg(b.detail || `Failed (${res.status})`);
        setStatus("error");
        return;
      }
      const data = await res.json();
      setChannelTitle(data.channel_title || "");
      setUploadsId(data.uploads_playlist_id || "");
      setPlaylists(data.playlists || []);
      setStatus("ready");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Request failed");
      setStatus("error");
    }
  };

  useEffect(() => {
    loadPlaylists();
  }, []);

  const connectGoogle = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/google/authorize`, { headers: authHeaders() });
      if (res.ok) {
        const { authorization_url } = await res.json();
        if (authorization_url) window.location.href = authorization_url;
      } else {
        setErrorMsg("Could not start Google authorization.");
      }
    } catch {
      setErrorMsg("Could not start Google authorization.");
    }
  };

  return (
    <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
      <div className="p-6 border-b border-white/5 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-blue-500/10 text-blue-400 rounded-xl">
            <ClipboardList size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Playlist Production Board</h2>
            <p className="text-slate-500 text-xs mt-0.5">
              Published videos + your pending ideas per playlist
              {channelTitle ? ` · ${channelTitle}` : ""}
            </p>
          </div>
        </div>
        {status === "ready" && (
          <button
            onClick={loadPlaylists}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-slate-300 border border-white/10 hover:bg-white/[0.05] transition-colors uppercase tracking-wider"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        )}
      </div>

      <div className="p-6">
        {status === "loading" && (
          <div className="text-center py-10">
            <div className="animate-spin text-blue-400 inline-block mb-3">
              <RefreshCw size={26} />
            </div>
            <p className="text-slate-400 text-sm animate-pulse">Loading your playlists…</p>
          </div>
        )}

        {(status === "need_reconnect" || status === "need_connect") && (
          <div className="text-center py-10">
            <PlugZap className="w-8 h-8 text-amber-400 mx-auto mb-3" />
            <p className="text-slate-200 text-sm mb-1">
              {status === "need_reconnect"
                ? "Reconnect Google to grant YouTube access."
                : "Connect your Google account to load playlists."}
            </p>
            <button
              onClick={connectGoogle}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-200 border border-blue-500/30 hover:bg-blue-600/30 transition-colors mt-3"
            >
              <PlugZap size={16} /> {status === "need_reconnect" ? "Reconnect Google" : "Connect Google"}
            </button>
          </div>
        )}

        {status === "error" && (
          <div className="py-6">
            <div className="flex items-start gap-2 text-sm text-red-400 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
              <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <button
              onClick={loadPlaylists}
              className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-slate-300 border border-white/10 hover:bg-white/[0.05] transition-colors"
            >
              <RefreshCw size={14} /> Retry
            </button>
          </div>
        )}

        {status === "ready" && (
          <div className="space-y-3">
            {uploadsId && (
              <BoardCard
                key={uploadsId}
                playlist={{ id: uploadsId, title: "Latest Uploads", description: "", item_count: 0, thumbnail: null }}
                isUploads
              />
            )}
            {playlists.length === 0 && !uploadsId && (
              <p className="text-slate-500 text-sm text-center py-6">No playlists found on this channel.</p>
            )}
            {playlists.map((p) => (
              <BoardCard key={p.id} playlist={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function BoardCard({ playlist, isUploads = false }: { playlist: Playlist; isUploads?: boolean }) {
  const [open, setOpen] = useState(false);
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [videosLoading, setVideosLoading] = useState(false);
  const [items, setItems] = useState<YoutubePlaylistItem[] | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [error, setError] = useState("");

  const loadItems = async () => {
    setItemsLoading(true);
    try {
      setItems(await playlistItemsApi.list(playlist.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pending items");
    } finally {
      setItemsLoading(false);
    }
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && videos === null) {
      setVideosLoading(true);
      try {
        const res = await fetch(
          `${BASE}/playlist-videos?playlist_id=${encodeURIComponent(playlist.id)}&limit=10`,
          { headers: authHeaders() },
        );
        setVideos(res.ok ? await res.json() : []);
      } catch {
        setVideos([]);
      } finally {
        setVideosLoading(false);
      }
    }
    if (next && items === null) loadItems();
  };

  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.04] transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className={`p-2 rounded-lg ${isUploads ? "bg-red-500/10 text-red-400" : "bg-blue-500/10 text-blue-400"}`}>
            <ListVideo size={16} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{playlist.title}</p>
            {!isUploads && <p className="text-[11px] text-slate-500">{playlist.item_count} videos</p>}
          </div>
        </div>
        <ChevronDown
          size={18}
          className={`text-slate-400 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-white/5 space-y-4">
          {error && <p className="text-red-400 text-xs pt-3">{error}</p>}

          {/* Published (real YouTube videos, read-only) */}
          <div className="pt-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-green-400 mb-2">Published</p>
            {videosLoading && <p className="text-slate-500 text-sm py-2 animate-pulse">Loading videos…</p>}
            {videos && videos.length === 0 && !videosLoading && (
              <p className="text-slate-600 text-sm py-2">No published videos found.</p>
            )}
            <ul className="space-y-1.5">
              {videos?.map((v) => (
                <li key={v.video_id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-slate-300 truncate">{v.title}</span>
                  <span className="text-[11px] text-slate-500 flex-shrink-0 tabular-nums">
                    {(v.published_at || "").slice(0, 10)} · {fmtViews(v.views)} views
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Pending / in production (local tracker, editable) */}
          <div className="pt-3 border-t border-white/5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-300 mb-2">
              Pending &amp; In Production
            </p>
            {itemsLoading && <p className="text-slate-500 text-sm py-2 animate-pulse">Loading…</p>}
            {items && items.length === 0 && !itemsLoading && (
              <p className="text-slate-600 text-sm py-2">
                No pending ideas yet — add trend ideas from the Analytics tab, or add one below.
              </p>
            )}
            <div className="space-y-2">
              {items?.map((it) => (
                <PendingRow
                  key={it.id}
                  item={it}
                  onChanged={loadItems}
                  onError={(m) => setError(m)}
                />
              ))}
            </div>

            <AddManualForm playlist={playlist} onAdded={loadItems} onError={(m) => setError(m)} />
          </div>
        </div>
      )}
    </div>
  );
}

function PendingRow({
  item,
  onChanged,
  onError,
}: {
  item: YoutubePlaylistItem;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description ?? "");
  const [scheduled, setScheduled] = useState(item.scheduled_date ?? "");
  const [publish, setPublish] = useState(item.publish_date ?? "");
  const [format, setFormat] = useState<VideoFormat>(item.video_format);

  const save = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await playlistItemsApi.update(item.id, {
        title: title.trim(),
        description: description.trim() || null,
        scheduled_date: scheduled || null,
        publish_date: publish || null,
        video_format: format,
      });
      setEditing(false);
      onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (production_status: ProductionStatus) => {
    setBusy(true);
    try {
      await playlistItemsApi.update(item.id, { production_status });
      onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this pending item?")) return;
    setBusy(true);
    try {
      await playlistItemsApi.remove(item.id);
      onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 space-y-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Video title"
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description — angle, key points, notes…"
          rows={2}
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-y"
        />
        <div className="flex gap-3 flex-wrap items-end">
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            Scheduled
            <input
              type="date"
              value={scheduled}
              onChange={(e) => setScheduled(e.target.value)}
              className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
          </label>
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            Publish date
            <input
              type="date"
              value={publish}
              onChange={(e) => setPublish(e.target.value)}
              className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
            />
          </label>
          <label className="text-[10px] uppercase tracking-wider text-slate-500">
            Format
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as VideoFormat)}
              className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
            >
              <option value="full" className="bg-slate-900">Full length</option>
              <option value="short" className="bg-slate-900">Short</option>
            </select>
          </label>
          <div className="flex-1" />
          <button
            onClick={save}
            disabled={busy || !title.trim()}
            className="text-xs px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Save
          </button>
          <button
            onClick={() => setEditing(false)}
            className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
          >
            <X className="w-3 h-3" /> Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-white">{item.title}</p>
          {item.description && (
            <p className="text-xs text-slate-400 mt-0.5 leading-relaxed line-clamp-2">{item.description}</p>
          )}
          <div className="flex items-center gap-2 flex-wrap mt-1.5 text-[11px] text-slate-500">
            <span className="uppercase tracking-wider">{item.video_format}</span>
            {item.scheduled_date && <span>· 📅 {item.scheduled_date}</span>}
            {item.publish_date && <span>· 🚀 {item.publish_date}</span>}
            {item.source === "trend_idea" && (
              <span className="text-purple-300/70">· from trend</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => setEditing(true)}
            className="p-1.5 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors"
            title="Edit"
          >
            <Pencil className="w-3 h-3" />
          </button>
          <button
            onClick={remove}
            disabled={busy}
            className="p-1.5 rounded-lg border border-white/10 text-slate-500 hover:text-red-400 hover:border-red-400/30 transition-colors disabled:opacity-50"
            title="Delete"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
      <div className="mt-2">
        <select
          value={item.production_status}
          onChange={(e) => changeStatus(e.target.value as ProductionStatus)}
          disabled={busy}
          className={`text-[11px] rounded-lg border px-2 py-1 focus:outline-none disabled:opacity-50 [color-scheme:dark] ${STATUS_STYLE[item.production_status]}`}
          title="Production stage"
        >
          {PRODUCTION_STATUSES.map((s) => (
            <option key={s.value} value={s.value} className="bg-slate-900 text-slate-200">
              {statusLabel(s.value)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

function AddManualForm({
  playlist,
  onAdded,
  onError,
}: {
  playlist: Playlist;
  onAdded: () => void;
  onError: (m: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scheduled, setScheduled] = useState("");
  const [publish, setPublish] = useState("");
  const [format, setFormat] = useState<VideoFormat>("full");

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await playlistItemsApi.add({
        playlist_id: playlist.id,
        playlist_title: playlist.title,
        title: title.trim(),
        description: description.trim() || null,
        scheduled_date: scheduled || null,
        publish_date: publish || null,
        video_format: format,
        source: "manual",
      });
      setTitle("");
      setDescription("");
      setScheduled("");
      setPublish("");
      setFormat("full");
      setOpen(false);
      onAdded();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border border-dashed border-white/10 text-slate-400 hover:text-blue-300 hover:border-blue-400/40 transition-colors"
      >
        <Plus className="w-3 h-3" /> Add a video manually
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-lg border border-white/10 bg-white/[0.03] p-3 space-y-2">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Video title / topic"
        className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)"
        rows={2}
        className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 resize-y"
      />
      <div className="flex gap-3 flex-wrap items-end">
        <label className="text-[10px] uppercase tracking-wider text-slate-500">
          Scheduled
          <input
            type="date"
            value={scheduled}
            onChange={(e) => setScheduled(e.target.value)}
            className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
          />
        </label>
        <label className="text-[10px] uppercase tracking-wider text-slate-500">
          Publish date
          <input
            type="date"
            value={publish}
            onChange={(e) => setPublish(e.target.value)}
            className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50 [color-scheme:dark]"
          />
        </label>
        <label className="text-[10px] uppercase tracking-wider text-slate-500">
          Format
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as VideoFormat)}
            className="mt-1 block rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500/50"
          >
            <option value="full" className="bg-slate-900">Full length</option>
            <option value="short" className="bg-slate-900">Short</option>
          </select>
        </label>
        <div className="flex-1" />
        <button
          onClick={submit}
          disabled={busy || !title.trim()}
          className="text-xs px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Add
        </button>
        <button
          onClick={() => setOpen(false)}
          className="text-xs px-3 py-2 rounded-lg border border-white/10 text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
        >
          <X className="w-3 h-3" /> Cancel
        </button>
      </div>
    </div>
  );
}
