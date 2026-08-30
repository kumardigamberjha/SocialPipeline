"use client";

import Link from "next/link";
import React, { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { request } from '@/lib/apiClient';
import InstagramAchievements from './InstagramAchievements';
import {
  Instagram,
  Trophy,
  Users,
  Film,
  Calendar,
  RefreshCw,
  BarChart2,
  X,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Layers,
  ExternalLink,
  Tag,
  Bookmark,
  Eye,
  Wand2,
  CheckCircle2,
  CalendarRange,
  Info,
  AlertTriangle,
} from 'lucide-react';

interface InstagramProfile {
  handle: string | null;
  brand_name: string;
  url: string | null;
  bio: string;
  followers: number;
  following: number;
  total_posts: number;
  /** Mean of the per-post rates that could be computed; null when none could. */
  avg_engagement_rate: number | null;
  profile_picture_url?: string;
  synced_at?: string | null;
  source?: string;
}

// `null` means Meta did not report the metric for this account — not zero.
// Instagram account insights need a Business/Creator account and the insights
// scope, and several metrics were dropped in newer API versions. Rendering a
// missing measurement as 0 is what made this page look precise and wrong.
interface InstagramStats {
  time_range: string;
  total_followers: number;
  followers_gained: number | null;
  total_reach: number | null;
  total_views: number | null;
  total_impressions: number | null;
  accounts_engaged: number | null;
  total_interactions: number | null;
  profile_visits: number | null;
  link_clicks: number | null;
  posts_published: number;
  total_reels_published: number;
  total_carousels_published: number;
  total_images_published: number;
  avg_reel_views: number | null;
  avg_carousel_saves: number | null;
  avg_engagement_rate: number | null;
  /** False for all_time: the insights endpoint is windowed, so that range
      cannot have account metrics regardless of permissions. */
  insights_supported: boolean;
  insights_available: boolean;
  /** The snapshot behind this predates insights provenance — re-sync for real figures. */
  stale?: boolean;
}

interface InstagramPost {
  id: string;
  title: string;
  type: 'reel' | 'carousel' | 'single';
  publish_time: string;
  // Exact for every post — straight off the media edge.
  likes: number;
  comments: number;
  // Insights-derived, so null when Meta withheld them.
  views: number | null;
  shares: number | null;
  saves: number | null;
  reach: number | null;
  /** Percent as a number now, where this used to be the string "6.2%". */
  engagement_rate: number | null;
  insights_available: boolean;
  metrics_updated_at: string;
  permalink: string;
  caption: string;
}

interface HashtagItem {
  tag: string;
  posts_used: number;
  posts_measured: number;
  avg_reach: number | null;
  score: number | null;
  category: string;
}

const HASHTAGS_PER_PAGE = 10;

// The window each stats block covers, so a KPI subtitle names its own scope
// instead of the vague "this period" that used to sit under every range.
const RANGE_LABELS: Record<string, string> = {
  "7_days": "last 7 days",
  "30_days": "last 30 days",
  "90_days": "last 90 days",
  "all_time": "all time",
};

const PALETTES = [
  "void_purple", "cyber_teal", "neon_coral", "solar_amber",
  "ice_blue", "forest", "crimson", "pure_dark",
] as const;

const LAYOUTS = [
  "bottom_hero", "top_title", "center_bold",
  "split_left", "minimal", "full_text",
] as const;


export default function InstagramAnalyticsDashboard() {
  const [profile, setProfile] = useState<InstagramProfile | null>(null);
  const [stats, setStats] = useState<InstagramStats | null>(null);
  const [posts, setPosts] = useState<InstagramPost[]>([]);
  const [hashtags, setHashtags] = useState<HashtagItem[]>([]);
  const [hashtagPage, setHashtagPage] = useState(0);
  const [strategy, setStrategy] = useState<any>(null);
  const [roadmap, setRoadmap] = useState<any>(null);

  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [timeRange, setTimeRange] = useState("30_days");
  const [tab, setTab] = useState<'analytics' | 'achievements' | 'strategy'>('analytics');
  const [formatFilter, setFormatFilter] = useState<'all' | 'reel' | 'carousel'>('all');

  const [isGeneratingStrategy, setIsGeneratingStrategy] = useState(false);
  const [isGeneratingRoadmap, setIsGeneratingRoadmap] = useState(false);
  const [selectedRoadmapItems, setSelectedRoadmapItems] = useState<Set<string>>(new Set());
  const [isAddingRoadmapToPlan, setIsAddingRoadmapToPlan] = useState(false);
  const [roadmapResult, setRoadmapResult] = useState<
    { plan_id: string; created: number; skipped: { title: string; reason: string }[] } | null
  >(null);

  // Quick Generator state
  const [genTopic, setGenTopic] = useState("Build AI Agents with CrewAI & Python");
  const [genPalette, setGenPalette] = useState("void_purple");
  const [genLayout, setGenLayout] = useState("bottom_hero");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<any>(null);

  // Which single post is being re-read from Meta right now, and the last
  // per-post failure (kept out of the console so the user actually sees it).
  const [refreshingPostId, setRefreshingPostId] = useState<string | null>(null);
  const [postError, setPostError] = useState<string | null>(null);

  const [authStatus, setAuthStatus] = useState<any>(null);
  const [oauthBanner, setOauthBanner] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const searchParams = useSearchParams();
  const router = useRouter();

  const fetchData = async () => {
    setLoading(true);
    try {
      const [profRes, statsRes, postsRes, tagsRes, authRes, strategyRes, roadmapRes] =
        await Promise.allSettled([
          request<InstagramProfile>('/instagram-analytics/profile'),
          request<InstagramStats>(`/instagram-analytics/stats?time_range=${timeRange}`),
          request<InstagramPost[]>(`/instagram-analytics/posts?limit=10&format_filter=${formatFilter}`),
          request<HashtagItem[]>('/instagram-analytics/hashtags'),
          request<any>('/instagram-auth/status'),
          request<any>('/instagram-analytics/strategy'),
          request<any>('/instagram-analytics/roadmap'),
        ]);

      if (profRes.status === 'fulfilled') setProfile(profRes.value);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
      if (postsRes.status === 'fulfilled') setPosts(postsRes.value);
      if (tagsRes.status === 'fulfilled') {
        setHashtags(tagsRes.value);
        setHashtagPage(0);
      }
      if (authRes.status === 'fulfilled') setAuthStatus(authRes.value);
      // Only restore a saved brief/roadmap if it actually has content — the
      // "nothing generated yet" shape is a valid, empty response.
      if (strategyRes.status === 'fulfilled' && strategyRes.value?.executive_summary) {
        setStrategy(strategyRes.value);
      }
      if (roadmapRes.status === 'fulfilled' && roadmapRes.value?.weeks?.length) {
        setRoadmap(roadmapRes.value);
      }
    } catch (error) {
      console.error("Failed to fetch Instagram analytics:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnectInstagram = async () => {
    try {
      const data = await request<{ authorization_url?: string }>('/instagram-auth/url');
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (err) {
      console.error("Failed to fetch auth URL", err);
      setOauthBanner({
        type: 'error',
        msg: '⚠️ Could not start Instagram connection. Please try again in a moment.'
      });
      setTimeout(() => setOauthBanner(null), 8000);
    }
  };

  const handleRefreshToken = async () => {
    try {
      await request('/instagram-auth/refresh', { method: 'POST' });
      alert("Instagram Token Refreshed for 60 days!");
      fetchData();
    } catch (err) {
      console.error("Failed to refresh token", err);
    }
  };

  const handleDisconnectInstagram = async () => {
    try {
      await request('/instagram-auth/disconnect', { method: 'DELETE' });
      fetchData();
    } catch (err) {
      console.error("Failed to disconnect Instagram", err);
    }
  };

  useEffect(() => {
    fetchData();
  }, [timeRange, formatFilter]);

  // Detect OAuth return from Instagram (e.g. ?instagram=connected)
  useEffect(() => {
    const igParam = searchParams.get('instagram');
    const msg = searchParams.get('msg');
    const expiresAt = searchParams.get('expires_at');
    if (!igParam) return;

    if (igParam === 'connected') {
      // Safe days calculation — only use if parsed date is in the future
      let daysLeft = 60;
      if (expiresAt) {
        const exp = new Date(expiresAt).getTime();
        const diff = Math.round((exp - Date.now()) / 86400000);
        if (diff > 0 && diff <= 65) daysLeft = diff;
      }
      setOauthBanner({
        type: 'success',
        msg: `✅ Instagram connected! Token valid for ~${daysLeft} days. Syncing data...`
      });
      // Clean the URL params
      router.replace('/instagram-analysis', { scroll: false });
      // POST /sync to populate Redis + DB from the fresh token, THEN fetch from cache
      setSyncing(true);
      request('/instagram-analytics/sync', { method: 'POST' })
        .then(() => fetchData())
        .catch(() => fetchData())
        .finally(() => setSyncing(false));
      setTimeout(() => setOauthBanner(null), 12000);
    } else if (igParam === 'error') {
      setOauthBanner({
        type: 'error',
        msg: `❌ OAuth Error: ${msg || 'Authorization failed. Please try again.'}`
      });
      router.replace('/instagram-analysis', { scroll: false });
      setTimeout(() => setOauthBanner(null), 15000);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);


  const handleSync = async () => {
    setSyncing(true);
    try {
      // POST /sync triggers live Instagram API fetch → saves to the cache + DB
      await request('/instagram-analytics/sync', { method: 'POST' });
    } catch (err) {
      console.error('Sync request failed:', err);
    }
    // Re-fetch dashboard data from cache (now freshly populated)
    await fetchData();
    setSyncing(false);
  };


  const handleGenerateStrategy = async () => {
    setIsGeneratingStrategy(true);
    try {
      const data = await request<any>(`/instagram-analytics/strategy?time_range=${timeRange}`, { method: 'POST' });
      setStrategy(data);
    } catch (err) {
      console.error("Failed to generate AI strategy", err);
    } finally {
      setIsGeneratingStrategy(false);
    }
  };

  const handleGenerateRoadmap = async () => {
    setIsGeneratingRoadmap(true);
    try {
      const data = await request<any>('/instagram-analytics/roadmap?weeks=4', { method: 'POST' });
      setRoadmap(data);
      setSelectedRoadmapItems(new Set());
    } catch (err) {
      console.error("Failed to generate AI roadmap", err);
    } finally {
      setIsGeneratingRoadmap(false);
    }
  };

  const toggleRoadmapItem = (key: string) => {
    setSelectedRoadmapItems((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleAddRoadmapToPlan = async (mode: 'all' | 'selected') => {
    if (!roadmap?.weeks) return;
    const items: {
      title: string; type: string; date: string; caption: string; image_prompt: string;
      rationale: string; week_number: number;
    }[] = [];
    for (const week of roadmap.weeks) {
      for (let idx = 0; idx < (week.items?.length ?? 0); idx++) {
        const key = `${week.week_number}-${idx}`;
        if (mode === 'selected' && !selectedRoadmapItems.has(key)) continue;
        const item = week.items[idx];
        items.push({
          title: item.title,
          type: item.type,
          date: item.date,
          caption: [item.tags, item.call_to_action].filter(Boolean).join('\n\n'),
          image_prompt: item.visual_prompt || '',
          rationale: item.rationale || '',
          week_number: week.week_number,
        });
      }
    }
    if (items.length === 0) return;

    setIsAddingRoadmapToPlan(true);
    try {
      // Same endpoint shape as YouTube's roadmap → plan: items already in a
      // plan or already published come back as `skipped` rather than being
      // duplicated, so re-running the roadmap is safe.
      const res = await request<{
        plan_id: string;
        created: unknown[];
        skipped: { title: string; reason: string }[];
      }>('/instagram-analytics/roadmap/add-to-plan', {
        method: 'POST',
        body: JSON.stringify({ items }),
      });
      setRoadmapResult({
        plan_id: res.plan_id,
        created: res.created.length,
        skipped: res.skipped ?? [],
      });
      setSelectedRoadmapItems(new Set());
    } catch (err) {
      console.error("Failed to add roadmap items to the planner", err);
    } finally {
      setIsAddingRoadmapToPlan(false);
    }
  };

  const handleGenerateImage = async () => {
    setIsGenerating(true);
    setGeneratedResult(null);
    try {
      const data = await request<any>('/instagram/generate', {
        method: 'POST',
        body: JSON.stringify({
          topic: genTopic,
          palette: genPalette,
          layout: genLayout,
          model: 'gemini_flash'
        })
      });
      setGeneratedResult(data);
    } catch (err) {
      console.error("Generation failed", err);
    } finally {
      setIsGenerating(false);
    }
  };

  const formatNumber = (num: number) => {
    if (!num) return '0';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  };

  // An em dash for an absent measurement. `formatNumber(x || 0)` would print
  // "0", which is a claim the data does not support — the whole point of the
  // backend returning null.
  const formatMetric = (num: number | null | undefined) =>
    num === null || num === undefined ? '—' : formatNumber(num);

  const formatRate = (rate: number | null | undefined) =>
    rate === null || rate === undefined ? '—' : `${rate}%`;

  /** Re-read one post's live metrics without a whole-account sync. */
  const handleRefreshPost = async (postId: string) => {
    setRefreshingPostId(postId);
    setPostError(null);
    try {
      const res = await request<{
        post: InstagramPost;
        stats: InstagramStats;
        stats_by_range: Record<string, InstagramStats>;
        hashtags: HashtagItem[];
        profile: InstagramProfile;
      }>(`/instagram-analytics/posts/${encodeURIComponent(postId)}/refresh`, {
        method: 'POST',
      });
      // Patch in place: re-fetching the list would drop the user's scroll
      // position and their format filter for a single-row change.
      setPosts((prev) => prev.map((p) => (p.id === postId ? res.post : p)));
      // The response carries every range; take the one on screen, not the
      // default, or a 7-day view would silently start showing 30-day numbers.
      const forRange = res.stats_by_range?.[timeRange] ?? res.stats;
      if (forRange) setStats(forRange);
      if (res.hashtags) setHashtags(res.hashtags);
      if (res.profile) setProfile((prev) => ({ ...prev, ...res.profile }));
    } catch (err) {
      setPostError(err instanceof Error ? err.message : 'Could not refresh that post.');
    } finally {
      setRefreshingPostId(null);
    }
  };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin text-pink-500">
          <RefreshCw size={32} />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
      {/* OAuth Return Banner */}
      {oauthBanner && (
        <div className={`flex items-center justify-between gap-4 px-5 py-3.5 rounded-2xl border text-sm font-medium animate-in slide-in-from-top-2 ${
          oauthBanner.type === 'success'
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
            : 'bg-red-500/10 border-red-500/30 text-red-300'
        }`}>
          <span>{oauthBanner.msg}</span>
          <button
            onClick={() => setOauthBanner(null)}
            className="text-current opacity-60 hover:opacity-100 transition-opacity flex-shrink-0"
          >
            <X size={16} />
          </button>
        </div>
      )}
      {/* Section Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 bg-gradient-to-b from-pink-500 via-purple-500 to-amber-500 rounded-full" />
          <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
            Instagram Engine
          </h2>
          <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2 w-24" />
        </div>
        <div className="flex items-center gap-3">
          {/* Planning lives in one place now — this page analyses, the planner plans. */}
          <Link
            href="/planner?platform=instagram&view=board"
            className="flex items-center gap-2 px-3 py-1.5 glass-card text-pink-300 text-xs rounded-lg hover:bg-pink-500/10 transition-colors border border-pink-500/20 uppercase tracking-wider"
          >
            <CalendarRange size={14} />
            Content Planner
          </Link>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-3 py-1.5 glass-card text-slate-300 text-xs rounded-lg hover:bg-white/10 transition-colors border border-white/5 uppercase tracking-wider bg-transparent focus:outline-none focus:ring-1 focus:ring-white/20"
          >
            <option value="7_days" className="bg-[#0f172a] text-slate-300">7 Days</option>
            <option value="30_days" className="bg-[#0f172a] text-slate-300">30 Days</option>
            <option value="90_days" className="bg-[#0f172a] text-slate-300">90 Days</option>
            <option value="all_time" className="bg-[#0f172a] text-slate-300">All Time</option>
          </select>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-3 py-1.5 glass-card text-slate-300 text-xs rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 border border-white/5 uppercase tracking-wider"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Syncing..." : "Sync Metrics"}
          </button>
        </div>
      </div>

      {/* Profile Header Banner */}
      <div className="glass-card p-6 rounded-3xl border border-white/10 bg-gradient-to-r from-purple-900/20 via-pink-900/20 to-slate-900/40 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-pink-500/10 to-purple-600/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
          <div className="flex items-center gap-5">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-amber-500 via-pink-500 to-purple-600 p-[2px] shadow-xl flex-shrink-0">
              <div className="w-full h-full bg-[#0b0f19] rounded-[14px] flex items-center justify-center">
                <Instagram className="text-pink-400" size={32} />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-white tracking-tight">{profile?.brand_name || "Not connected"}</h1>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-pink-500/10 text-pink-300 border border-pink-500/20">
                  {profile?.handle || "Connect your account"}
                </span>

                {authStatus && (
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold flex items-center gap-1.5 ${
                    authStatus.is_valid
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                  }`}>
                    <CheckCircle2 size={12} />
                    {authStatus.is_valid
                      ? `Connected • ${authStatus.days_remaining}d left`
                      : 'Token Action Needed'}
                  </span>
                )}
              </div>
              <p className="text-slate-400 text-xs sm:text-sm mt-1 max-w-2xl leading-relaxed">
                {profile?.bio || "🤖 AI, Python & Full-Stack Development Hub | Building Autonomous Agents & SaaS in India 🇮🇳"}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleConnectInstagram}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-pink-500 to-purple-600 hover:from-pink-600 hover:to-purple-700 text-white text-xs font-semibold rounded-xl shadow-lg transition-all disabled:opacity-50"
            >
              <Instagram size={14} />
              Connect Instagram (OAuth)
            </button>
            {authStatus?.is_valid && (
              <>
                <button
                  onClick={handleRefreshToken}
                  disabled={loading}
                  className="flex items-center gap-2 px-3 py-2 glass-card border border-emerald-500/30 hover:bg-emerald-500/10 text-emerald-300 text-xs font-semibold rounded-xl transition-all disabled:opacity-50"
                >
                  <RefreshCw size={12} />
                  Refresh 60-Day Token
                </button>
                <button
                  onClick={handleDisconnectInstagram}
                  disabled={loading}
                  className="flex items-center gap-2 px-3 py-2 glass-card border border-white/10 hover:border-red-400/30 text-slate-400 hover:text-red-400 text-xs font-semibold rounded-xl transition-all disabled:opacity-50"
                >
                  <X size={12} />
                  Disconnect
                </button>
              </>
            )}
            {profile?.url && (
              <a
                href={profile.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2 glass-card border border-white/10 hover:bg-white/10 text-slate-200 text-xs font-semibold rounded-xl transition-all"
              >
                <ExternalLink size={14} />
                Profile
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Sub-tabs: Analytics | Achievements | AI Strategy.
          Content planning lives entirely in /planner now — this page used to
          carry a second Kanban over the very same plan_items rows. */}
      <div className="border-b border-white/5">
        <nav className="flex items-center gap-2 -mb-px">
          {([
            { key: 'analytics', label: 'Analytics & Posts', Icon: BarChart2 },
            { key: 'achievements', label: 'Achievements', Icon: Trophy },
            { key: 'strategy', label: 'AI Strategy & Roadmap', Icon: Sparkles },
          ] as const).map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-2 px-5 py-3.5 text-sm font-semibold border-b-2 transition-all ${
                tab === key
                  ? 'border-pink-500 text-pink-300 bg-pink-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-white/10'
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* TAB 1: ANALYTICS & POSTS */}
      {tab === 'analytics' && (
        <div className="space-y-8">
          {stats?.stale && (
            <div className="flex items-start gap-2 py-2.5 px-4 rounded-xl border border-sky-500/20 bg-sky-500/[0.06] text-xs text-sky-200/90">
              <Info size={13} className="mt-0.5 flex-shrink-0 text-sky-400" />
              <span>
                These figures were synced before per-post metrics were verifiable, so reach,
                views, saves and engagement can&apos;t be vouched for and show as “—”.
                Likes, comments and post counts are real. Click{" "}
                <span className="font-semibold text-sky-100">Sync Metrics</span> to pull
                measured numbers from Instagram.
              </span>
            </div>
          )}

          {/* Two different absences, worded differently on purpose. Either way
              the affected KPIs read "—", never the zeros this page used to show. */}
          {stats && !stats.stale && !stats.insights_supported && (
            <div className="flex items-start gap-2 py-2.5 px-4 rounded-xl border border-white/[0.08] bg-white/[0.03] text-xs text-slate-400">
              <Info size={13} className="mt-0.5 flex-shrink-0 text-slate-500" />
              <span>
                Instagram&apos;s account insights are windowed, so reach, profile visits and
                followers gained have no all-time figure. Post counts and per-post
                engagement below do cover your whole history — pick a 7, 30 or 90 day range
                for the account metrics.
              </span>
            </div>
          )}
          {stats && !stats.stale && stats.insights_supported && !stats.insights_available && (
            <div className="flex items-start gap-2 py-2.5 px-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] text-xs text-amber-200/90">
              <Info size={13} className="mt-0.5 flex-shrink-0 text-amber-400" />
              <span>
                Account-level insights (reach, profile visits, followers gained) aren&apos;t
                available for this connection. They need an Instagram Business or Creator
                account with the insights permission granted — reconnect to grant it. Post
                counts and per-post engagement below are unaffected.
              </span>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-pink-500/10 text-pink-400 rounded-xl">
                  <Users size={24} />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Followers</p>
                  <p className="text-2xl font-bold text-white">{formatNumber(stats?.total_followers || 0)}</p>
                  {/* Was an unconditional green "+0 this period", which read as
                      a measured flat month rather than an absent metric. */}
                  {stats?.followers_gained === null || stats?.followers_gained === undefined ? (
                    <span className="text-xs text-slate-500">Growth not measured</span>
                  ) : (
                    <span className={`text-xs font-medium ${stats.followers_gained >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {stats.followers_gained >= 0 ? '+' : ''}{formatNumber(stats.followers_gained)} {RANGE_LABELS[timeRange] ?? 'this period'}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-purple-500/10 text-purple-400 rounded-xl">
                  <Eye size={24} />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Reach</p>
                  <p className="text-2xl font-bold text-white">{formatMetric(stats?.total_reach)}</p>
                  {/* `views` is Meta's replacement for the retired impressions
                      metric, which this line used to duplicate reach into. */}
                  <span className="text-xs text-slate-500">{formatMetric(stats?.total_views)} views</span>
                </div>
              </div>
            </div>

            <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-amber-500/10 text-amber-400 rounded-xl">
                  <Film size={24} />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Avg Reel Views</p>
                  <p className="text-2xl font-bold text-white">{formatMetric(stats?.avg_reel_views)}</p>
                  <span className="text-xs text-amber-400 font-medium">
                    {stats?.total_reels_published ?? 0} reels {RANGE_LABELS[timeRange] ?? ''}
                  </span>
                </div>
              </div>
            </div>

            <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-500/10 text-blue-400 rounded-xl">
                  <Bookmark size={24} />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Avg Carousel Saves</p>
                  <p className="text-2xl font-bold text-white">{formatMetric(stats?.avg_carousel_saves)}</p>
                  <span className="text-xs text-blue-400 font-medium">
                    {stats?.total_carousels_published ?? 0} carousels {RANGE_LABELS[timeRange] ?? ''}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Posts & Performance Table */}
          <div className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden">
            <div className="p-6 border-b border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Instagram size={20} className="text-pink-400" />
                  Top Performing Instagram Content
                </h2>
                <p className="text-xs text-slate-400">Reels and Carousels metrics for {profile?.handle || "your account"}</p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setFormatFilter('all')}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                    formatFilter === 'all' ? 'bg-pink-500/20 text-pink-300 border border-pink-500/30' : 'text-slate-400 hover:bg-white/5'
                  }`}
                >
                  All
                </button>
                <button
                  onClick={() => setFormatFilter('reel')}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                    formatFilter === 'reel' ? 'bg-pink-500/20 text-pink-300 border border-pink-500/30' : 'text-slate-400 hover:bg-white/5'
                  }`}
                >
                  Reels
                </button>
                <button
                  onClick={() => setFormatFilter('carousel')}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                    formatFilter === 'carousel' ? 'bg-pink-500/20 text-pink-300 border border-pink-500/30' : 'text-slate-400 hover:bg-white/5'
                  }`}
                >
                  Carousels
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/5 text-slate-400 font-medium">
                  <tr>
                    <th className="px-6 py-4">Title / Caption</th>
                    <th className="px-6 py-4">Format</th>
                    <th className="px-6 py-4 text-right">Views</th>
                    <th className="px-6 py-4 text-right">Reach</th>
                    <th className="px-6 py-4 text-right">Likes</th>
                    <th className="px-6 py-4 text-right">Shares</th>
                    <th className="px-6 py-4 text-right">Saves</th>
                    <th className="px-6 py-4 text-right">Engagement</th>
                    <th className="px-6 py-4 text-right">Update</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {posts.map((post) => (
                    <tr key={post.id} className="hover:bg-white/[0.04] transition-colors">
                      <td className="px-6 py-4 max-w-xs">
                        <div className="font-medium text-slate-200 line-clamp-1">
                          {post.permalink ? (
                            <a
                              href={post.permalink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:text-pink-300 transition-colors"
                            >
                              {post.title}
                            </a>
                          ) : (
                            post.title
                          )}
                        </div>
                        <div className="text-xs text-slate-500 mt-1 line-clamp-1">{post.caption}</div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wider ${
                          post.type === 'reel' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        }`}>
                          {post.type === 'reel' ? <Film size={12} /> : <Layers size={12} />}
                          {post.type}
                        </span>
                      </td>
                      {/* Views and reach are separate measurements. This column
                          used to be `post.views || post.reach` — two different
                          metrics under one heading, and both were
                          `likes + comments` whenever the insights call failed. */}
                      <td className="px-6 py-4 text-right font-semibold text-white">{formatMetric(post.views)}</td>
                      <td className="px-6 py-4 text-right text-slate-300 font-mono">{formatMetric(post.reach)}</td>
                      <td className="px-6 py-4 text-right text-slate-300 font-mono">{formatNumber(post.likes)}</td>
                      <td className="px-6 py-4 text-right text-slate-300 font-mono">{formatMetric(post.shares)}</td>
                      <td className="px-6 py-4 text-right text-slate-300 font-mono">{formatMetric(post.saves)}</td>
                      <td className="px-6 py-4 text-right">
                        {post.engagement_rate === null || post.engagement_rate === undefined ? (
                          <span className="text-slate-600 font-mono text-xs">—</span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-500/10 text-green-400 border border-green-500/20">
                            {formatRate(post.engagement_rate)}
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleRefreshPost(post.id)}
                          disabled={refreshingPostId !== null}
                          title={
                            post.metrics_updated_at
                              ? `Re-read this post's metrics from Instagram (last read ${new Date(post.metrics_updated_at).toLocaleString()})`
                              : "Re-read this post's metrics from Instagram"
                          }
                          className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-white/10 bg-white/5 text-slate-400 hover:text-pink-300 hover:border-pink-500/30 hover:bg-pink-500/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <RefreshCw
                            size={13}
                            className={refreshingPostId === post.id ? 'animate-spin text-pink-400' : ''}
                          />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {posts.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-6 py-10 text-center text-sm text-slate-500">
                        {profile?.handle
                          ? 'No posts match this filter.'
                          : 'Connect your Instagram account and run Sync Metrics to see your posts.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {postError && (
              <div className="flex items-start gap-2 mx-6 mb-6 py-2.5 px-4 rounded-xl border border-red-500/20 bg-red-500/[0.06] text-xs text-red-300">
                <AlertTriangle size={13} className="mt-0.5 flex-shrink-0 text-red-400" />
                <span>{postError}</span>
              </div>
            )}
          </div>

          {/* Hashtag Analytics */}
          <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
            <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
              <Tag size={18} className="text-pink-400" />
              Top Hashtag Clusters for {profile?.handle || "your account"}
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {hashtags
                .slice(hashtagPage * HASHTAGS_PER_PAGE, hashtagPage * HASHTAGS_PER_PAGE + HASHTAGS_PER_PAGE)
                .map((h) => (
                  <div key={h.tag} className="p-4 rounded-xl glass-card border border-white/5 bg-white/[0.01]">
                    <p className="text-sm font-mono font-semibold text-pink-300">{h.tag}</p>
                    <p className="text-xs text-slate-400 mt-1">
                      {h.avg_reach === null || h.avg_reach === undefined
                        ? 'Reach not measured'
                        : `${formatNumber(h.avg_reach)} avg reach`}
                    </p>
                    {/* posts_used counts every post carrying the tag;
                        posts_measured is the subset the average is over. */}
                    <p className="text-[10px] text-slate-500">
                      {h.posts_used} posts used
                      {h.posts_measured > 0 && h.posts_measured < h.posts_used
                        ? ` · ${h.posts_measured} measured`
                        : ''}
                    </p>
                    <span className="inline-block mt-2 text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-400 uppercase tracking-wider">
                      {h.category}
                    </span>
                  </div>
                ))}
            </div>
            {hashtags.length > HASHTAGS_PER_PAGE && (
              <div className="flex items-center justify-center gap-3 pt-5">
                <button
                  onClick={() => setHashtagPage((p) => Math.max(0, p - 1))}
                  disabled={hashtagPage === 0}
                  className="flex items-center gap-1 px-3 py-1.5 glass-card rounded-lg text-sm text-slate-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft size={14} /> Prev
                </button>
                <span className="text-slate-400 text-sm">
                  Page {hashtagPage + 1} of {Math.ceil(hashtags.length / HASHTAGS_PER_PAGE)}
                  <span className="text-slate-600 ml-2">({hashtags.length} hashtags)</span>
                </span>
                <button
                  onClick={() =>
                    setHashtagPage((p) =>
                      Math.min(Math.ceil(hashtags.length / HASHTAGS_PER_PAGE) - 1, p + 1)
                    )
                  }
                  disabled={hashtagPage >= Math.ceil(hashtags.length / HASHTAGS_PER_PAGE) - 1}
                  className="flex items-center gap-1 px-3 py-1.5 glass-card rounded-lg text-sm text-slate-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: ACHIEVEMENTS */}
      {tab === 'achievements' && <InstagramAchievements />}

      {/* Visual studio — a free-form image-generation scratchpad.
          Distinct from the planner's per-item "Generate image": that one renders
          the graphic for a specific scheduled post and stores it on the item;
          this is for trying prompts without committing to a plan. */}
      {tab === 'strategy' && (
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] space-y-4">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Wand2 size={20} className="text-pink-400" />
              Visual Studio
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Try a prompt against Gemini without touching a plan.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="block sm:col-span-3">
              <span className="text-[10px] uppercase tracking-wider text-slate-500">Topic</span>
              <input
                value={genTopic}
                onChange={(e) => setGenTopic(e.target.value)}
                className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-pink-500/50"
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-slate-500">Palette</span>
              <select
                value={genPalette}
                onChange={(e) => setGenPalette(e.target.value)}
                className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-pink-500/50"
              >
                {PALETTES.map((v) => (
                  <option key={v} value={v} className="bg-slate-900">{v.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-slate-500">Layout</span>
              <select
                value={genLayout}
                onChange={(e) => setGenLayout(e.target.value)}
                className="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-pink-500/50"
              >
                {LAYOUTS.map((v) => (
                  <option key={v} value={v} className="bg-slate-900">{v.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </label>
            <button
              onClick={handleGenerateImage}
              disabled={isGenerating || !genTopic.trim()}
              className="mt-1 self-end rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:from-pink-600 hover:to-purple-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Wand2 size={16} className={isGenerating ? "animate-spin" : ""} />
              {isGenerating ? "Rendering…" : "Render"}
            </button>
          </div>

          {generatedResult?.images?.[0] && (
            /* eslint-disable-next-line @next/next/no-img-element -- base64 payload
               returned inline by Gemini; there is no URL for next/image to fetch. */
            <img
              src={`data:image/png;base64,${generatedResult.images[0]}`}
              alt={`Generated concept for ${genTopic}`}
              className="rounded-xl border border-white/10 max-h-96 w-auto"
            />
          )}
        </div>
      )}

      {/* TAB 3: AI STRATEGY & ROADMAP */}
      {tab === 'strategy' && (
        <div className="space-y-8">
          {/* Generate actions */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleGenerateStrategy}
              disabled={isGeneratingStrategy || !profile?.handle}
              title={!profile?.handle ? "Sync your Instagram account first" : undefined}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-pink-500 to-purple-600 text-white text-xs font-semibold rounded-xl shadow-lg hover:from-pink-600 hover:to-purple-700 transition-all disabled:opacity-50"
            >
              <Sparkles size={16} className={isGeneratingStrategy ? "animate-spin" : ""} />
              {isGeneratingStrategy ? "Analyzing your account..." : "Generate Strategy Brief"}
            </button>
            <button
              onClick={handleGenerateRoadmap}
              disabled={isGeneratingRoadmap || !profile?.handle}
              title={!profile?.handle ? "Sync your Instagram account first" : undefined}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white text-xs font-semibold rounded-xl shadow-lg hover:from-purple-700 hover:to-indigo-700 transition-all disabled:opacity-50"
            >
              <Calendar size={16} className={isGeneratingRoadmap ? "animate-spin" : ""} />
              {isGeneratingRoadmap ? "Building your roadmap..." : "Generate Roadmap"}
            </button>
          </div>

          {/* Executive Summary */}
          {strategy && (
            <div className="glass-card p-6 rounded-2xl border border-white/10 bg-gradient-to-br from-pink-900/10 to-purple-900/10 space-y-4">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Sparkles size={18} className="text-pink-400" />
                AI Content Strategy Brief ({strategy?.brand || profile?.handle || "your account"})
              </h3>
              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                {strategy.executive_summary}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-white/5">
                {strategy.top_performing_formats?.map((fmt: any, i: number) => (
                  <div key={i} className="p-4 rounded-xl glass-card border border-white/5 bg-white/[0.02]">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white">{fmt.format}</span>
                      <span className="text-xs font-mono text-pink-400 font-bold">{fmt.reach_multiplier || fmt.save_multiplier}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-2">{fmt.recommendation}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Viral Reel Hooks */}
          {strategy?.viral_reel_hooks && (
            <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
              <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                <Film size={18} className="text-purple-400" />
                High-Conversion Reel Hook Templates
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {strategy.viral_reel_hooks.map((hook: string, idx: number) => (
                  <div key={idx} className="p-3.5 rounded-xl glass-card border border-white/5 bg-white/[0.01] flex items-center justify-between text-xs text-slate-200">
                    <span>"{hook}"</span>
                    <button
                      onClick={() => navigator.clipboard.writeText(hook)}
                      className="text-[10px] px-2 py-1 bg-white/5 hover:bg-white/10 rounded text-pink-300 font-mono"
                    >
                      Copy
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 30-Day Content Roadmap */}
          {roadmap?.weeks && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Calendar size={20} className="text-pink-400" />
                  30-Day Instagram Posting Roadmap
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleAddRoadmapToPlan('selected')}
                    disabled={isAddingRoadmapToPlan || selectedRoadmapItems.size === 0}
                    className="text-xs px-3 py-1.5 rounded-lg border border-white/10 text-slate-300 hover:border-white/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Add Selected to Planner ({selectedRoadmapItems.size})
                  </button>
                  <button
                    onClick={() => handleAddRoadmapToPlan('all')}
                    disabled={isAddingRoadmapToPlan}
                    className="text-xs px-3 py-1.5 rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 text-white font-semibold hover:from-pink-600 hover:to-purple-700 transition-all disabled:opacity-50"
                  >
                    {isAddingRoadmapToPlan ? "Adding…" : "Add All to Planner"}
                  </button>
                </div>
              </div>

              {roadmapResult && (
                <div className="rounded-xl border border-pink-500/20 bg-pink-500/[0.04] p-4 text-xs space-y-2">
                  <p className="text-slate-200">
                    Scheduled <span className="font-semibold text-pink-300">{roadmapResult.created}</span>{" "}
                    {roadmapResult.created === 1 ? "post" : "posts"}
                    {roadmapResult.skipped.length > 0 && (
                      <> · skipped {roadmapResult.skipped.length} already covered</>
                    )}
                    {" · "}
                    <Link
                      href={`/planner?plan=${roadmapResult.plan_id}`}
                      className="text-pink-300 underline underline-offset-2 hover:text-pink-200"
                    >
                      Open in the planner
                    </Link>
                  </p>
                  {roadmapResult.skipped.length > 0 && (
                    <ul className="text-slate-500 space-y-0.5">
                      {roadmapResult.skipped.map((s) => (
                        <li key={s.title}>· {s.title} — {s.reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="space-y-6">
                {roadmap.weeks.map((week: any) => (
                  <div key={week.week_number} className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] space-y-4">
                    <div className="flex items-center justify-between border-b border-white/5 pb-3">
                      <span className="text-sm font-bold text-pink-300 uppercase tracking-wider">{week.theme}</span>
                      <span className="text-xs font-mono text-slate-500">Starts {week.start_date}</span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {week.items.map((item: any, idx: number) => {
                        const key = `${week.week_number}-${idx}`;
                        return (
                          <div key={idx} className="p-4 rounded-xl glass-card border border-white/5 bg-white/[0.01] space-y-2">
                            <div className="flex items-center justify-between text-[11px]">
                              <label className="flex items-center gap-1.5 text-slate-400 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={selectedRoadmapItems.has(key)}
                                  onChange={() => toggleRoadmapItem(key)}
                                  className="accent-pink-500"
                                />
                                <span className="font-mono">{item.date}</span>
                              </label>
                              <span className={`uppercase font-bold text-[9px] px-2 py-0.5 rounded ${
                                item.type === 'reel' ? 'bg-purple-500/20 text-purple-300' : 'bg-blue-500/20 text-blue-300'
                              }`}>
                                {item.type}
                              </span>
                            </div>
                            <h4 className="text-xs font-bold text-white">{item.title}</h4>
                            <p className="text-[11px] text-pink-300 font-mono">{item.tags}</p>
                            <p className="text-[10px] text-slate-400 italic">CTA: {item.call_to_action}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add Item Modal */}
    </div>
  );
}
