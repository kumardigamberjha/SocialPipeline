"use client";

import React, { useState, useEffect } from 'react';
import { Youtube, TrendingUp, Clock, Users, PlaySquare, Calendar, RefreshCw, BarChart2, X, ChevronRight, ListVideo, Zap, CheckCircle, PlugZap, Swords } from 'lucide-react';
import { ApiError, request } from '@/lib/apiClient';
import YoutubePlaylistTrends from './YoutubePlaylistTrends';
import YoutubeStrategyRoadmap from './YoutubeStrategyRoadmap';
import YoutubePlaylistBoard from './YoutubePlaylistBoard';
import YoutubeLiveVideos from './YoutubeLiveVideos';
import CompetitorsTab from './competitors/CompetitorsTab';
import YoutubeAchievements from './YoutubeAchievements';

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

type ConnectStatus = 'checking' | 'need_connect' | 'need_reconnect' | 'ready';

export default function YoutubeAnalyticsDashboard() {
  const [stats, setStats] = useState<YoutubeStats | null>(null);
  const [videos, setVideos] = useState<YoutubeVideo[]>([]);
  const [trafficSources, setTrafficSources] = useState<YoutubeTrafficSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectStatus, setConnectStatus] = useState<ConnectStatus>('checking');
  const [connecting, setConnecting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [syncingAnalytics, setSyncingAnalytics] = useState(false);
  const [analyticsNeedsReconnect, setAnalyticsNeedsReconnect] = useState(false);
  const [timeRange, setTimeRange] = useState("all_time");
  const [tab, setTab] = useState<'analytics' | 'playlists' | 'live' | 'competitors'>('analytics');
  const [syncResult, setSyncResult] = useState<{ synced: number; new: number; updated: number; channel_title?: string } | null>(null);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  const [showAllVideosModal, setShowAllVideosModal] = useState(false);
  const [allVideos, setAllVideos] = useState<YoutubeVideo[]>([]);
  const [allVideosPage, setAllVideosPage] = useState(0);
  const [allVideosLoading, setAllVideosLoading] = useState(false);
  const [hasMoreVideos, setHasMoreVideos] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      // First check Google account connection status
      const googleStatus = await request<{ connected: boolean; email?: string }>(
        '/google/status'
      ).catch(() => ({ connected: false }));

      if (!googleStatus.connected) {
        setConnectStatus('need_connect');
        setLoading(false);
        return;
      }

      const statsData = await request<YoutubeStats>(`/youtube-analytics/stats?time_range=${timeRange}`);
      setStats(statsData);
      setConnectStatus('ready');

      const [videosRes, trafficRes] = await Promise.allSettled([
        request<YoutubeVideo[]>(`/youtube-analytics/videos?limit=10&time_range=${timeRange}`),
        request<YoutubeTrafficSource[]>(`/youtube-analytics/traffic-sources`),
      ]);
      if (videosRes.status === 'fulfilled') setVideos(videosRes.value);
      if (trafficRes.status === 'fulfilled') setTrafficSources(trafficRes.value);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 403) {
          setConnectStatus('need_reconnect');
        } else if (error.status === 401) {
          setConnectStatus('need_connect');
        } else {
          // Defaults to ready so empty analytics or server error shows dashboard instead of connect banner
          setConnectStatus('ready');
        }
      } else {
        setConnectStatus('ready');
      }
      console.error("Failed to fetch YouTube analytics:", error);
    } finally {
      setLoading(false);
    }
  };

  const connectGoogle = async () => {
    setConnecting(true);
    try {
      const { authorization_url } = await request<{ authorization_url?: string }>('/google/authorize?next=/youtube-analysis');
      if (authorization_url) window.location.href = authorization_url;
      else setConnecting(false);
    } catch {
      setConnecting(false);
    }
  };

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('google') === 'connected') {
      window.history.replaceState({}, document.title, window.location.pathname);
      handleImport();
    } else {
      fetchData();
    }
    if (showAllVideosModal) {
      handleOpenAllVideos();
    }
  }, [timeRange]);

  const fetchAllVideos = async (page: number, reset: boolean = false) => {
    setAllVideosLoading(true);
    try {
      const data = await request<YoutubeVideo[]>(
        `/youtube-analytics/videos?limit=50&offset=${page * 50}&time_range=${timeRange}`
      );
      if (data.length < 50) setHasMoreVideos(false);
      setAllVideos(prev => reset ? data : [...prev, ...data]);
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
    // Trigger live YouTube sync via Google OAuth
    setImporting(true);
    setSyncResult(null);
    try {
      const data = await request<{ synced: number; new: number; updated: number; channel_title?: string }>(
        '/youtube-analytics/sync-live',
        { method: 'POST' }
      );
      setSyncResult(data);
      setLastSynced(new Date().toLocaleTimeString());
      await fetchData();
      // Auto-dismiss toast after 6s
      setTimeout(() => setSyncResult(null), 6000);
    } catch (error) {
      console.error('Sync failed', error);
    } finally {
      setImporting(false);
    }
  };

  const handleSyncAnalytics = async () => {
    // Real impressions/CTR from the YouTube Analytics API — separate scope
    // and separate sync from the Data API "Sync from YouTube" above.
    setSyncingAnalytics(true);
    setAnalyticsNeedsReconnect(false);
    try {
      await request('/youtube-analytics/sync-analytics', { method: 'POST' });
      setLastSynced(new Date().toLocaleTimeString());
      await fetchData();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setAnalyticsNeedsReconnect(true);
      } else {
        console.error('CTR sync failed', error);
      }
    } finally {
      setSyncingAnalytics(false);
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

          {/* Last synced badge */}
          {lastSynced && (
            <span className="text-[10px] text-slate-500 hidden sm:block">
              Synced {lastSynced}
            </span>
          )}

          <button
            onClick={handleImport}
            disabled={importing}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs rounded-lg transition-colors disabled:opacity-50 border border-red-500/20 uppercase tracking-wider"
          >
            <Zap size={14} className={importing ? 'animate-pulse' : ''} />
            {importing ? 'Syncing…' : 'Sync from YouTube'}
          </button>

          {analyticsNeedsReconnect ? (
            <button
              onClick={connectGoogle}
              disabled={connecting}
              className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs rounded-lg transition-colors disabled:opacity-50 border border-amber-500/20 uppercase tracking-wider"
            >
              <PlugZap size={14} />
              {connecting ? 'Redirecting…' : 'Reconnect for CTR access'}
            </button>
          ) : (
            <button
              onClick={handleSyncAnalytics}
              disabled={syncingAnalytics}
              title="Pulls real impressions/CTR from the YouTube Analytics API — separate from the sync above"
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 text-xs rounded-lg transition-colors disabled:opacity-50 border border-blue-500/20 uppercase tracking-wider"
            >
              <TrendingUp size={14} className={syncingAnalytics ? 'animate-pulse' : ''} />
              {syncingAnalytics ? 'Syncing CTR…' : 'Sync CTR Data'}
            </button>
          )}
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

      {/* Sub-tabs */}
      <div className="border-b border-white/5">
        <nav className="flex items-center gap-1 -mb-px">
          {([
            { key: 'analytics', label: 'Analytics', Icon: BarChart2 },
            { key: 'live', label: 'Live Videos', Icon: Zap },
            { key: 'playlists', label: 'Playlists', Icon: ListVideo },
            { key: 'competitors', label: 'Competitors', Icon: Swords },
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

      {/* Sync result toast */}
      {syncResult && (
        <div className="flex items-center gap-3 px-4 py-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 text-sm animate-in fade-in slide-in-from-top-2 duration-300">
          <CheckCircle size={16} className="flex-shrink-0" />
          <span>
            Synced <strong>{syncResult.synced}</strong> videos
            {syncResult.channel_title ? ` from <em>${syncResult.channel_title}</em>` : ''}
            {' '}— <strong className="text-emerald-400">{syncResult.new} new</strong>, {syncResult.updated} updated
          </span>
        </div>
      )}

      {tab === 'competitors' ? (
        <CompetitorsTab />
      ) : tab === 'playlists' ? (
        <YoutubePlaylistBoard />
      ) : tab === 'live' ? (
        <div className="space-y-8">
          {/* Channel-level "what's working / underperforming / top priorities",
              web-trend informed — previously only shown on the Analytics tab. */}
          <YoutubeStrategyRoadmap timeRange={timeRange} />
          <YoutubeLiveVideos />
        </div>
      ) : (connectStatus === 'need_connect' || connectStatus === 'need_reconnect') ? (
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] py-16 text-center">
          <PlugZap className="w-8 h-8 text-amber-400 mx-auto mb-3" />
          <p className="text-slate-200 text-sm mb-1">
            {connectStatus === 'need_reconnect'
              ? 'Reconnect Google to grant YouTube access.'
              : 'Connect your Google account to see YouTube analytics.'}
          </p>
          <button
            onClick={connectGoogle}
            disabled={connecting}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-200 border border-blue-500/30 hover:bg-blue-600/30 transition-colors mt-3 disabled:opacity-50"
          >
            <PlugZap size={16} /> {connecting ? 'Redirecting…' : connectStatus === 'need_reconnect' ? 'Reconnect Google' : 'Connect Google'}
          </button>
        </div>
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

      {/* Achievements — Key Milestones + Top Performing Months */}
      <YoutubeAchievements />

      {/* Channel strategy report + 30-day roadmap (Gemini 3.6 Flash + live web trends) */}
      <YoutubeStrategyRoadmap timeRange={timeRange} />

      {/* Playlists & Trending Topics (YouTube Data API + Gemini 3.6 Flash + live web trends) */}
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
