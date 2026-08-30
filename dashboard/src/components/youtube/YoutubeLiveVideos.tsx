"use client";

import React, { useState, useEffect, useCallback } from 'react';
import {
  Search, SlidersHorizontal, ExternalLink, Tag, ThumbsUp,
  MessageSquare, Eye, TrendingUp, ChevronDown,
  Youtube, Loader2, AlertCircle, Info, ChevronLeft, ChevronRight,
  Globe, Lock, EyeOff, Calendar, Sparkles, Copy
} from 'lucide-react';
import { request } from '@/lib/apiClient';

interface LiveVideo {
  video_id: string;
  title: string;
  description: string;
  tags: string[];
  category_id: string;
  duration_seconds: number;
  published_at: string;
  thumbnail_url: string | null;
  views: number;
  likes: number;
  comments: number;
  channel_title: string;
  seo_title_score: number;
  seo_tag_count: number;
  seo_desc_words: number;
  privacy_status?: string;
  is_scheduled?: number;
  publish_at?: string | null;
  fetched_at: string;
  impressions?: number;
  impressions_ctr?: number;
  average_view_duration_seconds?: number;
  average_view_percentage?: number;
  analytics_synced_at?: string | null;
}

interface LiveVideoResponse {
  total: number;
  limit: number;
  offset: number;
  videos: LiveVideo[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n ?? 0);
}

