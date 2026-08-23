"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Sparkles,
  ListVideo,
  Clock,
  CheckCircle2,
  Trash2,
  Pencil,
  RefreshCw,
  Plus,
  Loader2,
  Film,
  Check,
  X,
  Tag,
  Calendar,
  ArrowLeft,
  ChevronRight,
  FolderOpen,
} from "lucide-react";
import {
  playlistItemsApi,
  PRODUCTION_STATUSES,
  ProductionStatus,
  VideoFormat,
  YoutubePlaylistItem,
} from "@/lib/youtubePlaylistItemsApi";

const STATUS_STYLE: Record<ProductionStatus, string> = {
  pending: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  script_generated: "bg-blue-500/10 text-blue-300 border-blue-400/30",
  presentation_created: "bg-indigo-500/10 text-indigo-300 border-indigo-400/30",
  video_created: "bg-purple-500/10 text-purple-300 border-purple-400/30",
  video_edited: "bg-pink-500/10 text-pink-300 border-pink-400/30",
  video_published: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
};

function statusLabel(s: ProductionStatus): string {
  return PRODUCTION_STATUSES.find((x) => x.value === s)?.label ?? s;
}

interface PlaylistGroup {
  id: string;
  title: string;
  items: YoutubePlaylistItem[];
  pendingCount: number;
  inProgressCount: number;
  publishedCount: number;
}

