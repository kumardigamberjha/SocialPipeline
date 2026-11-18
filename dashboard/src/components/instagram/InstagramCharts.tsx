"use client";

import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import {
  TrendingUp,
  BarChart3,
  Layers,
  Sparkles,
  Film,
  Tag,
} from 'lucide-react';

interface InstagramPost {
  id: string;
  title: string;
  type: 'reel' | 'carousel' | 'single';
  publish_time: string;
  likes: number;
  comments: number;
  views: number | null;
  shares: number | null;
  saves: number | null;
  reach: number | null;
  engagement_rate: number | null;
  rate_type?: string;
  permalink?: string;
}

interface HashtagItem {
  tag: string;
  posts_used: number;
  posts_measured: number;
  avg_reach: number | null;
  score: number | null;
  category: string;
}

interface InstagramChartsProps {
  posts: InstagramPost[];
  hashtags: HashtagItem[];
  followersCount: number;
}

export default function InstagramCharts({ posts, hashtags, followersCount }: InstagramChartsProps) {
  const [metricFocus, setMetricFocus] = useState<'reach_views' | 'engagement' | 'interactions'>('reach_views');

  // Prepare chronological posts data (oldest to newest for timeline)
  const timelineData = useMemo(() => {
    if (!posts || posts.length === 0) return [];
    return [...posts]
      .sort((a, b) => new Date(a.publish_time).getTime() - new Date(b.publish_time).getTime())
      .slice(-15) // last 15 posts
      .map((p, idx) => {
        const d = p.publish_time ? new Date(p.publish_time) : null;
        const dateStr = d ? `${d.getDate()} ${d.toLocaleString('default', { month: 'short' })}` : `P${idx + 1}`;
        const interactions = p.likes + p.comments + (p.saves || 0) + (p.shares || 0);
        return {
          id: p.id,
          date: dateStr,
          title: p.title,
          type: p.type,
          views: p.views ?? 0,
          reach: p.reach ?? 0,
          likes: p.likes,
          comments: p.comments,
          saves: p.saves ?? 0,
          interactions,
          rate: p.engagement_rate ?? 0,
          rateType: p.rate_type || 'followers',
        };
      });
  }, [posts]);

  // Format performance breakdown
  const formatBreakdown = useMemo(() => {
    if (!posts || posts.length === 0) return [];
    const grouped: Record<string, { count: number; totalViews: number; totalLikes: number; totalSaves: number; rates: number[] }> = {
      reel: { count: 0, totalViews: 0, totalLikes: 0, totalSaves: 0, rates: [] },
      carousel: { count: 0, totalViews: 0, totalLikes: 0, totalSaves: 0, rates: [] },
      single: { count: 0, totalViews: 0, totalLikes: 0, totalSaves: 0, rates: [] },
    };

    posts.forEach((p) => {
      const g = grouped[p.type] || grouped['single'];
      g.count += 1;
      if (p.views) g.totalViews += p.views;
      g.totalLikes += p.likes;
      if (p.saves) g.totalSaves += p.saves;
      if (p.engagement_rate) g.rates.push(p.engagement_rate);
    });

    const labels: Record<string, string> = {
      reel: 'Reels',
      carousel: 'Carousels',
      single: 'Singles',
    };

    return Object.entries(grouped)
      .filter(([_, data]) => data.count > 0)
      .map(([type, data]) => ({
        format: labels[type] || type,
        type,
        count: data.count,
        avgViews: data.count > 0 ? Math.round(data.totalViews / data.count) : 0,
        avgLikes: data.count > 0 ? Math.round(data.totalLikes / data.count) : 0,
        avgSaves: data.count > 0 ? Math.round(data.totalSaves / data.count) : 0,
        avgRate: data.rates.length > 0 ? Number((data.rates.reduce((a, b) => a + b, 0) / data.rates.length).toFixed(1)) : 0,
      }));
  }, [posts]);

  // Top hashtags for horizontal bar display
  const topHashtagsData = useMemo(() => {
    return (hashtags || [])
      .filter((h) => h.avg_reach && h.avg_reach > 0)
      .slice(0, 6)
      .map((h) => ({
        tag: h.tag,
        avgReach: h.avg_reach ?? 0,
        postsCount: h.posts_used,
        category: h.category,
      }));
  }, [hashtags]);

  if (!posts || posts.length === 0) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Charts Header & Metric Selector */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <TrendingUp size={18} className="text-pink-400" />
            Visual Intelligence & Growth Velocity
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time trajectory, format dynamics, and audience reach patterns
          </p>
        </div>

        {/* View switcher */}
        <div className="flex items-center gap-1.5 p-1 bg-white/[0.04] border border-white/10 rounded-xl">
          <button
            onClick={() => setMetricFocus('reach_views')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
              metricFocus === 'reach_views'
                ? 'bg-gradient-to-r from-pink-500 to-purple-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Reach & Views
          </button>
          <button
            onClick={() => setMetricFocus('interactions')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
              metricFocus === 'interactions'
                ? 'bg-gradient-to-r from-pink-500 to-purple-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Interactions
          </button>
          <button
            onClick={() => setMetricFocus('engagement')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
              metricFocus === 'engagement'
                ? 'bg-gradient-to-r from-pink-500 to-purple-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Engagement %
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Performance Timeline Chart (2 Cols) */}
        <div className="lg:col-span-2 glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <BarChart3 size={14} className="text-purple-400" />
              Post-by-Post Trajectory
            </span>
            <span className="text-[11px] font-mono text-slate-500">
              Last {timelineData.length} Posts
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="pinkGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ec4899" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#ec4899" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="purpleGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload || !payload.length) return null;
                    const item = payload[0].payload;
                    return (
                      <div className="p-3 bg-slate-900/95 border border-pink-500/30 rounded-xl shadow-xl backdrop-blur-md text-xs space-y-1 max-w-xs">
                        <p className="font-semibold text-white line-clamp-1">{item.title}</p>
                        <p className="text-[10px] text-slate-400 font-mono">{item.date} • {item.type.toUpperCase()}</p>
                        <div className="pt-1.5 border-t border-white/10 grid grid-cols-2 gap-2 text-[11px]">
                          <div>
                            <span className="text-slate-400">Views:</span>{" "}
                            <span className="font-bold text-white">{item.views.toLocaleString()}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Reach:</span>{" "}
                            <span className="font-bold text-purple-300">{item.reach.toLocaleString()}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Likes:</span>{" "}
                            <span className="font-bold text-pink-300">{item.likes}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Rate:</span>{" "}
                            <span className="font-bold text-emerald-400">{item.rate}%</span>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                />

                {metricFocus === 'reach_views' && (
                  <>
                    <Area
                      type="monotone"
                      dataKey="views"
                      name="Views"
                      stroke="#ec4899"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#pinkGrad)"
                    />
                    <Area
                      type="monotone"
                      dataKey="reach"
                      name="Reach"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#purpleGrad)"
                    />
                  </>
                )}

                {metricFocus === 'interactions' && (
                  <>
                    <Area
                      type="monotone"
                      dataKey="likes"
                      name="Likes"
                      stroke="#ec4899"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#pinkGrad)"
                    />
                    <Area
                      type="monotone"
                      dataKey="interactions"
                      name="Total Engagements"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#blueGrad)"
                    />
                  </>
                )}

                {metricFocus === 'engagement' && (
                  <Area
                    type="monotone"
                    dataKey="rate"
                    name="Engagement %"
                    stroke="#10b981"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#purpleGrad)"
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Format Breakdown & Benchmark Card (1 Col) */}
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Layers size={14} className="text-pink-400" />
                Format Efficiency
              </span>
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-pink-500/10 text-pink-300 border border-pink-500/20">
                Benchmarks
              </span>
            </div>

            <div className="space-y-4">
              {formatBreakdown.map((fmt) => (
                <div
                  key={fmt.type}
                  className="p-3.5 rounded-xl border border-white/5 bg-white/[0.01] hover:bg-white/[0.03] transition-colors"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold text-white flex items-center gap-1.5">
                      {fmt.type === 'reel' ? (
                        <Film size={13} className="text-purple-400" />
                      ) : (
                        <Layers size={13} className="text-blue-400" />
                      )}
                      {fmt.format}
                    </span>
                    <span className="text-[11px] font-mono text-emerald-400 font-semibold">
                      {fmt.avgRate}% avg eng
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-400 mt-2 pt-2 border-t border-white/5">
                    <div>
                      <span className="text-slate-500">Count:</span>{" "}
                      <span className="font-semibold text-slate-200">{fmt.count}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Avg Views:</span>{" "}
                      <span className="font-semibold text-slate-200">
                        {fmt.avgViews > 0 ? fmt.avgViews.toLocaleString() : '—'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Avg Likes:</span>{" "}
                      <span className="font-semibold text-slate-200">{fmt.avgLikes}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 p-3 rounded-xl border border-purple-500/20 bg-purple-500/[0.04] text-[11px] text-purple-200/90 leading-relaxed">
            <span className="font-semibold text-purple-300 flex items-center gap-1 mb-0.5">
              <Sparkles size={12} /> Strategic Signal:
            </span>
            Reels maintain your highest velocity for algorithmic discovery, while Carousels maximize saves and bookmark rate.
          </div>
        </div>
      </div>

      {/* Top Hashtag Performance Visual Ranking */}
      {topHashtagsData.length > 0 && (
        <div className="glass-card p-6 rounded-2xl border border-white/5 bg-white/[0.02]">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Tag size={16} className="text-pink-400" />
              <h4 className="text-sm font-bold text-white">Top Converting Hashtag Clusters</h4>
            </div>
            <span className="text-xs text-slate-400 font-mono">Ranked by Average Reach per Post</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {topHashtagsData.map((h) => (
              <div
                key={h.tag}
                className="p-3.5 rounded-xl border border-white/5 bg-white/[0.01] hover:border-pink-500/20 transition-all flex items-center justify-between"
              >
                <div>
                  <span className="text-xs font-mono font-bold text-pink-300">{h.tag}</span>
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    {h.postsCount} posts used • <span className="text-slate-500">{h.category}</span>
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-white">
                    {h.avgReach.toLocaleString()}
                  </span>
                  <p className="text-[9px] uppercase tracking-wider text-slate-500">avg reach</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