function formatDuration(secs: number): string {
  if (!secs) return '0:00';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function timeAgo(iso: string): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

// SEO score → color + label
function seoMeta(score: number): { label: string; color: string; bg: string; width: string } {
  if (score >= 75) return { label: 'Excellent', color: 'text-emerald-400', bg: 'bg-emerald-400', width: `${score}%` };
  if (score >= 50) return { label: 'Good', color: 'text-amber-400', bg: 'bg-amber-400', width: `${score}%` };
  return { label: 'Needs Work', color: 'text-red-400', bg: 'bg-red-400', width: `${score}%` };
}

// Status badge helper
function getStatusBadge(video: LiveVideo) {
  if (video.is_scheduled || (video.publish_at && new Date(video.publish_at) > new Date())) {
    return {
      label: 'Scheduled',
      icon: Calendar,
      className: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    };
  }
  const status = (video.privacy_status || 'public').toLowerCase();
  switch (status) {
    case 'private':
      return {
        label: 'Private',
        icon: Lock,
        className: 'bg-red-500/20 text-red-300 border-red-500/40',
      };
    case 'unlisted':
      return {
        label: 'Unlisted',
        icon: EyeOff,
        className: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
      };
    case 'public':
    default:
      return {
        label: 'Public',
        icon: Globe,
        className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      };
  }
}

// ── Video Detail Modal ────────────────────────────────────────────────────────

interface VideoDetailModalProps {
  video: LiveVideo;
  onClose: () => void;
  onUpdated?: (updatedVideo: LiveVideo) => void;
}

interface VideoGrowthRecommendations {
  verdict: string;
  title_options: string[];
  thumbnail_ideas: string[];
  hook_rewrite: string;
  description_fixes: string[];
  tag_fixes: string[];
  priority_actions: string[];
}

function VideoDetailModal({ video, onClose, onUpdated }: VideoDetailModalProps) {
  const [currentVideo, setCurrentVideo] = useState<LiveVideo>(video);
  const [detail, setDetail] = useState<LiveVideo & { seo_suggestions?: string[]; youtube_url?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [growth, setGrowth] = useState<VideoGrowthRecommendations | null>(null);
  const [loadingGrowth, setLoadingGrowth] = useState(false);
  const [growthError, setGrowthError] = useState<string | null>(null);

  // Editable fields for 1-Click Update to YouTube
  const [editTitle, setEditTitle] = useState(video.title);
  const [editDescription, setEditDescription] = useState(video.description || '');
  const [editTags, setEditTags] = useState(video.tags ? video.tags.join(', ') : '');
  const [showEditSection, setShowEditSection] = useState(false);
  const [updatingYouTube, setUpdatingYouTube] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    request<LiveVideo & { seo_suggestions?: string[]; youtube_url?: string }>(
      `/youtube-analytics/live-video/${currentVideo.video_id}`
    )
      .then((res) => {
        setDetail(res);
        if (res) {
          setEditDescription(res.description || '');
          setEditTags(res.tags ? res.tags.join(', ') : '');
        }
      })
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [currentVideo.video_id]);

  const handleGetGrowthRecommendations = async () => {
    setLoadingGrowth(true);
    setGrowthError(null);
    try {
      const data = await request<VideoGrowthRecommendations>(
        `/youtube-analytics/live-video/${currentVideo.video_id}/growth-recommendations`,
        { method: 'POST' }
      );
      setGrowth(data);
    } catch (err) {
      setGrowthError(err instanceof Error ? err.message : 'Failed to generate recommendations');
    } finally {
      setLoadingGrowth(false);
    }
  };

  const handleUpdateToYouTube = async (customFields?: { title?: string; description?: string; tags?: string[] }) => {
    setUpdatingYouTube(true);
    setUpdateStatus(null);
    try {
      const payload = {
        title: customFields?.title ?? editTitle,
        description: customFields?.description ?? editDescription,
        tags: customFields?.tags ?? editTags.split(',').map((s) => s.trim()).filter(Boolean),
      };
      const res = await request<{
        success: boolean;
        video_id: string;
        title: string;
        description: string;
        tags: string[];
        seo_title_score: number;
        seo_tag_count: number;
        seo_desc_words: number;
        message: string;
      }>(`/youtube-analytics/live-video/${currentVideo.video_id}/update-metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const updated: LiveVideo = {
        ...currentVideo,
        title: res.title,
        description: res.description,
        tags: res.tags,
        seo_title_score: res.seo_title_score,
        seo_tag_count: res.seo_tag_count,
        seo_desc_words: res.seo_desc_words,
      };

      setCurrentVideo(updated);
      setEditTitle(res.title);
      setEditDescription(res.description);
      setEditTags(res.tags ? res.tags.join(', ') : '');
      setUpdateStatus({ type: 'success', message: '✅ Video successfully updated directly on YouTube!' });
      onUpdated?.(updated);
    } catch (err: unknown) {
      setUpdateStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to update video on YouTube. Please check permissions.',
      });
    } finally {
      setUpdatingYouTube(false);
    }
  };

  const seo = seoMeta(currentVideo.seo_title_score);
  const statusBadge = getStatusBadge(currentVideo);
  const StatusIcon = statusBadge.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm" onClick={onClose}>
      <div
        className="glass-card w-full max-w-2xl max-h-[90vh] rounded-2xl border border-white/10 flex flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-white/[0.02]">
          <div className="flex items-center gap-2 text-white font-semibold text-sm">
            <Youtube size={18} className="text-red-500" />
            Video Detail & 1-Click Update
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Update status message */}
          {updateStatus && (
            <div
              className={`p-3 rounded-xl text-xs font-medium flex items-center justify-between gap-3 border ${
                updateStatus.type === 'success'
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                  : 'bg-red-500/10 text-red-300 border-red-500/20'
              }`}
            >
              <span>{updateStatus.message}</span>
              {(updateStatus.message.toLowerCase().includes('reconnect') ||
                updateStatus.message.toLowerCase().includes('permission') ||
                updateStatus.message.toLowerCase().includes('scope')) && (
                <button
                  onClick={async () => {
                    try {
                      const res = await request<{ authorization_url: string }>('/google/authorize?next=/youtube-analysis');
                      if (res.authorization_url) window.location.href = res.authorization_url;
                    } catch {
                      window.location.href = '/settings';
                    }
                  }}
                  className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white font-semibold rounded-lg text-[11px] whitespace-nowrap transition-colors cursor-pointer flex-shrink-0"
                >
                  Grant YouTube Permission
                </button>
              )}
            </div>
          )}

          {/* Thumbnail + title */}
          <div className="flex gap-4">
            {currentVideo.thumbnail_url ? (
              <img
                src={currentVideo.thumbnail_url}
                alt={currentVideo.title}
                className="w-40 h-24 object-cover rounded-xl border border-white/10 flex-shrink-0 bg-slate-800"
              />
            ) : (
              <div className="w-40 h-24 bg-white/5 rounded-xl flex items-center justify-center flex-shrink-0">
                <Youtube size={28} className="text-red-500/50" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border ${statusBadge.className}`}>
                  <StatusIcon size={12} />
                  {statusBadge.label}
                </span>
                {currentVideo.publish_at && (
                  <span className="text-[11px] text-slate-400">
                    Scheduled for {new Date(currentVideo.publish_at).toLocaleString()}
                  </span>
                )}
              </div>
              <h3 className="text-white font-semibold text-sm leading-snug line-clamp-3">{currentVideo.title}</h3>
              <p className="text-slate-500 text-xs mt-1">{timeAgo(currentVideo.published_at)} · {formatDuration(currentVideo.duration_seconds)}</p>
              {detail?.youtube_url && (
                <a
                  href={detail.youtube_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
                >
                  <ExternalLink size={12} /> Open on YouTube
                </a>
              )}
            </div>
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { icon: Eye, label: 'Views', value: formatCount(currentVideo.views), color: 'text-blue-400' },
              { icon: ThumbsUp, label: 'Likes', value: formatCount(currentVideo.likes), color: 'text-emerald-400' },
              { icon: MessageSquare, label: 'Comments', value: formatCount(currentVideo.comments), color: 'text-purple-400' },
            ].map(({ icon: Icon, label, value, color }) => (
              <div key={label} className="bg-white/5 rounded-xl p-3 text-center">
                <Icon size={16} className={`${color} mx-auto mb-1`} />
                <p className="text-white font-bold text-sm">{value}</p>
                <p className="text-slate-500 text-xs">{label}</p>
              </div>
            ))}
          </div>

          {/* Real CTR / impressions */}
          <div className="bg-white/[0.03] rounded-xl p-4 border border-white/5">
            {detail?.analytics_synced_at ? (
              <div className="grid grid-cols-3 gap-2 text-xs text-slate-400">
                <span>Impressions: <span className="text-white font-medium">{formatCount(detail.impressions ?? 0)}</span></span>
                <span>CTR: <span className="text-white font-medium">{detail.impressions_ctr != null ? `${(detail.impressions_ctr).toFixed(1)}%` : '—'}</span></span>
                <span>Avg % Viewed: <span className="text-white font-medium">{(detail.average_view_percentage ?? 0).toFixed(1)}%</span></span>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Live Retention: <span className="text-cyan-300 font-medium">{(currentVideo.average_view_percentage ?? 0).toFixed(1)}%</span> · Lifetime Net Subs: <span className="text-emerald-300 font-medium">+{currentVideo.likes || 0}</span>
              </p>
            )}
          </div>

          {/* SEO Score */}
          <div className="bg-white/[0.03] rounded-xl p-4 space-y-3 border border-white/5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 text-sm font-medium flex items-center gap-2"><TrendingUp size={14} /> SEO Score</span>
              <span className={`font-bold text-sm ${seo.color}`}>{currentVideo.seo_title_score}/100 · {seo.label}</span>
            </div>
            <div className="w-full bg-white/10 rounded-full h-2">
              <div className={`${seo.bg} h-2 rounded-full transition-all duration-700`} style={{ width: seo.width }} />
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs text-slate-400">
              <span>Tags: <span className="text-white font-medium">{currentVideo.seo_tag_count}</span></span>
              <span>Desc Words: <span className="text-white font-medium">{currentVideo.seo_desc_words}</span></span>
              <span>Title Len: <span className="text-white font-medium">{currentVideo.title?.length}</span></span>
            </div>
          </div>

          {/* SEO Suggestions */}
          {loading && <div className="flex justify-center py-2"><Loader2 size={16} className="animate-spin text-slate-400" /></div>}
          {detail?.seo_suggestions && detail.seo_suggestions.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5"><Info size={12} /> Improvement Tips</p>
              {detail.seo_suggestions.map((tip, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-slate-300 bg-amber-500/5 border border-amber-500/15 rounded-lg p-3">
                  <AlertCircle size={12} className="text-amber-400 mt-0.5 flex-shrink-0" />
                  {tip}
                </div>
              ))}
            </div>
          )}

          {/* AI Growth Recommendations & 1-Click Update */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles size={12} /> AI Growth Recommendations
              </p>
              <button
                onClick={handleGetGrowthRecommendations}
                disabled={loadingGrowth}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-red-500 to-orange-500 text-white text-xs font-semibold rounded-lg shadow-lg hover:from-red-600 hover:to-orange-600 transition-all disabled:opacity-50 cursor-pointer"
              >
                {loadingGrowth ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                {loadingGrowth ? 'Analyzing…' : growth ? 'Regenerate' : 'Get AI Recommendations'}
              </button>
            </div>

            {growthError && <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 p-2.5 rounded-lg">{growthError}</p>}

            {growth && (
              <div className="space-y-4 bg-gradient-to-br from-red-900/10 to-orange-900/10 border border-white/10 rounded-xl p-4">
                <p className="text-xs text-slate-300 leading-relaxed font-medium">{growth.verdict}</p>

                {/* 1-Click Title Update Options */}
                {growth.title_options.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                      <Youtube size={13} className="text-red-400" /> Title Recommendations (1-Click Update to YouTube)
                    </p>
                    <div className="space-y-2">
                      {growth.title_options.map((t, i) => (
                        <div key={i} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-200 bg-white/[0.04] border border-white/10 hover:border-red-500/30 rounded-xl p-3 transition-colors">
                          <span className="font-medium leading-snug flex-1">{t}</span>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <button
                              onClick={() => navigator.clipboard.writeText(t)}
                              title="Copy title"
                              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
                            >
                              <Copy size={13} />
                            </button>
                            <button
                              disabled={updatingYouTube}
                              onClick={() => handleUpdateToYouTube({ title: t })}
                              className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-orange-500 text-white font-semibold text-xs rounded-lg shadow-md transition-all disabled:opacity-50 cursor-pointer"
                              title="Update this title on YouTube immediately"
                            >
                              {updatingYouTube ? <Loader2 size={12} className="animate-spin" /> : <Youtube size={13} />}
                              Update on YouTube
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {growth.thumbnail_ideas.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Thumbnail Concepts</p>
                    {growth.thumbnail_ideas.map((t, i) => (
                      <p key={i} className="text-xs text-slate-300 bg-white/[0.03] border border-white/5 rounded-lg p-2.5">{t}</p>
                    ))}
                  </div>
                )}

                {growth.hook_rewrite && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Hook Rewrite (first 5-10s)</p>
                    <p className="text-xs text-slate-300 bg-white/[0.03] border border-white/5 rounded-lg p-2.5">{growth.hook_rewrite}</p>
                  </div>
                )}

                {growth.priority_actions.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Top Priorities</p>
                    <ol className="space-y-1.5 list-decimal list-inside">
                      {growth.priority_actions.map((a, i) => (
                        <li key={i} className="text-xs text-slate-200">{a}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Quick Edit & 1-Click Update to YouTube Section */}
          <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Youtube size={14} className="text-red-500" />
                Live YouTube Metadata Editor
              </p>
              <button
                onClick={() => setShowEditSection(!showEditSection)}
                className="text-xs text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                {showEditSection ? 'Collapse' : 'Edit & Update'}
              </button>
            </div>

            {showEditSection && (
              <div className="space-y-3 pt-2">
                <div>
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">Title</label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-red-500 transition-colors"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">Description</label>
                  <textarea
                    rows={4}
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-red-500 transition-colors"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">Tags (comma-separated)</label>
                  <input
                    type="text"
                    value={editTags}
                    onChange={(e) => setEditTags(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-red-500 transition-colors"
                  />
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    disabled={updatingYouTube}
                    onClick={() => handleUpdateToYouTube()}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-500 hover:to-orange-400 text-white font-semibold text-xs rounded-xl shadow-lg transition-all disabled:opacity-50 cursor-pointer"
                  >
                    {updatingYouTube ? <Loader2 size={14} className="animate-spin" /> : <Youtube size={14} />}
                    {updatingYouTube ? 'Updating YouTube...' : '🚀 1-Click Update to YouTube'}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Tags */}
          {currentVideo.tags && currentVideo.tags.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5"><Tag size={12} /> Current Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {currentVideo.tags.map((t) => (
                  <span key={t} className="px-2 py-1 bg-white/5 border border-white/10 text-slate-300 text-xs rounded-lg">{t}</span>
                ))}
              </div>
            </div>
          )}

          {/* Description (truncated) */}
          {currentVideo.description && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Current Description</p>
              <p className="text-slate-400 text-xs leading-relaxed line-clamp-6">{currentVideo.description}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function YoutubeLiveVideos() {
  const [data, setData] = useState<LiveVideoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sortBy, setSortBy] = useState('published_at');
  const [order, setOrder] = useState('desc');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const [selectedVideo, setSelectedVideo] = useState<LiveVideo | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const LIMIT = 24;

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 350);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        limit: String(LIMIT),
        offset: String(page * LIMIT),
        sort_by: sortBy,
        order,
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
      });
      const data = await request<LiveVideoResponse>(`/youtube-analytics/live-videos?${params}`);
      setData(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load videos');
    } finally {
      setLoading(false);
    }
  }, [page, sortBy, order, debouncedSearch, statusFilter]);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 0;
  const seo = (score: number) => seoMeta(score);

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search videos or tags…"
            className="w-full pl-9 pr-4 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-red-500/40 transition-all"
          />
        </div>

        {/* Status Filter direct select */}
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
          className="px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-red-500/40"
        >
          <option value="">All Statuses</option>
          <option value="public">Public</option>
          <option value="scheduled">Scheduled</option>
          <option value="unlisted">Unlisted</option>
          <option value="private">Private</option>
        </select>

        {/* Filters toggle */}
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-sm transition-colors ${showFilters ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'}`}
        >
          <SlidersHorizontal size={14} />
          Filters
          <ChevronDown size={12} className={`transition-transform ${showFilters ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {/* Filter row */}
      {showFilters && (
        <div className="flex flex-wrap gap-3 p-4 bg-white/[0.02] rounded-xl border border-white/5 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 uppercase tracking-wider">Sort by</label>
            <select
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(0); }}
              className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-red-500/30"
            >
              <option value="published_at">Newest First</option>
              <option value="views">Most Views</option>
              <option value="likes">Most Likes</option>
              <option value="comments">Most Comments</option>
              <option value="seo_title_score">SEO Score</option>
              <option value="duration_seconds">Duration</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 uppercase tracking-wider">Order</label>
            <select
              value={order}
              onChange={(e) => { setOrder(e.target.value); setPage(0); }}
              className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-red-500/30"
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </div>
          {data && (
            <div className="flex items-end">
              <span className="text-xs text-slate-500 py-1.5">{data.total} videos found</span>
            </div>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-300 text-sm">
          <AlertCircle size={16} className="flex-shrink-0" />
          <div>
            <p className="font-medium">Failed to load live videos</p>
            <p className="text-xs text-red-400/70 mt-0.5">{error}</p>
            {error.includes('not connected') || error.includes('Reconnect') ? (
              <p className="text-xs mt-1 text-red-300/70">Connect your Google account first via Settings → Google.</p>
            ) : error.includes('not enabled') ? (
              <p className="text-xs mt-1 text-red-300/70">Enable YouTube Data API v3 in Google Cloud Console.</p>
            ) : null}
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="glass-card rounded-2xl border border-white/5 overflow-hidden animate-pulse">
              <div className="w-full h-36 bg-white/5" />
              <div className="p-4 space-y-2">
                <div className="h-3 bg-white/5 rounded w-3/4" />
                <div className="h-3 bg-white/5 rounded w-1/2" />
                <div className="h-2 bg-white/5 rounded w-full mt-3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && data?.videos.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center space-y-4">
          <div className="p-5 bg-red-500/10 rounded-2xl">
            <Youtube size={40} className="text-red-500/60" />
          </div>
          <div>
            <p className="text-white font-semibold">No live videos found</p>
            <p className="text-slate-500 text-sm mt-1">Click <strong className="text-slate-300">Sync from YouTube</strong> above or try resetting your search filters.</p>
          </div>
        </div>
      )}

      {/* Video grid */}
      {!loading && !error && data && data.videos.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {data.videos.map((video) => {
              const s = seo(video.seo_title_score);
              const statusBadge = getStatusBadge(video);
              const StatusIcon = statusBadge.icon;

              return (
                <div
                  key={video.video_id}
                  onClick={() => setSelectedVideo(video)}
                  className="glass-card rounded-2xl border border-white/5 bg-white/[0.02] overflow-hidden hover:border-red-500/30 hover:bg-white/[0.04] transition-all duration-200 cursor-pointer group flex flex-col"
                >
                  {/* Thumbnail */}
                  <div className="relative w-full h-36 bg-white/5 overflow-hidden">
                    {video.thumbnail_url ? (
                      <img
                        src={video.thumbnail_url}
                        alt={video.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Youtube size={32} className="text-red-500/30" />
                      </div>
                    )}

                    {/* Status Badge */}
                    <div className={`absolute top-2 right-2 flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border backdrop-blur-md shadow-md ${statusBadge.className}`}>
                      <StatusIcon size={10} />
                      {statusBadge.label}
                    </div>

                    {/* Duration badge */}
                    <div className="absolute bottom-2 right-2 bg-black/75 text-white text-xs px-1.5 py-0.5 rounded font-mono">
                      {formatDuration(video.duration_seconds)}
                    </div>

                    {/* SEO score chip */}
                    <div className={`absolute top-2 left-2 text-xs font-bold px-2 py-0.5 rounded-full bg-black/60 ${s.color}`}>
                      {video.seo_title_score}
                    </div>
                  </div>

                  {/* Content */}
                  <div className="flex-1 p-4 flex flex-col gap-3">
                    {/* Title */}
                    <h3 className="text-slate-100 text-xs font-semibold leading-snug line-clamp-2 group-hover:text-white transition-colors">
                      {video.title}
                    </h3>

                    {/* Date */}
                    <p className="text-slate-500 text-xs">{timeAgo(video.published_at)}</p>

                    {/* Stats row */}
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <Eye size={11} className="text-blue-400" />
                        {formatCount(video.views)}
                      </span>
                      <span className="flex items-center gap-1">
                        <ThumbsUp size={11} className="text-emerald-400" />
                        {formatCount(video.likes)}
                      </span>
                      <span className="flex items-center gap-1">
                        <MessageSquare size={11} className="text-purple-400" />
                        {formatCount(video.comments)}
                      </span>
                    </div>

                    {/* SEO bar */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-500">SEO</span>
                        <span className={s.color + ' font-medium'}>{s.label}</span>
                      </div>
                      <div className="w-full bg-white/10 rounded-full h-1.5">
                        <div className={`${s.bg} h-1.5 rounded-full transition-all duration-700`} style={{ width: s.width }} />
                      </div>
                    </div>

                    {/* Tags */}
                    {video.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-auto pt-1">
                        {video.tags.slice(0, 3).map((t) => (
                          <span key={t} className="flex items-center gap-0.5 px-1.5 py-0.5 bg-white/5 border border-white/10 text-slate-400 text-[10px] rounded-md">
                            <Tag size={8} />
                            {t.length > 14 ? t.slice(0, 14) + '…' : t}
                          </span>
                        ))}
                        {video.tags.length > 3 && (
                          <span className="px-1.5 py-0.5 bg-white/5 border border-white/10 text-slate-500 text-[10px] rounded-md">
                            +{video.tags.length - 3}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Open link */}
                    <a
                      href={`https://www.youtube.com/watch?v=${video.video_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1 flex items-center gap-1 text-[10px] text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <ExternalLink size={10} /> youtube.com
                    </a>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 px-3 py-1.5 glass-card rounded-lg text-sm text-slate-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <span className="text-slate-400 text-sm">
                Page {page + 1} of {totalPages}
                <span className="text-slate-600 ml-2">({data.total} videos)</span>
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 px-3 py-1.5 glass-card rounded-lg text-sm text-slate-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          )}
        </>
      )}

      {/* Video detail modal */}
      {selectedVideo && (
        <VideoDetailModal
          video={selectedVideo}
          onClose={() => setSelectedVideo(null)}
          onUpdated={(updated) => {
            setSelectedVideo(updated);
            setData((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                videos: prev.videos.map((v) => (v.video_id === updated.video_id ? updated : v)),
              };
            });
          }}
        />
      )}
    </div>
  );
}
