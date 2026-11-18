"use client";

import React, { useState } from 'react';
import {
  Search,
  Users,
  Film,
  Sparkles,
  ExternalLink,
  ChevronRight,
  TrendingUp,
  Tag,
  CheckCircle2,
  AlertCircle,
  X,
} from 'lucide-react';
import { request } from '@/lib/apiClient';

interface ResolvedProfile {
  handle: string;
  title: string;
  followers: number;
  total_posts: number;
  bio: string;
  profile_url: string;
  avatar_url?: string | null;
  is_live_enriched: boolean;
  representative_topics: string[];
}

interface InstagramProfileInspectorProps {
  myFollowers?: number;
  myHandle?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function InstagramProfileInspector({
  myFollowers = 246,
  myHandle = '@codingindiaai',
  isOpen,
  onClose,
}: InstagramProfileInspectorProps) {
  const [handleInput, setHandleInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResolvedProfile | null>(null);

  const handleInspect = async (queryHandle?: string) => {
    const target = (queryHandle || handleInput).trim().replace(/^@/, '');
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      const data = await request<ResolvedProfile>(`/instagram-analytics/inspect?handle=${encodeURIComponent(target)}`);
      setResult(data);
    } catch (err: any) {
      setError(err?.message || 'Could not resolve Instagram profile. Please check the handle.');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl glass-card rounded-3xl border border-white/10 bg-slate-900/95 shadow-2xl p-6 sm:p-8 space-y-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-pink-500 to-purple-600 p-[1px] flex items-center justify-center">
              <div className="w-full h-full bg-slate-950 rounded-[11px] flex items-center justify-center text-pink-400">
                <Search size={20} />
              </div>
            </div>
            <div>
              <h3 className="text-lg font-bold text-white tracking-tight">
                Live Instagram Profile Inspector
              </h3>
              <p className="text-xs text-slate-400">
                Audit any creator or competitor account in real time without login
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg border border-white/10 text-slate-400 hover:text-white hover:bg-white/5 flex items-center justify-center transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search Bar */}
        <div className="space-y-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleInspect();
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500 font-mono text-sm">@</span>
              <input
                type="text"
                placeholder="Enter Instagram handle (e.g. codingindiaai, techcreator)..."
                value={handleInput}
                onChange={(e) => setHandleInput(e.target.value)}
                className="w-full pl-8 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-pink-500/50 transition-all font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={loading || !handleInput.trim()}
              className="px-5 py-2.5 bg-gradient-to-r from-pink-500 to-purple-600 hover:from-pink-600 hover:to-purple-700 text-white text-xs font-semibold rounded-xl shadow-lg transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Inspecting…
                </>
              ) : (
                <>
                  <Search size={14} />
                  Inspect Profile
                </>
              )}
            </button>
          </form>

          {/* Quick presets */}
          <div className="flex items-center gap-2 pt-1">
            <span className="text-[11px] text-slate-500">Suggested:</span>
            {['codingindiaai', 'python.hub', 'ai.creators', 'openai'].map((suggested) => (
              <button
                key={suggested}
                onClick={() => {
                  setHandleInput(suggested);
                  handleInspect(suggested);
                }}
                className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-white/5 text-slate-400 hover:text-pink-300 hover:bg-white/10 transition-colors"
              >
                @{suggested}
              </button>
            ))}
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="flex items-center gap-2 p-4 rounded-xl border border-red-500/20 bg-red-500/[0.06] text-xs text-red-300">
            <AlertCircle size={16} className="text-red-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Resolved Profile Result Card */}
        {result && (
          <div className="space-y-6 animate-in fade-in-50 duration-300">
            <div className="p-5 rounded-2xl border border-white/10 bg-gradient-to-br from-purple-900/20 via-pink-900/10 to-slate-900/40 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-pink-500 to-purple-600 p-[2px] shadow-lg flex-shrink-0">
                    <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center font-bold text-lg text-pink-400">
                      {result.handle.replace('@', '').slice(0, 2).toUpperCase()}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-white flex items-center gap-2">
                      {result.title}
                      {result.is_live_enriched && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                          <CheckCircle2 size={10} /> Live Verified
                        </span>
                      )}
                    </h4>
                    <p className="text-xs font-mono text-pink-300 mt-0.5">{result.handle}</p>
                  </div>
                </div>

                <a
                  href={result.profile_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white glass-card rounded-lg border border-white/10 hover:bg-white/10 transition-colors"
                >
                  <ExternalLink size={12} />
                  Open Instagram
                </a>
              </div>

              {/* Bio */}
              <p className="text-xs text-slate-300 leading-relaxed bg-black/20 p-3 rounded-xl border border-white/5">
                {result.bio || "No public bio provided."}
              </p>

              {/* Stats Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    <Users size={12} className="text-pink-400" /> Followers
                  </div>
                  <p className="text-lg font-bold text-white font-mono">{result.followers.toLocaleString()}</p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    <Film size={12} className="text-purple-400" /> Posts
                  </div>
                  <p className="text-lg font-bold text-white font-mono">{result.total_posts}</p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    <TrendingUp size={12} className="text-emerald-400" /> Est. Rate
                  </div>
                  <p className="text-lg font-bold text-emerald-400 font-mono">
                    {result.followers > 0 ? `${((result.total_posts * 14) / result.followers * 10).toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                  <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase tracking-wider mb-1">
                    <Sparkles size={12} className="text-amber-400" /> Niche Tier
                  </div>
                  <p className="text-xs font-bold text-amber-300 font-mono mt-1">
                    {result.followers >= 100000 ? 'Macro Creator' : result.followers >= 10000 ? 'Micro Influencer' : 'Nano / Emerging'}
                  </p>
                </div>
              </div>

              {/* Topics / Keywords */}
              {result.representative_topics.length > 0 && (
                <div className="pt-2">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                    <Tag size={11} /> Niche Keyword Clusters
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {result.representative_topics.map((t, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-0.5 rounded-md text-[11px] font-mono bg-white/5 border border-white/10 text-slate-300"
                      >
                        #{t.toLowerCase()}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Benchmarking Against Your Account */}
            <div className="p-4 rounded-2xl border border-white/5 bg-white/[0.01] space-y-3">
              <h5 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <TrendingUp size={13} className="text-pink-400" />
                Benchmark vs Your Account ({myHandle || '@codingindiaai'})
              </h5>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3 rounded-xl bg-black/20 border border-white/5">
                  <span className="text-slate-400">Audience Delta:</span>
                  <p className="font-mono font-bold text-white mt-1">
                    {result.followers >= myFollowers ? (
                      <span className="text-purple-300">+{(result.followers - myFollowers).toLocaleString()} more followers</span>
                    ) : (
                      <span className="text-emerald-400">+{(myFollowers - result.followers).toLocaleString()} your advantage</span>
                    )}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-black/20 border border-white/5">
                  <span className="text-slate-400">Content Volume:</span>
                  <p className="font-mono font-bold text-white mt-1">
                    {result.total_posts} published posts
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
