"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, ExternalLink, Loader2, RefreshCw, Users } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { Competitor, competitorsApi } from "@/lib/youtubeCompetitorsApi";

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function fmtDate(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "never";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface Props {
  search: string;
  refreshKey: number;
  onChanged: () => void;
  onSelect?: (competitor: Competitor) => void;
}

export default function CompetitorList({ search, refreshKey, onChanged, onSelect }: Props) {
  const [items, setItems] = useState<Competitor[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const page = await competitorsApi.list({ status: "approved", q, limit: 50 });
      setItems(page.items);
      setNextCursor(page.next_cursor);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load competitors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(search), search ? 300 : 0);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search, refreshKey, load]);

  const loadMore = async () => {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const page = await competitorsApi.list({ status: "approved", q: search, cursor: nextCursor, limit: 50 });
      setItems((prev) => [...prev, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSync = async (channelId: string) => {
    setSyncingId(channelId);
    try {
      await competitorsApi.sync(channelId);
      await load(search);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sync failed");
    } finally {
      setSyncingId(null);
    }
  };

  const handleArchive = async (channelId: string) => {
    try {
      await competitorsApi.remove(channelId);
      setItems((prev) => prev.filter((c) => c.channel_id !== channelId));
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to archive");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="animate-spin text-slate-500" size={22} />
      </div>
    );
  }

  if (error) {
    return <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">{error}</div>;
  }

  if (items.length === 0) {
    return (
      <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-12 text-center">
        <Users className="w-6 h-6 text-slate-600 mx-auto mb-2" />
        <p className="text-slate-400 text-sm">No competitors match &quot;{search}&quot;</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-white/5">
              <th className="px-4 py-3 font-medium">Channel</th>
              <th className="px-4 py-3 font-medium text-right">Subscribers</th>
              <th className="px-4 py-3 font-medium text-right">Videos</th>
              <th className="px-4 py-3 font-medium">Last synced</th>
              <th className="px-4 py-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr
                key={c.channel_id}
                className="border-b border-white/5 last:border-0 hover:bg-white/[0.03] transition-colors group cursor-pointer"
                onClick={() => onSelect?.(c)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    {c.thumbnail_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={c.thumbnail_url} alt="" className="w-8 h-8 rounded-full object-cover" />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center text-slate-500">
                        <Users size={14} />
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-200 group-hover:text-red-300 font-medium text-sm transition-colors truncate">
                          {c.title}
                        </span>
                        <a
                          href={`https://youtube.com/channel/${c.channel_id}`}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-slate-500 hover:text-blue-300 flex-shrink-0 transition-colors"
                          title="Open on YouTube"
                        >
                          <ExternalLink size={11} />
                        </a>
                      </div>
                      {c.rationale && <p className="text-slate-500 text-xs truncate max-w-md">{c.rationale}</p>}
                      <p className="text-[10px] text-slate-600 group-hover:text-red-400/60 transition-colors">Click to view videos →</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-slate-300 tabular-nums">{fmtNum(c.subscriber_count)}</td>
                <td className="px-4 py-3 text-right text-slate-400 tabular-nums">{fmtNum(c.video_count)}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {c.sync_error ? (
                    <span className="text-amber-400" title={c.sync_error}>sync error</span>
                  ) : (
                    fmtDate(c.last_synced_at)
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => handleSync(c.channel_id)}
                      disabled={syncingId === c.channel_id}
                      title="Sync latest videos"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-blue-300 hover:bg-blue-500/10 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw size={14} className={syncingId === c.channel_id ? "animate-spin" : ""} />
                    </button>
                    <button
                      onClick={() => handleArchive(c.channel_id)}
                      title="Stop tracking"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                    >
                      <Archive size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {nextCursor && (
        <div className="flex justify-center pt-2">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 border border-white/10 rounded-lg hover:bg-white/[0.03] transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loadingMore && <Loader2 size={12} className="animate-spin" />}
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