export default function PendingIdeasQueue() {
  const [items, setItems] = useState<YoutubePlaylistItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await playlistItemsApi.list();
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pending ideas");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // Group items by playlist_id
  const playlistGroups = useMemo<PlaylistGroup[]>(() => {
    if (!items) return [];
    const map: Record<string, PlaylistGroup> = {};

    items.forEach((item) => {
      const key = item.playlist_id || "general";
      const title =
        item.playlist_title ||
        (key === "general"
          ? "General / Custom Backlog"
          : `Playlist (${key.length > 12 ? key.slice(0, 12) + "…" : key})`);

      if (!map[key]) {
        map[key] = {
          id: key,
          title,
          items: [],
          pendingCount: 0,
          inProgressCount: 0,
          publishedCount: 0,
        };
      }

      map[key].items.push(item);
      if (item.production_status === "pending") map[key].pendingCount++;
      else if (item.production_status === "video_published") map[key].publishedCount++;
      else map[key].inProgressCount++;
    });

    return Object.values(map);
  }, [items]);

  const selectedGroup = useMemo(() => {
    if (!selectedPlaylistId) return null;
    if (selectedPlaylistId === "__ALL__") {
      return {
        id: "__ALL__",
        title: "All Playlist Queues & Ideas",
        items: items || [],
        pendingCount: (items || []).filter((i) => i.production_status === "pending").length,
        inProgressCount: (items || []).filter(
          (i) => i.production_status !== "pending" && i.production_status !== "video_published"
        ).length,
        publishedCount: (items || []).filter((i) => i.production_status === "video_published").length,
      };
    }
    return playlistGroups.find((g) => g.id === selectedPlaylistId) || null;
  }, [selectedPlaylistId, playlistGroups, items]);

  const activeItems = useMemo(() => {
    if (!selectedGroup) return [];
    return selectedGroup.items.filter((item) => {
      if (filterStatus === "all") return true;
      if (filterStatus === "pending") return item.production_status === "pending";
      if (filterStatus === "in_progress")
        return item.production_status !== "pending" && item.production_status !== "video_published";
      if (filterStatus === "published") return item.production_status === "video_published";
      return true;
    });
  }, [selectedGroup, filterStatus]);

  const totalPending = (items || []).filter((i) => i.production_status === "pending").length;
  const totalCount = items?.length || 0;

  return (
    <div className="glass-card rounded-2xl border border-white/10 bg-slate-900/40 overflow-hidden shadow-xl mb-8">
      {/* Top Header Bar */}
      <div className="p-6 border-b border-white/5 bg-white/[0.02] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {selectedPlaylistId ? (
            <button
              onClick={() => setSelectedPlaylistId(null)}
              className="p-2.5 bg-white/5 hover:bg-white/10 text-slate-300 rounded-xl border border-white/10 transition-colors flex items-center gap-1.5 text-xs font-semibold"
              title="Back to Playlists"
            >
              <ArrowLeft size={16} /> Playlists
            </button>
          ) : (
            <div className="p-2.5 bg-gradient-to-br from-purple-500/20 to-blue-500/20 text-purple-300 rounded-xl border border-purple-500/20">
              <FolderOpen size={20} />
            </div>
          )}

          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-tight">
                {selectedGroup ? selectedGroup.title : "YouTube Playlist Ideas & Queues"}
              </h2>
              {totalCount > 0 && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  {selectedGroup ? `${selectedGroup.pendingCount} Pending` : `${playlistGroups.length} Playlists (${totalPending} Ideas)`}
                </span>
              )}
            </div>
            <p className="text-slate-400 text-xs mt-0.5">
              {selectedGroup
                ? "Manage topic ideas and production stages for this playlist"
                : "Select a YouTube Playlist folder to view and manage saved topic ideas"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {selectedPlaylistId && (
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-slate-300 focus:outline-none focus:border-purple-500/50 [color-scheme:dark]"
            >
              <option value="all" className="bg-slate-900">All Statuses ({selectedGroup?.items.length || 0})</option>
              <option value="pending" className="bg-slate-900">Pending Only ({selectedGroup?.pendingCount || 0})</option>
              <option value="in_progress" className="bg-slate-900">In Production</option>
              <option value="published" className="bg-slate-900">Published</option>
            </select>
          )}

          {selectedPlaylistId && (
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition-colors shadow-md shadow-purple-600/20"
            >
              <Plus size={14} /> Add Idea
            </button>
          )}

          <button
            onClick={loadItems}
            disabled={loading}
            className="p-2 rounded-lg border border-white/10 text-slate-400 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50"
            title="Refresh queue"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>

          <Link
            href="/youtube-analysis"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-medium transition-colors"
          >
            <Sparkles size={14} /> Browse Trends
          </Link>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="p-6">
        {loading && items === null && (
          <div className="flex flex-col items-center justify-center py-12 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin text-purple-400 mb-2" />
            <p className="text-sm">Loading playlist ideas…</p>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-center justify-between mb-4">
            <span>{error}</span>
            <button onClick={loadItems} className="underline text-red-200">
              Retry
            </button>
          </div>
        )}

        {/* VIEW 1: PLAYLIST FOLDERS GRID (Default view when no playlist is selected) */}
        {!selectedPlaylistId && items !== null && !loading && (
          <div>
            {playlistGroups.length === 0 ? (
              <div className="text-center py-12 px-4 border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
                <FolderOpen className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-slate-300">No Playlists or Pending Ideas Found</h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                  Add topic ideas from the YouTube Analytics trends page to group them into playlists here for production.
                </p>
                <Link
                  href="/youtube-analysis"
                  className="inline-flex items-center gap-2 px-4 py-2 mt-4 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors shadow-lg shadow-purple-600/20"
                >
                  <Sparkles size={14} /> Find Trending Topics
                </Link>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Select a Playlist Folder ({playlistGroups.length})
                  </span>
                  <button
                    onClick={() => setSelectedPlaylistId("__ALL__")}
                    className="text-xs text-purple-400 hover:text-purple-300 font-medium transition-colors flex items-center gap-1"
                  >
                    View All Items ({totalCount}) <ChevronRight size={14} />
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {playlistGroups.map((group) => (
                    <div
                      key={group.id}
                      onClick={() => setSelectedPlaylistId(group.id)}
                      className="group cursor-pointer rounded-xl border border-white/10 bg-white/[0.02] hover:bg-white/[0.05] hover:border-purple-500/40 p-5 transition-all flex flex-col justify-between space-y-4 shadow-lg hover:shadow-purple-900/10"
                    >
                      <div>
                        {/* Folder Header */}
                        <div className="flex items-center justify-between mb-3">
                          <div className="p-2 rounded-lg bg-purple-500/15 text-purple-300 border border-purple-500/20 group-hover:scale-105 transition-transform">
                            <FolderOpen size={18} />
                          </div>
                          <span className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                            {group.pendingCount} Pending
                          </span>
                        </div>

                        {/* Title */}
                        <h3 className="text-sm font-bold text-white group-hover:text-purple-200 transition-colors line-clamp-2 leading-snug">
                          {group.title}
                        </h3>

                        {/* Summary Badges */}
                        <div className="flex items-center gap-2 mt-3 text-[11px] text-slate-400 flex-wrap">
                          <span className="bg-white/5 px-2 py-0.5 rounded border border-white/5">
                            {group.items.length} total topics
                          </span>
                          {group.inProgressCount > 0 && (
                            <span className="bg-blue-500/10 text-blue-300 px-2 py-0.5 rounded border border-blue-500/20">
                              {group.inProgressCount} in dev
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Latest topic preview */}
                      <div className="pt-3 border-t border-white/5">
                        <div className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider mb-1">
                          Up Next:
                        </div>
                        <p className="text-xs text-slate-300 truncate font-medium">
                          {group.items[0]?.title || "No items"}
                        </p>
                        <div className="flex items-center justify-between mt-3 text-xs text-purple-400 font-semibold group-hover:translate-x-1 transition-transform">
                          <span>Open Playlist Queue</span>
                          <ChevronRight size={14} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* VIEW 2: SINGLE PLAYLIST QUEUE ITEMS (Shown when a playlist is clicked) */}
        {selectedPlaylistId && selectedGroup && (
          <div>
            {activeItems.length === 0 ? (
              <div className="text-center py-12 px-4 border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
                <ListVideo className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-slate-300">
                  {filterStatus === "all"
                    ? "No items in this playlist queue"
                    : `No items matching "${filterStatus}" filter`}
                </h3>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 mt-4 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors"
                >
                  <Plus size={14} /> Add First Idea to Playlist
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {activeItems.map((item) => (
                  <ItemCard
                    key={item.id}
                    item={item}
                    onUpdated={loadItems}
                    isEditing={editingId === item.id}
                    setEditing={(v) => setEditingId(v ? item.id : null)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add Idea Modal */}
      {showAddModal && (
        <AddIdeaModal
          defaultPlaylistId={selectedPlaylistId !== "__ALL__" ? selectedPlaylistId || "general" : "general"}
          defaultPlaylistTitle={selectedGroup?.title !== "All Playlist Queues & Ideas" ? selectedGroup?.title : undefined}
          playlistGroups={playlistGroups}
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            setShowAddModal(false);
            loadItems();
          }}
        />
      )}
    </div>
  );
}

function ItemCard({
  item,
  onUpdated,
  isEditing,
  setEditing,
}: {
  item: YoutubePlaylistItem;
  onUpdated: () => void;
  isEditing: boolean;
  setEditing: (v: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description ?? "");
  const [scheduled, setScheduled] = useState(item.scheduled_date ?? "");
  const [publish, setPublish] = useState(item.publish_date ?? "");
  const [format, setFormat] = useState<VideoFormat>(item.video_format);

  const handleStatusChange = async (newStatus: ProductionStatus) => {
    setBusy(true);
    try {
      await playlistItemsApi.update(item.id, { production_status: newStatus });
      onUpdated();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async () => {
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
      onUpdated();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save changes");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${item.title}" from your queue?`)) return;
    setBusy(true);
    try {
      await playlistItemsApi.remove(item.id);
      onUpdated();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to delete item");
    } finally {
      setBusy(false);
    }
  };

  if (isEditing) {
    return (
      <div className="rounded-xl border border-purple-500/30 bg-purple-950/20 p-4 space-y-3 shadow-lg">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Video title"
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500/50"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Rationale / key points…"
          rows={2}
          className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-purple-500/50 resize-y"
        />
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[10px] uppercase tracking-wider text-slate-400">
            Scheduled Date
            <input
              type="date"
              value={scheduled}
              onChange={(e) => setScheduled(e.target.value)}
              className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-2 py-1 text-xs text-slate-200 focus:outline-none [color-scheme:dark]"
            />
          </label>
          <label className="text-[10px] uppercase tracking-wider text-slate-400">
            Format
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as VideoFormat)}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-white/10 px-2 py-1 text-xs text-slate-200 focus:outline-none"
            >
              <option value="full">Full Length</option>
              <option value="short">Short</option>
            </select>
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-white/5">
          <button
            onClick={() => setEditing(false)}
            className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={busy || !title.trim()}
            className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition-colors flex items-center gap-1 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Save
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-xl border border-white/5 bg-white/[0.02] p-4 hover:border-white/15 transition-all flex flex-col justify-between space-y-3">
      <div>
        {/* Badges bar */}
        <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            {item.source === "trend_idea" ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                <Sparkles size={10} /> Trend Idea
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-500/15 text-slate-400 border border-white/10">
                <Tag size={10} /> Manual
              </span>
            )}

            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-blue-500/10 text-blue-300 border border-blue-500/20 uppercase tracking-wider">
              <Film size={10} /> {item.video_format}
            </span>

            {item.playlist_title && (
              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-white/5 text-slate-400 border border-white/5 truncate max-w-[180px]">
                {item.playlist_title}
              </span>
            )}
          </div>

          {/* Action controls */}
          <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-md hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
              title="Edit idea"
            >
              <Pencil size={13} />
            </button>
            <button
              onClick={handleDelete}
              disabled={busy}
              className="p-1.5 rounded-md hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors"
              title="Delete item"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>

        {/* Title & Description */}
        <h4 className="text-sm font-semibold text-white group-hover:text-purple-200 transition-colors leading-snug">
          {item.title}
        </h4>
        {item.description && (
          <p className="text-xs text-slate-400 mt-1.5 leading-relaxed line-clamp-3">
            {item.description}
          </p>
        )}
      </div>

      {/* Footer: Production status picker */}
      <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">
            Stage:
          </span>
          <select
            value={item.production_status}
            onChange={(e) => handleStatusChange(e.target.value as ProductionStatus)}
            disabled={busy}
            className={`text-xs font-medium rounded-lg border px-2.5 py-1 focus:outline-none cursor-pointer transition-colors [color-scheme:dark] ${STATUS_STYLE[item.production_status]}`}
          >
            {PRODUCTION_STATUSES.map((s) => (
              <option key={s.value} value={s.value} className="bg-slate-900 text-slate-200">
                {statusLabel(s.value)}
              </option>
            ))}
          </select>
        </div>

        {item.scheduled_date && (
          <span className="text-[11px] text-slate-500 flex items-center gap-1">
            <Calendar size={11} /> {item.scheduled_date}
          </span>
        )}
      </div>
    </div>
  );
}

function AddIdeaModal({
  defaultPlaylistId,
  defaultPlaylistTitle,
  playlistGroups,
  onClose,
  onAdded,
}: {
  defaultPlaylistId: string;
  defaultPlaylistTitle?: string;
  playlistGroups: PlaylistGroup[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [playlistId, setPlaylistId] = useState(defaultPlaylistId);
  const [playlistTitle, setPlaylistTitle] = useState(defaultPlaylistTitle || "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [format, setFormat] = useState<VideoFormat>("full");
  const [scheduled, setScheduled] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const found = playlistGroups.find((g) => g.id === playlistId);
    if (found && found.title) {
      setPlaylistTitle(found.title);
    }
  }, [playlistId, playlistGroups]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setBusy(true);
    try {
      await playlistItemsApi.add({
        playlist_id: playlistId,
        playlist_title: playlistTitle.trim() || undefined,
        title: title.trim(),
        description: description.trim() || undefined,
        video_format: format,
        scheduled_date: scheduled || undefined,
        source: "manual",
      });
      onAdded();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add idea");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Plus className="text-purple-400" size={18} /> Add Pending Video Idea
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Target Playlist
            </label>
            <select
              value={playlistId}
              onChange={(e) => {
                setPlaylistId(e.target.value);
                const g = playlistGroups.find((pg) => pg.id === e.target.value);
                if (g) setPlaylistTitle(g.title);
              }}
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500/50 [color-scheme:dark]"
            >
              {playlistGroups.map((g) => (
                <option key={g.id} value={g.id} className="bg-slate-900">
                  {g.title} ({g.id})
                </option>
              ))}
              {!playlistGroups.some((g) => g.id === "general") && (
                <option value="general" className="bg-slate-900">
                  General / Custom Backlog
                </option>
              )}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Video Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Building an AI Agent with Gemini 3.6 Flash"
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500/50"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Rationale / Outline Notes
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Key concepts, target audience hook, or research note..."
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-purple-500/50"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Format</label>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as VideoFormat)}
                className="w-full rounded-lg bg-slate-900 border border-white/10 px-3 py-2 text-xs text-white focus:outline-none"
              >
                <option value="full">Full Length Video</option>
                <option value="short">60-Sec Short</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Scheduled Date</label>
              <input
                type="date"
                value={scheduled}
                onChange={(e) => setScheduled(e.target.value)}
                className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-xs text-white focus:outline-none [color-scheme:dark]"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-4 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !title.trim()}
              className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50 shadow-md shadow-purple-600/20"
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />} Add to Queue
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
