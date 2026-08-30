"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Eye,
  Loader2,
  ThumbsUp,
  MessageCircle,
  ArrowUpDown,
  Users,
  Film,
  RefreshCw,
} from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import {
  CompetitorVideo,
  competitorsApi,
} from "@/lib/youtubeCompetitorsApi";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function fmtDuration(secs: number): string {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

type VideoRow = CompetitorVideo & {
  channel_title?: string;
  channel_thumbnail?: string;
  channel_handle?: string;
};

interface Props {
  /** If set, show only videos from this competitor channel */
  filterChannelId?: string | null;
  filterChannelTitle?: string | null;
  onClearFilter?: () => void;
}

const PER_PAGE = 20;

export default function CompetitorVideosTab({
  filterChannelId,
  filterChannelTitle,
  onClearFilter,
}: Props) {
  const [videos, setVideos] = useState<VideoRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError(null);
      try {
        const data = await competitorsApi.listVideos({
          page: p,
          per_page: PER_PAGE,
          channel_id: filterChannelId ?? undefined,
        });
        setVideos(data.items as VideoRow[]);
        setTotalPages(data.pages);
        setTotal(data.total);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load videos");
      } finally {
        setLoading(false);
      }
    },
    [filterChannelId],
  );

  useEffect(() => {
    setPage(1);
    load(1);
  }, [load]);

  const goTo = (p: number) => {
    if (p < 1 || p > totalPages) return;
    setPage(p);
    load(p);
  };

  const handleSync = async () => {
    if (!filterChannelId) return;
    setSyncing(true);
    try {
      await competitorsApi.sync(filterChannelId);
      await load(page);
    } catch {
      /* silent */
    } finally {
      setSyncing(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          {filterChannelId ? (
            <button
              onClick={onClearFilter}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              <ChevronLeft size={14} />
              All channels
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <Film size={16} className="text-red-400" />
              <span className="text-white font-semibold text-sm">Top Videos</span>
            </div>
          )}
          {filterChannelTitle && (
            <>
              <span className="text-slate-600 text-sm">/</span>
              <span className="text-slate-200 text-sm font-medium">{filterChannelTitle}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {total > 0 && (
            <span className="text-xs text-slate-500">
              {total.toLocaleString()} videos · sorted by views
            </span>
          )}
          {filterChannelId && (
            <button
              onClick={handleSync}
              disabled={syncing}
              title="Sync latest videos"
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-slate-400 hover:text-blue-300 border border-white/10 hover:border-blue-500/30 rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw size={12} className={syncing ? "animate-spin" : ""} />
              Sync
            </button>
          )}
        </div>
      </div>

      {/* Sort hint */}
      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
        <ArrowUpDown size={11} />
        Sorted by highest views
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center h-52">
          <Loader2 className="animate-spin text-slate-500" size={24} />
        </div>
      ) : videos.length === 0 ? (
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-16 text-center">
          <Film className="w-8 h-8 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm mb-1">No videos yet</p>
          <p className="text-slate-500 text-xs">
            {filterChannelId
              ? 'Click "Sync" to fetch this channel\'s latest videos.'
              : "Approve competitors and sync their videos to see them here."}
          </p>
        </div>
      ) : (
        <>
          {/* Video grid */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {videos.map((v) => (
              <VideoCard key={v.video_id} video={v} showChannel={!filterChannelId} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button
                onClick={() => goTo(page - 1)}
                disabled={page === 1}
                className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] border border-white/10 transition-colors disabled:opacity-30"
              >
                <ChevronLeft size={14} />
              </button>
              {paginationRange(page, totalPages).map((p, i) =>
                p === "…" ? (
                  <span key={`ellipsis-${i}`} className="text-slate-600 text-xs px-1">
                    …
                  </span>
                ) : (
                  <button
                    key={p}
                    onClick={() => goTo(Number(p))}
                    className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors border ${
                      p === page
                        ? "bg-red-500/20 border-red-500/40 text-red-300"
                        : "border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
                    }`}
                  >
                    {p}
                  </button>
                ),
              )}
              <button
                onClick={() => goTo(page + 1)}
                disabled={page === totalPages}
                className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] border border-white/10 transition-colors disabled:opacity-30"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── VideoCard ─────────────────────────────────────────────────────────────────

function VideoCard({ video, showChannel }: { video: VideoRow; showChannel: boolean }) {
  const isShort = video.is_short;
  const ytUrl = `https://youtube.com/watch?v=${video.video_id}`;

  return (
    <a
      href={ytUrl}
      target="_blank"
      rel="noreferrer"
      className="group block bg-white/[0.02] border border-white/5 rounded-xl overflow-hidden hover:border-red-500/20 hover:bg-white/[0.04] transition-all duration-200"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-slate-800/60 overflow-hidden">
        {video.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={video.thumbnail_url}
            alt={video.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Film size={28} className="text-slate-600" />
          </div>
        )}
        {/* Duration badge */}
        <div className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 bg-black/80 rounded text-[10px] text-white font-mono">
          {isShort ? "#Short" : fmtDuration(video.duration_seconds)}
        </div>
        {/* Views overlay on hover */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end px-2 pb-2">
          <span className="text-white text-xs font-medium flex items-center gap-1">
            <Eye size={11} />
            {fmtNum(video.views)} views
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        {/* Channel badge */}
        {showChannel && (video.channel_title || video.channel_handle) && (
          <div className="flex items-center gap-1.5">
            {video.channel_thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={video.channel_thumbnail}
                alt=""
                className="w-4 h-4 rounded-full object-cover"
              />
            ) : (
              <div className="w-4 h-4 rounded-full bg-white/10 flex items-center justify-center">
                <Users size={8} className="text-slate-400" />
              </div>
            )}
            <span className="text-[11px] text-slate-400 truncate">
              {video.channel_title ?? video.channel_handle}
            </span>
          </div>
        )}

        {/* Title */}
        <p className="text-slate-200 text-xs font-medium leading-snug line-clamp-2 group-hover:text-white transition-colors">
          {video.title}
        </p>

        {/* Metrics row */}
        <div className="flex items-center gap-3 text-[11px] text-slate-500">
          <span className="flex items-center gap-1">
            <Eye size={10} className="text-blue-400" />
            <span className="text-slate-300">{fmtNum(video.views)}</span>
          </span>
          <span className="flex items-center gap-1">
            <ThumbsUp size={10} className="text-emerald-400" />
            <span>{fmtNum(video.likes)}</span>
          </span>
          <span className="flex items-center gap-1">
            <MessageCircle size={10} className="text-amber-400" />
            <span>{fmtNum(video.comments)}</span>
          </span>
          <span className="ml-auto text-[10px]">{fmtDate(video.published_at)}</span>
        </div>

        {/* External link hint */}
        <div className="flex items-center gap-1 text-[10px] text-slate-600 group-hover:text-red-400 transition-colors">
          <ExternalLink size={9} />
          Watch on YouTube
        </div>
      </div>
    </a>
  );
}

// ── Pagination range helper ───────────────────────────────────────────────────

function paginationRange(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "…")[] = [1];
  if (current > 3) pages.push("…");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p);
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}
