"use client";

import React, { useEffect, useState, useMemo } from "react";
import { Loader2, Users, AlertCircle, BarChart3, TrendingUp, ThumbsUp, Activity, Sparkles, Check, CheckCircle2 } from "lucide-react";
import { ApiError } from "@/lib/apiClient";
import { Competitor, CompetitorDetail, competitorsApi } from "@/lib/youtubeCompetitorsApi";
import { motion, AnimatePresence } from "framer-motion";

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function CompetitorBenchmark() {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detailsMap, setDetailsMap] = useState<Record<string, CompetitorDetail>>({});
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [showSelector, setShowSelector] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const page = await competitorsApi.list({ status: "approved", limit: 50 });
        const items = [...page.items].sort((a, b) => b.subscriber_count - a.subscriber_count);
        setCompetitors(items);
        
        if (items.length > 0) {
          // Default select top 3 (or fewer if we don't have 3)
          const topIds = items.slice(0, 3).map(c => c.channel_id);
          setSelectedIds(topIds);
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load competitors");
      } finally {
        setLoadingList(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    if (selectedIds.length === 0) return;

    async function loadDetails() {
      setLoadingDetails(true);
      try {
        const missingIds = selectedIds.filter(id => !detailsMap[id]);
        if (missingIds.length === 0) {
          setLoadingDetails(false);
          return;
        }

        const results = await Promise.all(
          missingIds.map(id => competitorsApi.get(id).catch(() => null))
        );

        const newMap = { ...detailsMap };
        missingIds.forEach((id, idx) => {
          if (results[idx]) {
            newMap[id] = results[idx] as CompetitorDetail;
          }
        });
        setDetailsMap(newMap);
      } catch (e) {
        console.error("Failed to load details", e);
      } finally {
        setLoadingDetails(false);
      }
    }

    loadDetails();
  }, [selectedIds, detailsMap]);

  const toggleSelection = (id: string) => {
    setSelectedIds(prev => {
      if (prev.includes(id)) {
        return prev.filter(x => x !== id);
      } else {
        if (prev.length >= 4) return prev; // max 4
        return [...prev, id];
      }
    });
  };

  const benchmarkData = useMemo(() => {
    return selectedIds.map(id => {
      const basic = competitors.find(c => c.channel_id === id);
      const detail = detailsMap[id];
      
      let avgViews = 0;
      let avgEngRate = 0;
      let uploadFreqDays = 0;
      
      if (detail && detail.videos.length > 0) {
        const vids = detail.videos;
        const totalViews = vids.reduce((sum, v) => sum + v.views, 0);
        avgViews = Math.round(totalViews / vids.length);
        
        const totalEng = vids.reduce((sum, v) => sum + v.likes + v.comments, 0);
        avgEngRate = totalViews > 0 ? (totalEng / totalViews) * 100 : 0;
        
        const sortedDates = vids
          .map(v => (v.published_at ? new Date(v.published_at).getTime() : 0))
          .filter(t => t > 0)
          .sort((a, b) => b - a);
          
        if (sortedDates.length > 1) {
          const diffs = [];
          for (let i = 0; i < sortedDates.length - 1; i++) {
            diffs.push((sortedDates[i] - sortedDates[i+1]) / (1000 * 60 * 60 * 24));
          }
          uploadFreqDays = diffs.reduce((sum, d) => sum + d, 0) / diffs.length;
        }
      }

      return {
        id,
        basic,
        detail,
        avgViews,
        avgEngRate,
        uploadFreqDays
      };
    });
  }, [selectedIds, competitors, detailsMap]);

  // Find winners for each metric
  const maxSubs = Math.max(0, ...benchmarkData.map(d => d.basic?.subscriber_count ?? 0));
  const maxTotalViews = Math.max(0, ...benchmarkData.map(d => d.basic?.view_count ?? 0));
  const maxAvgViews = Math.max(0, ...benchmarkData.map(d => d.avgViews));
  const maxEngRate = Math.max(0, ...benchmarkData.map(d => d.avgEngRate));

  if (loadingList) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-red-500" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300">
        <AlertCircle size={18} />
        <p className="text-sm font-medium">{error}</p>
      </div>
    );
  }

  if (competitors.length === 0) {
    return (
      <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-16 text-center">
        <Users className="w-8 h-8 text-slate-600 mx-auto mb-3" />
        <p className="text-slate-300 text-sm">Not enough data to benchmark.</p>
        <p className="text-slate-500 text-xs mt-1">Track at least 2 channels to compare them side-by-side.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Sparkles className="text-red-400" size={18} />
            Channel Benchmark Matrix
          </h2>
          <p className="text-slate-400 text-xs mt-1">
            Compare performance metrics against top competitors to discover your edge.
          </p>
        </div>
        <button
          onClick={() => setShowSelector(!showSelector)}
          className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors flex items-center gap-2 bg-white/[0.03] hover:bg-white/[0.06] border-white/10 text-slate-300"
        >
          <Users size={14} />
          {showSelector ? "Hide Selector" : "Change Channels"}
        </button>
      </div>

      <AnimatePresence>
        {showSelector && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 bg-slate-950/50 border border-white/5 rounded-2xl backdrop-blur-xl">
              <p className="text-xs text-slate-400 mb-3 uppercase tracking-wider font-semibold">
                Select up to 4 channels to compare
              </p>
              <div className="flex flex-wrap gap-2">
                {competitors.map(c => {
                  const isSelected = selectedIds.includes(c.channel_id);
                  return (
                    <button
                      key={c.channel_id}
                      onClick={() => toggleSelection(c.channel_id)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-all border ${
                        isSelected 
                          ? "bg-red-500/20 border-red-500/40 text-red-200" 
                          : "bg-white/[0.02] border-white/10 text-slate-400 hover:bg-white/[0.05]"
                      }`}
                    >
                      {c.thumbnail_url ? (
                        <img src={c.thumbnail_url} alt="" className="w-4 h-4 rounded-full object-cover" />
                      ) : (
                        <div className="w-4 h-4 rounded-full bg-slate-800 flex items-center justify-center">
                          <Users size={8} />
                        </div>
                      )}
                      <span className="truncate max-w-[120px] font-medium">{c.title}</span>
                      {isSelected && <Check size={12} className="text-red-400" />}
                    </button>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {selectedIds.length < 2 ? (
        <div className="p-12 text-center border border-white/5 rounded-2xl bg-white/[0.01]">
          <BarChart3 className="w-10 h-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">Select at least 2 channels to view the benchmark matrix.</p>
        </div>
      ) : (
        <div className="relative">
          {loadingDetails && (
            <div className="absolute inset-0 z-10 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center rounded-2xl">
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="animate-spin text-red-500" size={28} />
                <span className="text-xs font-medium text-red-300 bg-red-500/10 px-3 py-1 rounded-full border border-red-500/20 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                  Analyzing recent videos...
                </span>
              </div>
            </div>
          )}

          <div className="overflow-x-auto pb-4">
            <div className={`grid grid-cols-${benchmarkData.length} min-w-[800px] gap-4`}>
              {benchmarkData.map((data, i) => (
                <div key={data.id} className="flex flex-col gap-4">
                  {/* Channel Header Card */}
                  <div className="glass-card rounded-2xl border border-white/5 bg-gradient-to-b from-white/[0.04] to-transparent p-5 flex flex-col items-center text-center relative overflow-hidden group">
                    <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-transparent via-red-500/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                    
                    {data.basic?.thumbnail_url ? (
                      <div className="relative w-16 h-16 rounded-full p-1 bg-gradient-to-br from-slate-700 to-slate-900 shadow-xl mb-3">
                        <img src={data.basic.thumbnail_url} alt="" className="w-full h-full rounded-full object-cover border border-slate-800" />
                      </div>
                    ) : (
                      <div className="w-16 h-16 rounded-full bg-slate-800 border-2 border-slate-700 flex items-center justify-center text-slate-500 shadow-xl mb-3">
                        <Users size={24} />
                      </div>
                    )}
                    
                    <h3 className="text-white font-bold text-base truncate w-full mb-0.5">{data.basic?.title || 'Unknown'}</h3>
                    <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">{data.basic?.handle || 'Channel'}</p>
                  </div>

                  {/* Metrics List */}
                  <div className="flex flex-col gap-2">
                    
                    {/* Subscriber Count */}
                    <MetricCard 
                      label="Subscribers"
                      value={fmtNum(data.basic?.subscriber_count)}
                      icon={<Users size={14} className="text-blue-400" />}
                      isWinner={data.basic?.subscriber_count === maxSubs && maxSubs > 0}
                    />

                    {/* Total Views */}
                    <MetricCard 
                      label="Total Views"
                      value={fmtNum(data.basic?.view_count)}
                      icon={<Activity size={14} className="text-purple-400" />}
                      isWinner={data.basic?.view_count === maxTotalViews && maxTotalViews > 0}
                    />

                    {/* Video Count */}
                    <MetricCard 
                      label="Uploads"
                      value={fmtNum(data.basic?.video_count)}
                      icon={<BarChart3 size={14} className="text-emerald-400" />}
                      isWinner={false} // More uploads isn't necessarily better
                    />

                    {/* Recent Average Views */}
                    <MetricCard 
                      label="Avg. Views (Recent)"
                      value={fmtNum(data.avgViews)}
                      icon={<TrendingUp size={14} className="text-red-400" />}
                      isWinner={data.avgViews === maxAvgViews && maxAvgViews > 0}
                      highlight
                    />

                    {/* Engagement Rate */}
                    <MetricCard 
                      label="Engagement Rate"
                      value={`${data.avgEngRate.toFixed(2)}%`}
                      icon={<ThumbsUp size={14} className="text-amber-400" />}
                      isWinner={data.avgEngRate === maxEngRate && maxEngRate > 0}
                      highlight
                    />

                    {/* Upload Frequency */}
                    <MetricCard 
                      label="Upload Frequency"
                      value={data.uploadFreqDays > 0 ? `~${Math.round(data.uploadFreqDays)} days` : 'N/A'}
                      icon={<Activity size={14} className="text-cyan-400" />}
                      isWinner={false}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, icon, isWinner, highlight }: { label: string; value: string; icon: React.ReactNode; isWinner: boolean; highlight?: boolean }) {
  return (
    <div className={`p-4 rounded-xl border flex flex-col gap-2 relative overflow-hidden transition-all duration-300 ${
      isWinner 
        ? "bg-amber-500/10 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.05)]" 
        : highlight
          ? "bg-white/[0.03] border-white/10 hover:border-white/20"
          : "bg-transparent border-white/5"
    }`}>
      {isWinner && (
        <div className="absolute top-0 right-0 p-1 bg-gradient-to-bl from-amber-500/20 to-transparent rounded-bl-xl">
          <CheckCircle2 size={12} className="text-amber-400" />
        </div>
      )}
      <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium tracking-wide uppercase">
        {icon}
        {label}
      </div>
      <div className={`text-xl font-bold font-mono tracking-tight ${isWinner ? "text-amber-300" : "text-slate-200"}`}>
        {value}
      </div>
    </div>
  );
}
