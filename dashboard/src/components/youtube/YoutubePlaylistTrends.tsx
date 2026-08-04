"use client";

import React, { useEffect, useState } from "react";
import {
  ListVideo,
  Sparkles,
  RefreshCw,
  ChevronDown,
  Wand2,
  PlugZap,
  TrendingUp,
  AlertTriangle,
  Plus,
  Check,
  Loader2,
} from "lucide-react";
import { playlistItemsApi } from "@/lib/youtubePlaylistItemsApi";

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
interface Trend {
  title: string;
  rationale: string;
  format: string;
}

type Status = "loading" | "need_connect" | "need_reconnect" | "error" | "ready";

function fmtViews(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

export default function YoutubePlaylistTrends() {
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
          <div className="p-2.5 bg-purple-500/10 text-purple-400 rounded-xl">
            <Sparkles size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Playlists & Trending Topics</h2>
            <p className="text-slate-500 text-xs mt-0.5">
              Your latest videos per playlist + AI trend ideas
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
            <div className="animate-spin text-purple-400 inline-block mb-3">
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
            <p className="text-slate-600 text-xs mb-5 max-w-md mx-auto">
              This reads your channel&apos;s playlists and latest uploads (read-only). Your Google Cloud
              project must also have the <span className="text-slate-400">YouTube Data API v3</span> enabled.
            </p>
            <button
              onClick={connectGoogle}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors"
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
              <PlaylistCard
                key={uploadsId}
                playlist={{ id: uploadsId, title: "Latest Uploads", description: "", item_count: 0, thumbnail: null }}
                isUploads
              />
            )}
            {playlists.length === 0 && !uploadsId && (
              <p className="text-slate-500 text-sm text-center py-6">No playlists found on this channel.</p>
            )}
            {playlists.map((p) => (
              <PlaylistCard key={p.id} playlist={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PlaylistCard({ playlist, isUploads = false }: { playlist: Playlist; isUploads?: boolean }) {
  const [open, setOpen] = useState(false);
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [videosLoading, setVideosLoading] = useState(false);
  const [trends, setTrends] = useState<Trend[] | null>(null);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendsError, setTrendsError] = useState("");
  // Per-trend "add to pending" state, keyed by trend index: "idle" | "busy" | "done".
  const [addState, setAddState] = useState<Record<number, "busy" | "done">>({});
  const [addError, setAddError] = useState("");

  const addTrendToPending = async (t: Trend, idx: number) => {
    setAddError("");
    setAddState((s) => ({ ...s, [idx]: "busy" }));
    try {
      await playlistItemsApi.add({
        playlist_id: playlist.id,
        playlist_title: playlist.title,
        title: t.title,
        description: t.rationale || null,
        video_format: /shorts?/i.test(t.format || "") ? "short" : "full",
        source: "trend_idea",
      });
      setAddState((s) => ({ ...s, [idx]: "done" }));
    } catch (e) {
      setAddState((s) => {
        const next = { ...s };
        delete next[idx];
        return next;
      });
      setAddError(e instanceof Error ? e.message : "Failed to add");
    }
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && videos === null) {
      setVideosLoading(true);
      try {
        const res = await fetch(
          `${BASE}/playlist-videos?playlist_id=${encodeURIComponent(playlist.id)}&limit=8`,
          { headers: authHeaders() }
        );
        setVideos(res.ok ? await res.json() : []);
      } catch {
        setVideos([]);
      } finally {
        setVideosLoading(false);
      }
    }
  };

  const getTrends = async (refresh = false) => {
    setTrendsLoading(true);
    setTrendsError("");
    try {
      const res = await fetch(
        `${BASE}/playlist-trends?playlist_id=${encodeURIComponent(playlist.id)}` +
          `&playlist_title=${encodeURIComponent(playlist.title)}&refresh=${refresh}`,
        { method: "POST", headers: authHeaders() }
      );
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `Failed (${res.status})`);
      }
      const data = await res.json();
      setTrends(data.trending_topics || []);
    } catch (e) {
      setTrendsError(e instanceof Error ? e.message : "Trend analysis failed");
    } finally {
      setTrendsLoading(false);
    }
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
        <div className="px-4 pb-4 border-t border-white/5">
          {/* Latest videos */}
          <div className="pt-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Latest Videos</p>
            {videosLoading && <p className="text-slate-500 text-sm py-2 animate-pulse">Loading videos…</p>}
            {videos && videos.length === 0 && !videosLoading && (
              <p className="text-slate-600 text-sm py-2">No videos found.</p>
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

          {/* Trending topics */}
          <div className="mt-4 pt-3 border-t border-white/5">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-purple-300 flex items-center gap-1.5">
                <TrendingUp size={13} /> Trending Topic Ideas
              </p>
              <button
                onClick={() => getTrends(!!trends)}
                disabled={trendsLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-600/20 text-purple-200 border border-purple-500/30 hover:bg-purple-600/30 transition-colors disabled:opacity-50"
              >
                <Wand2 size={13} className={trendsLoading ? "animate-pulse" : ""} />
                {trendsLoading ? "Researching…" : trends ? "Regenerate" : "Get Trending Topics"}
              </button>
            </div>

            {trendsLoading && (
              <p className="text-slate-500 text-xs py-3 animate-pulse">
                Searching the web for current trends and asking qwen… this can take 30–60s.
              </p>
            )}
            {trendsError && <p className="text-red-400 text-xs py-2">{trendsError}</p>}

            {addError && <p className="text-red-400 text-xs py-1">{addError}</p>}

            {trends && trends.length > 0 && (
              <div className="space-y-2 mt-1">
                {trends.map((t, i) => {
                  const st = addState[i];
                  return (
                    <div key={i} className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium text-white">{t.title}</p>
                        {t.format && (
                          <span className="text-[10px] uppercase tracking-wider text-purple-300 bg-purple-500/10 border border-purple-500/20 rounded px-1.5 py-0.5 flex-shrink-0">
                            {t.format}
                          </span>
                        )}
                      </div>
                      {t.rationale && <p className="text-xs text-slate-400 mt-1 leading-relaxed">{t.rationale}</p>}
                      <div className="mt-2 flex justify-end">
                        <button
                          onClick={() => addTrendToPending(t, i)}
                          disabled={st === "busy" || st === "done"}
                          title="Save this idea as a pending video under this playlist"
                          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors disabled:cursor-default ${
                            st === "done"
                              ? "border-green-400/30 text-green-400 bg-green-500/10"
                              : "border-white/10 text-slate-300 hover:border-blue-400/40 hover:text-blue-300 disabled:opacity-60"
                          }`}
                        >
                          {st === "busy" ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : st === "done" ? (
                            <Check size={13} />
                          ) : (
                            <Plus size={13} />
                          )}
                          {st === "done" ? "Added" : st === "busy" ? "Adding…" : "Add to Pending"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
