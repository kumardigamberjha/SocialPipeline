"use client";

import { useCallback, useEffect, useState } from "react";
import { Film, Search, Sparkles, Swords, Users } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { Competitor, competitorsApi } from "@/lib/youtubeCompetitorsApi";
import CompetitorDiscoveryModal from "./CompetitorDiscoveryModal";
import CompetitorList from "./CompetitorList";
import CompetitorVideosTab from "./CompetitorVideosTab";

type SubTab = "channels" | "videos";

interface SelectedChannel {
  channel_id: string;
  title: string;
}

export default function CompetitorsTab() {
  const [summary, setSummary] = useState<{ approved: number; rejected: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [search, setSearch] = useState("");
  const [subTab, setSubTab] = useState<SubTab>("channels");
  const [selectedChannel, setSelectedChannel] = useState<SelectedChannel | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      const data = await competitorsApi.summary();
      setSummary(data);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load competitor summary");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSummary();
  }, [loadSummary]);

  const refresh = useCallback(() => {
    loadSummary();
    setRefreshKey((k) => k + 1);
  }, [loadSummary]);

  const handleApplied = () => {
    setShowDiscovery(false);
    refresh();
  };

  const handleSelectCompetitor = (c: Competitor) => {
    setSelectedChannel({ channel_id: c.channel_id, title: c.title });
    setSubTab("videos");
  };

  const handleClearFilter = () => {
    setSelectedChannel(null);
  };

  const noCompetitors = summary && summary.approved === 0 && !showDiscovery;

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <Swords className="text-red-400" size={18} />
          </div>
          <div>
            <h3 className="text-white font-semibold text-sm">Competitor Tracking</h3>
            <p className="text-slate-500 text-xs mt-0.5">
              {summary ? (
                <>
                  <span className="text-slate-300 font-medium">{summary.approved}</span> tracked
                  {summary.rejected > 0 && (
                    <span className="text-slate-600"> · {summary.rejected} rejected</span>
                  )}
                </>
              ) : (
                "Loading…"
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {subTab === "channels" && (
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tracked channels…"
                className="pl-8 pr-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-red-500/40 w-56"
              />
            </div>
          )}
          <button
            onClick={() => setShowDiscovery(true)}
            className="flex items-center gap-2 px-3.5 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-medium rounded-lg transition-colors border border-red-500/20"
          >
            <Sparkles size={14} />
            Find competitors
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">
          {error}
        </div>
      )}

      {noCompetitors ? (
        /* Empty state */
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-16 text-center">
          <Users className="w-8 h-8 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-300 text-sm mb-1">No competitors tracked yet</p>
          <p className="text-slate-500 text-xs mb-4 max-w-sm mx-auto">
            Discover real channels in your niche — every candidate is verified against YouTube
            before it&apos;s ever shown to you.
          </p>
          <button
            onClick={() => setShowDiscovery(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-500/10 text-red-300 border border-red-500/20 hover:bg-red-500/20 transition-colors"
          >
            <Sparkles size={16} /> Find competitors
          </button>
        </div>
      ) : (
        <>
          {/* ── Sub-nav ──────────────────────────────────────────────────── */}
          <div className="flex items-center gap-1 p-1 bg-white/[0.02] border border-white/5 rounded-xl w-fit">
            <SubNavBtn
              active={subTab === "channels"}
              onClick={() => {
                setSubTab("channels");
                setSelectedChannel(null);
              }}
              icon={<Users size={13} />}
              label="Channels"
              count={summary?.approved}
            />
            <SubNavBtn
              active={subTab === "videos"}
              onClick={() => setSubTab("videos")}
              icon={<Film size={13} />}
              label={selectedChannel ? `${selectedChannel.title} videos` : "Top Videos"}
            />
          </div>

          {/* ── Tab Content ──────────────────────────────────────────────── */}
          {subTab === "channels" && (
            <CompetitorList
              search={search}
              refreshKey={refreshKey}
              onChanged={refresh}
              onSelect={handleSelectCompetitor}
            />
          )}

          {subTab === "videos" && (
            <CompetitorVideosTab
              filterChannelId={selectedChannel?.channel_id ?? null}
              filterChannelTitle={selectedChannel?.title ?? null}
              onClearFilter={handleClearFilter}
            />
          )}
        </>
      )}

      {showDiscovery && (
        <CompetitorDiscoveryModal onClose={() => setShowDiscovery(false)} onApplied={handleApplied} />
      )}
    </div>
  );
}

// ── Sub-nav button ────────────────────────────────────────────────────────────

function SubNavBtn({
  active,
  onClick,
  icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
        active
          ? "bg-red-500/15 text-red-300 border border-red-500/25 shadow-sm"
          : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
      }`}
    >
      {icon}
      <span className="truncate max-w-[160px]">{label}</span>
      {count != null && count > 0 && (
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
            active ? "bg-red-500/20 text-red-300" : "bg-white/5 text-slate-500"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
