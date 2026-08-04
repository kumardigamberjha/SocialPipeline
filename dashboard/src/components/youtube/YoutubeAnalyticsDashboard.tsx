"use client";

import React, { useState, useEffect } from 'react';
import { Youtube, TrendingUp, Clock, Users, PlaySquare, Calendar, RefreshCw, BarChart2, X, ChevronRight, ListVideo } from 'lucide-react';
import YoutubePlaylistTrends from './YoutubePlaylistTrends';
import YoutubeStrategyRoadmap from './YoutubeStrategyRoadmap';
import YoutubePlaylistBoard from './YoutubePlaylistBoard';

interface YoutubeStats {
  total_videos: number;
  total_views: number;
  total_watch_time: number;
  total_subscribers: number;
  total_impressions: number;
}

interface YoutubeVideo {
  video_id: string;
  title: string;
  publish_time: string;
  views: number;
  watch_time_hours: number;
  subscribers: number;
  impressions: number;
  impressions_ctr: number;
}

interface YoutubeTrafficSource {
  traffic_source: string;
  views: number;
  watch_time_hours: number;
  avg_view_duration: string;
  impressions: number;
  impressions_ctr: number;
}

export default function YoutubeAnalyticsDashboard() {
  const [stats, setStats] = useState<YoutubeStats | null>(null);
  const [videos, setVideos] = useState<YoutubeVideo[]>([]);
  const [trafficSources, setTrafficSources] = useState<YoutubeTrafficSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [timeRange, setTimeRange] = useState("all_time");
  const [tab, setTab] = useState<'analytics' | 'playlists'>('analytics');

  const [showAllVideosModal, setShowAllVideosModal] = useState(false);
  const [allVideos, setAllVideos] = useState<YoutubeVideo[]>([]);
  const [allVideosPage, setAllVideosPage] = useState(0);
  const [allVideosLoading, setAllVideosLoading] = useState(false);
  const [hasMoreVideos, setHasMoreVideos] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, videosRes, trafficRes] = await Promise.all([
        fetch(`http://localhost:8000/api/youtube-analytics/stats?time_range=${timeRange}`),
        fetch(`http://localhost:8000/api/youtube-analytics/videos?limit=10&time_range=${timeRange}`),
        fetch('http://localhost:8000/api/youtube-analytics/traffic-sources')
      ]);

      if (statsRes.ok) setStats(await statsRes.json());
      if (videosRes.ok) setVideos(await videosRes.json());
      if (trafficRes.ok) setTrafficSources(await trafficRes.json());
    } catch (error) {
      console.error("Failed to fetch YouTube analytics:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    if (showAllVideosModal) {
      handleOpenAllVideos();
    }
  }, [timeRange]);

  const fetchAllVideos = async (page: number, reset: boolean = false) => {
    setAllVideosLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/youtube-analytics/videos?limit=50&offset=${page * 50}&time_range=${timeRange}`);
      if (res.ok) {
        const data = await res.json();
        if (data.length < 50) setHasMoreVideos(false);
        setAllVideos(prev => reset ? data : [...prev, ...data]);
      }
    } catch (error) {
      console.error("Failed to fetch all videos", error);
    } finally {
      setAllVideosLoading(false);
    }
  };

  const handleOpenAllVideos = () => {
    setShowAllVideosModal(true);
    setAllVideosPage(0);
    setHasMoreVideos(true);
    fetchAllVideos(0, true);
  };

  const handleImport = async () => {
    setImporting(true);
    try {
      const res = await fetch('http://localhost:8000/api/youtube-analytics/import', {
        method: 'POST'
      });
      if (res.ok) {
        await fetchData();
      }
    } catch (error) {
      console.error("Import failed", error);
    } finally {
      setImporting(false);
    }
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num?.toString() || '0';
  };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin text-red-500">
          <RefreshCw size={32} />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Section header — matches AgentPipeline style */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 bg-gradient-to-b from-red-500 to-orange-500 rounded-full" />
          <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
            YouTube Analytics
          </h2>
          <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2 w-24" />
        </div>
        <div className="flex items-center gap-3">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-3 py-1.5 glass-card text-slate-300 text-xs rounded-lg hover:bg-white/10 transition-colors border border-white/5 uppercase tracking-wider bg-transparent focus:outline-none focus:ring-1 focus:ring-white/20"
          >
            <option value="all_time" className="bg-[#0f172a] text-slate-300">All Time</option>
            <option value="1_year" className="bg-[#0f172a] text-slate-300">1 Year</option>
            <option value="90_days" className="bg-[#0f172a] text-slate-300">90 Days</option>
            <option value="30_days" className="bg-[#0f172a] text-slate-300">30 Days</option>
            <option value="7_days" className="bg-[#0f172a] text-slate-300">7 Days</option>
          </select>
          <button
            onClick={handleImport}
            disabled={importing}
            className="flex items-center gap-2 px-3 py-1.5 glass-card text-slate-300 text-xs rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 border border-white/5 uppercase tracking-wider"
          >
            <RefreshCw size={14} className={importing ? "animate-spin" : ""} />
            {importing ? "Syncing..." : "Sync Data"}
          </button>
        </div>
      </div>

      {/* Page title */}
      <div className="flex items-center gap-3">
        <Youtube className="text-red-500" size={28} />
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">YouTube Analytics</h1>
          <p className="text-slate-500 text-sm mt-0.5">Channel performance and content metrics</p>
        </div>
      </div>

      {/* Sub-tabs: Analytics ↔ Playlists production board */}
      <div className="border-b border-white/5">
        <nav className="flex items-center gap-1 -mb-px">
          {([
            { key: 'analytics', label: 'Analytics', Icon: BarChart2 },
            { key: 'playlists', label: 'Playlists', Icon: ListVideo },
          ] as const).map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === key
                  ? 'border-red-500 text-red-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-white/10'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {tab === 'playlists' ? (
        <YoutubePlaylistBoard />
      ) : (
      <>
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-red-500/10 text-red-400 rounded-xl">
              <TrendingUp size={24} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Total Views</p>
              <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_views || 0)}</p>
            </div>
          </div>
        </div>
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-500/10 text-blue-400 rounded-xl">
              <Users size={24} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Subscribers Gained</p>
              <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_subscribers || 0)}</p>
            </div>
          </div>
        </div>
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-amber-500/10 text-amber-400 rounded-xl">
              <Clock size={24} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Watch Time (Hours)</p>
              <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_watch_time || 0)}</p>
            </div>
          </div>
        </div>
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-purple-500/10 text-purple-400 rounded-xl">
              <PlaySquare size={24} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">Videos Published</p>
              <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_videos || 0)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Channel strategy report + 30-day roadmap (qwen + live web trends) */}
      <YoutubeStrategyRoadmap timeRange={timeRange} />

      {/* Playlists & Trending Topics (YouTube Data API + qwen + live web trends) */}
      <YoutubePlaylistTrends />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Top Videos */}
        <div className="lg:col-span-2 glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
          <div className="p-6 border-b border-white/5 flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
              <PlaySquare size={20} className="text-slate-400" />
              Top Performing Videos
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-slate-400 font-medium">
                <tr>
                  <th className="px-6 py-4">Video</th>
                  <th className="px-6 py-4 text-right">Views</th>
                  <th className="px-6 py-4 text-right">CTR</th>
                  <th className="px-6 py-4 text-right">Subs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {videos.map((video) => (
                  <tr key={video.video_id} className="hover:bg-white/[0.05] transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-slate-200 line-clamp-1">{video.title}</div>
                      <div className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                        <Calendar size={12} />
                        {new Date(video.publish_time).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right font-medium text-white">{formatNumber(video.views)}</td>
                    <td className="px-6 py-4 text-right">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400">
                        {video.impressions_ctr}%
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right text-slate-400">{video.subscribers > 0 ? '+' : ''}{video.subscribers}</td>
                  </tr>
                ))}
                {videos.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                      No video data available. Sync data to see results.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="p-4 border-t border-white/5 bg-white/[0.01]">
            <button 
              onClick={handleOpenAllVideos}
              className="w-full py-2 flex items-center justify-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
            >
              View All Videos <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Traffic Sources */}
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden flex flex-col">
          <div className="p-6 border-b border-white/5 flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
              <BarChart2 size={20} className="text-slate-400" />
              Traffic Sources
            </h2>
          </div>
          <div className="p-6 flex-1 flex flex-col justify-center space-y-6">
            {trafficSources.length > 0 ? (
              trafficSources.slice(0, 5).map((source) => {
                const percentage = stats?.total_views 
                  ? Math.round((source.views / stats.total_views) * 100) 
                  : 0;
                
                return (
                  <div key={source.traffic_source} className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium text-slate-300">{source.traffic_source}</span>
                      <span className="text-slate-500">{percentage}%</span>
                    </div>
                    <div className="w-full bg-white/10 rounded-full h-2">
                      <div 
                        className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all duration-1000"
                        style={{ width: `${percentage}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center text-slate-500 py-8">
                No traffic source data available.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* All Videos Modal */}
      {showAllVideosModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="glass-card w-full max-w-5xl max-h-[90vh] rounded-2xl border border-white/10 flex flex-col overflow-hidden shadow-2xl">
            <div className="p-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
              <h2 className="text-xl font-bold flex items-center gap-2 text-white">
                <Youtube size={24} className="text-red-500" />
                All Uploaded Videos
              </h2>
              <button 
                onClick={() => setShowAllVideosModal(false)}
                className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#0f172a] sticky top-0 z-10 text-slate-400 font-medium shadow-md">
                  <tr>
                    <th className="px-6 py-4">Video</th>
                    <th className="px-6 py-4 text-right">Views</th>
                    <th className="px-6 py-4 text-right">Watch Time (hrs)</th>
                    <th className="px-6 py-4 text-right">CTR</th>
                    <th className="px-6 py-4 text-right">Subs</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-[#0b1120]">
                  {allVideos.map((video) => (
                    <tr key={`all-${video.video_id}`} className="hover:bg-white/[0.05] transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-medium text-slate-200 line-clamp-1">{video.title}</div>
                        <div className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                          <Calendar size={12} />
                          {new Date(video.publish_time).toLocaleDateString()}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right font-medium text-white">{formatNumber(video.views)}</td>
                      <td className="px-6 py-4 text-right text-slate-300">{video.watch_time_hours.toFixed(1)}</td>
                      <td className="px-6 py-4 text-right">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400">
                          {video.impressions_ctr}%
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-slate-400">{video.subscribers > 0 ? '+' : ''}{video.subscribers}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              
              <div className="p-6 flex justify-center border-t border-white/5">
                {hasMoreVideos ? (
                  <button
                    onClick={() => {
                      const nextPage = allVideosPage + 1;
                      setAllVideosPage(nextPage);
                      fetchAllVideos(nextPage);
                    }}
                    disabled={allVideosLoading}
                    className="px-6 py-2 glass-card text-white text-sm rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 border border-white/10 flex items-center gap-2"
                  >
                    {allVideosLoading && <RefreshCw size={14} className="animate-spin" />}
                    {allVideosLoading ? 'Loading...' : 'Load More'}
                  </button>
                ) : (
                  <span className="text-slate-500 text-sm">End of results</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
}
