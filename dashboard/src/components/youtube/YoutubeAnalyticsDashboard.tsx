"use client";

import React, { useState, useEffect } from 'react';
import {
  Youtube,
  TrendingUp,
  Clock,
  Users,
  PlaySquare,
  Calendar,
  RefreshCw,
  BarChart2,
  X,
  ChevronRight,
  ListVideo,
  Zap,
  CheckCircle,
  PlugZap,
  Swords,
  Trophy,
  Map,
  ThumbsUp,
  MessageSquare,
  Smartphone,
  Globe,
  FileSpreadsheet,
} from 'lucide-react';
import { ApiError, request } from '@/lib/apiClient';
import YoutubePlaylistTrends from './YoutubePlaylistTrends';
import YoutubeStrategyRoadmap from './YoutubeStrategyRoadmap';
import YoutubePlaylistBoard from './YoutubePlaylistBoard';
import YoutubeLiveVideos from './YoutubeLiveVideos';
import CompetitorsTab from './competitors/CompetitorsTab';
import YoutubeAchievements from './YoutubeAchievements';

/** A metric the backend could not measure renders as a dash, never as 0. */
const dash = (v: number | null | undefined, fmt: (n: number) => string) =>
  v === null || v === undefined ? "—" : fmt(v);

function formatDuration(secs?: number | null): string {
  if (!secs) return '';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatEngagement(views: number, likes?: number | null, comments?: number | null): string {
  if (!views || views <= 0) return '0%';
  const rate = (((likes || 0) + (comments || 0)) / views) * 100;
  return `${rate.toFixed(1)}%`;
}

interface YoutubeStats {
  total_videos: number;
  total_views: number;
  total_watch_time: number;
  total_subscribers: number;
  total_impressions: number | null;
}

interface YoutubeVideo {
  video_id: string;
  title: string;
  publish_time: string;
  duration_seconds?: number | null;
  views: number;
  likes?: number | null;
  comments?: number | null;
  thumbnail_url?: string | null;
  watch_time_hours: number | null;
  subscribers: number | null;
  impressions: number | null;
  impressions_ctr: number | null;
  average_view_percentage?: number | null;
  average_view_duration_seconds?: number | null;
}

interface YoutubeTrafficSource {
  traffic_source: string;
  views: number;
  watch_time_hours: number;
  avg_view_duration: string;
  impressions: number;
  impressions_ctr: number;
}

interface AudienceInsights {
  devices: { device: string; views: number; watch_time_hours: number }[];
  operating_systems: { os: string; views: number; watch_time_hours: number }[];
  demographics: { age_group: string; gender: string; percentage: number }[];
  geography: { country_code: string; views: number; watch_time_hours: number }[];
}

interface ReportingJob {
  id: string;
  reportTypeId: string;
  name: string;
  createTime?: string;
}

type ConnectStatus = 'checking' | 'need_connect' | 'need_reconnect' | 'ready';

export default function YoutubeAnalyticsDashboard() {
  const [stats, setStats] = useState<YoutubeStats | null>(null);
  const [videos, setVideos] = useState<YoutubeVideo[]>([]);
  const [trafficSources, setTrafficSources] = useState<YoutubeTrafficSource[]>([]);
  const [audienceInsights, setAudienceInsights] = useState<AudienceInsights | null>(null);
  const [reportingJobs, setReportingJobs] = useState<ReportingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectStatus, setConnectStatus] = useState<ConnectStatus>('checking');
  const [connecting, setConnecting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [syncingAnalytics, setSyncingAnalytics] = useState(false);
  const [analyticsNeedsReconnect, setAnalyticsNeedsReconnect] = useState(false);
  const [timeRange, setTimeRange] = useState("all_time");
  const [tab, setTab] = useState<'analytics' | 'playlists' | 'live' | 'competitors' | 'achievements' | 'strategy'>('analytics');
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

      const [videosRes, trafficRes, audienceRes, jobsRes] = await Promise.allSettled([
        request<YoutubeVideo[]>(`/youtube-analytics/videos?limit=10&time_range=${timeRange}`),
        request<YoutubeTrafficSource[]>(`/youtube-analytics/traffic-sources`),
        request<AudienceInsights>(`/youtube-analytics/audience-insights`),
        request<ReportingJob[]>(`/youtube-analytics/reporting/jobs`),
      ]);
      if (videosRes.status === 'fulfilled') setVideos(videosRes.value);
      if (trafficRes.status === 'fulfilled') setTrafficSources(trafficRes.value);
      if (audienceRes.status === 'fulfilled') setAudienceInsights(audienceRes.value);
      if (jobsRes.status === 'fulfilled') setReportingJobs(jobsRes.value);
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
              title="Pulls real watch-time, retention, subscriber gains & traffic sources from YouTube Analytics API"
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 text-xs rounded-lg transition-colors disabled:opacity-50 border border-blue-500/20 uppercase tracking-wider"
            >
              <TrendingUp size={14} className={syncingAnalytics ? 'animate-pulse' : ''} />
              {syncingAnalytics ? 'Syncing Analytics…' : 'Sync Analytics'}
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
            { key: 'achievements', label: 'Achievements', Icon: Trophy },
            { key: 'strategy', label: 'Strategy & Roadmap', Icon: Map },
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

      {tab === 'achievements' ? (
        <YoutubeAchievements />
      ) : tab === 'strategy' ? (
        <div className="space-y-8">
          {/* Channel strategy report + 30-day roadmap (Gemini Flash + live web trends) */}
          <YoutubeStrategyRoadmap timeRange={timeRange} />
          {/* Playlists & Trending Topics */}
          <YoutubePlaylistTrends />
        </div>
      ) : tab === 'competitors' ? (
        <CompetitorsTab />
      ) : tab === 'playlists' ? (
        <YoutubePlaylistBoard />
      ) : tab === 'live' ? (
        <YoutubeLiveVideos />
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
      {/* Time Range Filter Bar + Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-1.5 p-1 bg-white/[0.03] border border-white/5 rounded-xl">
          {([
            { key: '7_days', label: '7 Days' },
            { key: '30_days', label: '30 Days' },
            { key: '90_days', label: '90 Days' },
            { key: '1_year', label: '1 Year' },
            { key: 'all_time', label: 'Lifetime' },
          ] as const).map(({ key, label }) => {
            const isActive = timeRange === key || (key === 'all_time' && timeRange === 'lifetime');
            return (
              <button
                key={key}
                onClick={() => setTimeRange(key)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all ${
                  isActive
                    ? 'bg-red-500/20 text-red-300 border border-red-500/30 shadow-sm shadow-red-500/10'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <div className="text-xs text-slate-500 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Live YouTube Channel Sync</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow hover:border-white/10">
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
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow hover:border-white/10">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-500/10 text-blue-400 rounded-xl">
              <Users size={24} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-400">
                {timeRange === 'all_time' || timeRange === 'lifetime' ? 'Total Subscribers' : 'Subscribers Gained'}
              </p>
              <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_subscribers || 0)}</p>
            </div>
          </div>
        </div>
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow hover:border-white/10">
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
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] transition-shadow hover:border-white/10">
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


      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Top Videos */}
        <div className="lg:col-span-2 glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
          <div className="p-6 border-b border-white/5 flex items-center justify-between">
            <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
              <PlaySquare size={20} className="text-slate-400" />
              Top Performing Videos
            </h2>
            <span className="text-xs text-slate-500 font-medium">Sorted by Views</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-slate-400 font-medium text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3.5">Video</th>
                  <th className="px-4 py-3.5 text-right">Views</th>
                  <th className="px-4 py-3.5 text-right">Likes</th>
                  <th className="px-4 py-3.5 text-right">Comments</th>
                  <th className="px-4 py-3.5 text-right">Watch Time</th>
                  <th className="px-4 py-3.5 text-right" title="Audience Retention rate from YouTube Analytics">Retention</th>
                  <th className="px-4 py-3.5 text-right" title="Net subscribers gained from this video">Subscribers</th>
                  <th className="px-4 py-3.5 text-right">Engage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {videos.map((video) => {
                  const duration = formatDuration(video.duration_seconds);
                  const engRate = formatEngagement(video.views, video.likes, video.comments);
                  const thumbSrc = video.thumbnail_url || `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`;
                  return (
                    <tr key={video.video_id} className="hover:bg-white/[0.05] transition-colors">
                      <td className="px-5 py-4 min-w-[200px] max-w-[260px]">
                        <div className="flex items-center gap-3">
                          <img
                            src={thumbSrc}
                            alt=""
                            onError={(e) => {
                              (e.currentTarget as HTMLImageElement).src = `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`;
                            }}
                            className="w-12 h-8 rounded-lg object-cover flex-shrink-0 bg-slate-800 border border-white/10"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="font-medium text-slate-200 truncate text-xs sm:text-sm" title={video.title}>
                              {video.title}
                            </div>
                            <div className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-2">
                              <span className="flex items-center gap-1 whitespace-nowrap">
                                <Calendar size={11} />
                                {new Date(video.publish_time).toLocaleDateString()}
                              </span>
                              {duration && (
                                <span className="flex items-center gap-1 text-slate-400 whitespace-nowrap">
                                  <Clock size={11} />
                                  {duration}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right font-semibold text-white whitespace-nowrap">
                        {formatNumber(video.views)}
                      </td>
                      <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1 text-xs">
                          <ThumbsUp size={12} className="text-amber-400/80" />
                          {formatNumber(video.likes ?? 0)}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1 text-xs">
                          <MessageSquare size={12} className="text-blue-400/80" />
                          {formatNumber(video.comments ?? 0)}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap text-xs">
                        {video.watch_time_hours != null
                          ? `${video.watch_time_hours.toFixed(1)}h`
                          : dash(null, (n) => `${n}h`)}
                      </td>
                      <td className="px-4 py-4 text-right whitespace-nowrap">
                        {video.average_view_percentage != null && video.average_view_percentage > 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-500/10 text-cyan-300 border border-cyan-500/20" title="Audience Retention % from YouTube Analytics">
                            {video.average_view_percentage.toFixed(1)}%
                          </span>
                        ) : video.impressions_ctr != null && video.impressions_ctr > 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title="Impressions Click-Through Rate">
                            {video.impressions_ctr}% CTR
                          </span>
                        ) : (
                          <span className="text-slate-500 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-4 text-right whitespace-nowrap text-xs">
                        {video.subscribers != null && video.subscribers > 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 font-semibold border border-emerald-500/20 shadow-xs">
                            +{video.subscribers}
                          </span>
                        ) : video.subscribers != null && video.subscribers < 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-red-500/10 text-red-300 font-semibold border border-red-500/20">
                            {video.subscribers}
                          </span>
                        ) : video.subscribers != null ? (
                          <span className="text-slate-400">0</span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-4 text-right whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${
                          parseFloat(engRate) >= 1.0
                            ? 'bg-purple-500/15 text-purple-300 border-purple-500/30 font-semibold'
                            : 'bg-slate-500/10 text-slate-400 border-white/5'
                        }`}>
                          {engRate}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {videos.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-6 py-8 text-center text-slate-500">
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
              className="w-full py-2 flex items-center justify-center gap-2 text-sm text-slate-400 hover:text-white transition-colors cursor-pointer"
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
              (() => {
                const totalTrafficViews = trafficSources.reduce((acc, s) => acc + (s.views || 0), 0);
                return trafficSources.slice(0, 6).map((source) => {
                  const percentage = totalTrafficViews > 0
                    ? Math.round((source.views / totalTrafficViews) * 100)
                    : 0;

                  return (
                    <div key={source.traffic_source} className="space-y-1.5">
                      <div className="flex justify-between text-xs sm:text-sm">
                        <span className="font-medium text-slate-300 truncate pr-2">{source.traffic_source}</span>
                        <span className="text-slate-400 font-semibold flex-shrink-0">
                          {percentage}% <span className="text-xs text-slate-500 font-normal">({formatNumber(source.views)})</span>
                        </span>
                      </div>
                      <div className="w-full bg-white/10 rounded-full h-1.5">
                        <div
                          className="bg-gradient-to-r from-red-500 via-orange-500 to-purple-500 h-1.5 rounded-full transition-all duration-1000"
                          style={{ width: `${percentage}%` }}
                        ></div>
                      </div>
                    </div>
                  );
                });
              })()
            ) : (
              <div className="text-center text-slate-500 py-8">
                No traffic source data available.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Audience Insights & YouTube Reporting API Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Device Distribution */}
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2 text-white">
              <Smartphone size={16} className="text-blue-400" />
              Device Distribution
            </h3>
            <span className="text-[11px] text-slate-500 font-medium">Last 90 Days</span>
          </div>
          <div className="space-y-3 pt-2">
            {audienceInsights?.devices && audienceInsights.devices.length > 0 ? (
              (() => {
                const totalDevViews = audienceInsights.devices.reduce((acc, d) => acc + d.views, 0);
                return audienceInsights.devices.map((dev) => {
                  const pct = totalDevViews > 0 ? Math.round((dev.views / totalDevViews) * 100) : 0;
                  return (
                    <div key={dev.device} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-300 font-medium">{dev.device}</span>
                        <span className="text-slate-400 font-semibold">
                          {pct}% <span className="text-slate-500 font-normal">({formatNumber(dev.views)} views)</span>
                        </span>
                      </div>
                      <div className="w-full bg-white/10 rounded-full h-1.5">
                        <div
                          className="bg-gradient-to-r from-blue-500 to-indigo-500 h-1.5 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                });
              })()
            ) : (
              <p className="text-xs text-slate-500 py-4 text-center">Sync channel to view device breakdown.</p>
            )}
          </div>
        </div>

        {/* Viewer Demographics */}
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2 text-white">
              <Users size={16} className="text-purple-400" />
              Viewer Demographics
            </h3>
            <span className="text-[11px] text-slate-500 font-medium">Age & Gender</span>
          </div>
          <div className="space-y-3 pt-2">
            {audienceInsights?.demographics && audienceInsights.demographics.length > 0 ? (
              audienceInsights.demographics.slice(0, 5).map((demo, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 font-medium">
                      Age {demo.age_group} <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 ml-1">{demo.gender}</span>
                    </span>
                    <span className="text-purple-300 font-semibold">{demo.percentage}%</span>
                  </div>
                  <div className="w-full bg-white/10 rounded-full h-1.5">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-pink-500 h-1.5 rounded-full"
                      style={{ width: `${Math.min(100, demo.percentage * 2)}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500 py-4 text-center">Demographic data will appear with more audience traffic.</p>
            )}
          </div>
        </div>

        {/* Reporting API & Geographies */}
        <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2 text-white">
              <Globe size={16} className="text-emerald-400" />
              Top Geographies & Jobs
            </h3>
            <span className="text-[11px] text-slate-500 font-medium">YouTube Reporting API</span>
          </div>

          <div className="space-y-3 pt-1">
            {audienceInsights?.geography && audienceInsights.geography.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {audienceInsights.geography.slice(0, 4).map((geo) => (
                  <div key={geo.country_code} className="p-2 rounded-xl bg-white/[0.03] border border-white/5 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-200">{geo.country_code}</span>
                    <span className="text-[11px] text-slate-400">{formatNumber(geo.views)} views</span>
                  </div>
                ))}
              </div>
            ) : null}

            {/* Scheduled Reporting Jobs Status */}
            <div className="pt-2 border-t border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <FileSpreadsheet size={13} className="text-emerald-400" />
                  Scheduled Bulk Jobs
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                  {reportingJobs.length} Active
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {reportingJobs.slice(0, 4).map((job) => (
                  <span key={job.id} className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-300 border border-white/5">
                    {job.name.replace("Channel ", "").replace(" Report", "")}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* All Videos Modal */}
      {showAllVideosModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="glass-card w-full max-w-6xl max-h-[90vh] rounded-2xl border border-white/10 flex flex-col overflow-hidden shadow-2xl">
            <div className="p-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
              <h2 className="text-xl font-bold flex items-center gap-2 text-white">
                <Youtube size={24} className="text-red-500" />
                All Uploaded Videos
              </h2>
              <button 
                onClick={() => setShowAllVideosModal(false)}
                className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors cursor-pointer"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#0f172a] sticky top-0 z-10 text-slate-400 font-medium text-xs uppercase tracking-wider shadow-md">
                  <tr>
                    <th className="px-5 py-3.5">Video</th>
                    <th className="px-4 py-3.5 text-right">Views</th>
                    <th className="px-4 py-3.5 text-right">Likes</th>
                    <th className="px-4 py-3.5 text-right">Comments</th>
                    <th className="px-4 py-3.5 text-right">Watch Time</th>
                    <th className="px-4 py-3.5 text-right" title="Audience Retention rate from YouTube Analytics">Retention</th>
                    <th className="px-4 py-3.5 text-right" title="Net subscribers gained from this video">Subscribers</th>
                    <th className="px-4 py-3.5 text-right">Engage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-[#0b1120]">
                  {allVideos.map((video) => {
                    const duration = formatDuration(video.duration_seconds);
                    const engRate = formatEngagement(video.views, video.likes, video.comments);
                    const thumbSrc = video.thumbnail_url || `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`;
                    return (
                      <tr key={`all-${video.video_id}`} className="hover:bg-white/[0.05] transition-colors">
                        <td className="px-5 py-4 min-w-[200px] max-w-[280px]">
                          <div className="flex items-center gap-3">
                            <img
                              src={thumbSrc}
                              alt=""
                              onError={(e) => {
                                (e.currentTarget as HTMLImageElement).src = `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`;
                              }}
                              className="w-12 h-8 rounded-lg object-cover flex-shrink-0 bg-slate-800 border border-white/10"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="font-medium text-slate-200 truncate text-xs sm:text-sm" title={video.title}>
                                {video.title}
                              </div>
                              <div className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-2">
                                <span className="flex items-center gap-1 whitespace-nowrap">
                                  <Calendar size={11} />
                                  {new Date(video.publish_time).toLocaleDateString()}
                                </span>
                                {duration && (
                                  <span className="flex items-center gap-1 text-slate-400 whitespace-nowrap">
                                    <Clock size={11} />
                                    {duration}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-right font-semibold text-white whitespace-nowrap">
                          {formatNumber(video.views)}
                        </td>
                        <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap">
                          <span className="inline-flex items-center gap-1 text-xs">
                            <ThumbsUp size={12} className="text-amber-400/80" />
                            {formatNumber(video.likes ?? 0)}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap">
                          <span className="inline-flex items-center gap-1 text-xs">
                            <MessageSquare size={12} className="text-blue-400/80" />
                            {formatNumber(video.comments ?? 0)}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right text-slate-300 whitespace-nowrap text-xs">
                          {video.watch_time_hours != null
                            ? `${video.watch_time_hours.toFixed(1)}h`
                            : dash(null, (n) => `${n}h`)}
                        </td>
                        <td className="px-4 py-4 text-right whitespace-nowrap">
                          {video.average_view_percentage != null && video.average_view_percentage > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-500/10 text-cyan-300 border border-cyan-500/20" title="Audience Retention % from YouTube Analytics">
                              {video.average_view_percentage.toFixed(1)}%
                            </span>
                          ) : video.impressions_ctr != null && video.impressions_ctr > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title="Impressions Click-Through Rate">
                              {video.impressions_ctr}% CTR
                            </span>
                          ) : (
                            <span className="text-slate-500 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-right whitespace-nowrap text-xs">
                          {video.subscribers != null && video.subscribers > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 font-semibold border border-emerald-500/20 shadow-xs">
                              +{video.subscribers}
                            </span>
                          ) : video.subscribers != null && video.subscribers < 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-red-500/10 text-red-300 font-semibold border border-red-500/20">
                              {video.subscribers}
                            </span>
                          ) : video.subscribers != null ? (
                            <span className="text-slate-400">0</span>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-right whitespace-nowrap">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${
                            parseFloat(engRate) >= 1.0
                              ? 'bg-purple-500/15 text-purple-300 border-purple-500/30 font-semibold'
                              : 'bg-slate-500/10 text-slate-400 border-white/5'
                          }`}>
                            {engRate}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
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
                    className="px-6 py-2 glass-card text-white text-sm rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 border border-white/10 flex items-center gap-2 cursor-pointer"
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
