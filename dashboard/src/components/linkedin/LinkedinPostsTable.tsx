"use client";

import React, { useState, useMemo } from "react";
import {
  Search,
  Filter,
  CheckCircle2,
  Clock,
  Copy,
  Check,
  RefreshCw,
  Trash2,
  ExternalLink,
  X,
  FileText,
  Hash,
  BookOpen,
  Share2,
} from "lucide-react";
import { LinkedinPostItem, linkedinApi } from "@/lib/linkedinApi";

interface Props {
  posts: LinkedinPostItem[];
  onRefresh: () => void;
}

export default function LinkedinPostsTable({ posts, onRefresh }: Props) {
  const [search, setSearch] = useState("");
  const [selectedAngle, setSelectedAngle] = useState("all");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [activePost, setActivePost] = useState<LinkedinPostItem | null>(null);
  const [copied, setCopied] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  // Available unique angles
  const angles = useMemo(() => {
    const set = new Set<string>();
    posts.forEach((p) => {
      if (p.angle_type) set.add(p.angle_type);
    });
    return Array.from(set);
  }, [posts]);

  // Filtered posts
  const filteredPosts = useMemo(() => {
    return posts.filter((post) => {
      const matchesSearch =
        search === "" ||
        post.topic.toLowerCase().includes(search.toLowerCase()) ||
        post.hook.toLowerCase().includes(search.toLowerCase()) ||
        post.snippet.toLowerCase().includes(search.toLowerCase());

      const matchesAngle =
        selectedAngle === "all" || post.angle_type === selectedAngle;

      const matchesStatus =
        selectedStatus === "all" ||
        (selectedStatus === "published" && Boolean(post.published_at)) ||
        (selectedStatus === "approved" && post.approved && !post.published_at) ||
        (selectedStatus === "pending" && !post.approved);

      return matchesSearch && matchesAngle && matchesStatus;
    });
  }, [posts, search, selectedAngle, selectedStatus]);

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  }

  async function handlePublish(postId: string) {
    if (!confirm("Are you sure you want to publish this post live to your connected LinkedIn profile?")) return;
    setPublishingId(postId);
    try {
      const res = await linkedinApi.publishPost(postId);
      if (res.success) {
        alert("Post published live to LinkedIn successfully!");
        onRefresh();
        if (activePost?.id === postId) {
          setActivePost((prev) =>
            prev ? { ...prev, published_at: res.published_at, linkedin_post_url: res.linkedin_post_url, approved: true } : null
          );
        }
      }
    } catch (err: any) {
      console.error("Publishing error:", err);
      alert(`Publishing failed: ${err.message || "Failed to publish"}`);
    } finally {
      setPublishingId(null);
    }
  }

  async function handleApprove(postId: string) {
    setApprovingId(postId);
    try {
      await linkedinApi.approvePost(postId);
      onRefresh();
      if (activePost?.id === postId) {
        setActivePost((prev) => (prev ? { ...prev, approved: true } : null));
      }
    } catch (err: any) {
      console.error("Approve error:", err);
      alert("Failed to approve post.");
    } finally {
      setApprovingId(null);
    }
  }

  async function handleRegenerate(postId: string) {
    setRegeneratingId(postId);
    try {
      await linkedinApi.regeneratePost(postId);
      onRefresh();
    } catch (err) {
      console.error("Failed to regenerate post:", err);
    } finally {
      setRegeneratingId(null);
    }
  }

  async function handleDelete(postId: string) {
    if (!confirm("Are you sure you want to delete this LinkedIn post?")) return;
    setDeletingId(postId);
    try {
      await linkedinApi.deletePost(postId);
      if (activePost?.id === postId) setActivePost(null);
      onRefresh();
    } catch (err) {
      console.error("Failed to delete post:", err);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* ── Filter Bar ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-900/60 p-4 backdrop-blur-xl">
        <div className="relative min-w-[240px] flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search posts by topic, hook, or keywords..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-slate-950/60 py-2 pl-9 pr-3 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Angle Filter */}
          <select
            value={selectedAngle}
            onChange={(e) => setSelectedAngle(e.target.value)}
            className="rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-slate-300 focus:border-blue-500 focus:outline-none"
          >
            <option value="all">All Content Angles</option>
            {angles.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-slate-300 focus:border-blue-500 focus:outline-none"
          >
            <option value="all">All Statuses</option>
            <option value="published">Live on LinkedIn</option>
            <option value="approved">Approved (Ready to Publish)</option>
            <option value="pending">Pending QA / Review</option>
          </select>
        </div>
      </div>

      {/* ── Posts Table ── */}
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-900/60 backdrop-blur-xl shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-white/10 bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="py-3.5 pl-5 pr-3 font-semibold">Topic & Hook</th>
                <th className="py-3.5 px-3 font-semibold">Angle Type</th>
                <th className="py-3.5 px-3 font-semibold">Metrics</th>
                <th className="py-3.5 px-3 font-semibold">QA Status</th>
                <th className="py-3.5 px-3 font-semibold">Created</th>
                <th className="py-3.5 pl-3 pr-5 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredPosts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-xs text-slate-500 font-mono">
                    No LinkedIn posts match your filter criteria.
                  </td>
                </tr>
              ) : (
                filteredPosts.map((post) => (
                  <tr
                    key={post.id}
                    className="hover:bg-white/[0.02] transition-colors group cursor-pointer"
                    onClick={() => setActivePost(post)}
                  >
                    <td className="py-4 pl-5 pr-3 max-w-sm">
                      <div className="font-semibold text-white group-hover:text-blue-400 transition-colors line-clamp-1 mb-1">
                        {post.topic}
                      </div>
                      <div className="text-[11px] text-slate-400 line-clamp-2 italic font-mono">
                        "{post.hook || post.snippet}"
                      </div>
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap">
                      <span className="inline-flex items-center rounded-lg border border-blue-500/20 bg-blue-500/10 px-2.5 py-1 text-[11px] font-medium text-blue-300">
                        {post.angle_type || "Standard Hook"}
                      </span>
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
                        <span title="Word Count">{post.word_count || 0} words</span>
                        <span className="text-slate-600">•</span>
                        <span title="Hashtag Count">#{post.hashtag_count || 0}</span>
                      </div>
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap">
                      {post.published_at ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-blue-400">
                          <Share2 className="h-3 w-3" />
                          Live on LinkedIn
                        </span>
                      ) : post.approved ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" />
                          Approved
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-amber-400">
                          <Clock className="h-3 w-3" />
                          Pending Review
                        </span>
                      )}
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap font-mono text-[11px] text-slate-500">
                      {post.created_at ? new Date(post.created_at).toLocaleDateString() : "—"}
                    </td>

                    <td
                      className="py-4 pl-3 pr-5 text-right whitespace-nowrap"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-end gap-1.5">
                        {post.published_at && post.linkedin_post_url ? (
                          <a
                            href={post.linkedin_post_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 rounded-lg border border-blue-500/30 bg-blue-500/10 px-2 py-1 text-[11px] font-semibold text-blue-300 hover:bg-blue-500/20 transition-all"
                            title="View Live on LinkedIn"
                          >
                            <ExternalLink className="h-3 w-3" />
                            <span>Live</span>
                          </a>
                        ) : post.approved ? (
                          <button
                            onClick={() => handlePublish(post.id)}
                            disabled={publishingId === post.id}
                            className="flex items-center gap-1 rounded-lg bg-blue-600 hover:bg-blue-500 px-2.5 py-1 text-[11px] font-semibold text-white shadow-md shadow-blue-500/20 transition-all disabled:opacity-50"
                            title="Publish Live to LinkedIn"
                          >
                            <Share2 className={`h-3 w-3 ${publishingId === post.id ? "animate-spin" : ""}`} />
                            <span>Publish</span>
                          </button>
                        ) : (
                          <button
                            onClick={() => handleApprove(post.id)}
                            disabled={approvingId === post.id}
                            className="flex items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/20 transition-all disabled:opacity-50"
                            title="Approve Post"
                          >
                            <CheckCircle2 className={`h-3 w-3 ${approvingId === post.id ? "animate-spin" : ""}`} />
                            <span>Approve</span>
                          </button>
                        )}

                        <button
                          onClick={() => setActivePost(post)}
                          className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-300 hover:border-blue-500/40 hover:bg-blue-500/10 hover:text-blue-300 transition-all"
                          title="Inspect Post"
                        >
                          <BookOpen className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => handleRegenerate(post.id)}
                          disabled={regeneratingId === post.id}
                          className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-300 hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-300 transition-all disabled:opacity-50"
                          title="Regenerate Fresh Angle"
                        >
                          <RefreshCw
                            className={`h-3.5 w-3.5 ${regeneratingId === post.id ? "animate-spin" : ""}`}
                          />
                        </button>
                        <button
                          onClick={() => handleDelete(post.id)}
                          disabled={deletingId === post.id}
                          className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-400 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300 transition-all disabled:opacity-50"
                          title="Delete Post"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Post Inspector Modal ── */}
      {activePost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-2xl rounded-2xl border border-white/15 bg-slate-900 p-6 shadow-2xl max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-300 uppercase tracking-wider">
                    {activePost.angle_type}
                  </span>
                  {activePost.published_at ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-semibold text-blue-400">
                      <Share2 className="h-3 w-3" />
                      Live on LinkedIn
                    </span>
                  ) : activePost.approved ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      Approved
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                      <Clock className="h-3 w-3" />
                      Review Required
                    </span>
                  )}
                </div>
                <h3 className="text-base font-bold text-white">{activePost.topic}</h3>
              </div>
              <button
                onClick={() => setActivePost(null)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Post Content Scrollable Area */}
            <div className="flex-1 overflow-y-auto py-4 space-y-4">
              {/* Hook Analysis Banner */}
              <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3.5">
                <div className="flex items-center gap-1.5 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-1">
                  <Hash className="h-3.5 w-3.5" />
                  Hook Statement (First 140 Chars)
                </div>
                <p className="text-xs text-slate-200 font-mono italic">
                  "{activePost.hook || activePost.snippet.slice(0, 140)}"
                </p>
              </div>

              {/* Full Post Body */}
              <div className="rounded-xl border border-white/10 bg-slate-950 p-4">
                <div className="whitespace-pre-wrap font-sans text-xs text-slate-200 leading-relaxed space-y-2">
                  {activePost.full_text || activePost.snippet}
                </div>
              </div>

              {/* Character & Word Metrics */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Word Count</div>
                  <div className="text-base font-bold text-white font-mono mt-0.5">
                    {activePost.word_count || (activePost.full_text ? activePost.full_text.split(/\s+/).length : 0)}
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Character Count</div>
                  <div className="text-base font-bold text-white font-mono mt-0.5">
                    {(activePost.full_text || activePost.snippet).length}
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider">Hashtags</div>
                  <div className="text-base font-bold text-blue-400 font-mono mt-0.5">
                    #{activePost.hashtag_count || 3}
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-between border-t border-white/10 pt-4">
              <button
                onClick={() => handleRegenerate(activePost.id)}
                disabled={regeneratingId === activePost.id}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-xs font-medium text-slate-300 hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${regeneratingId === activePost.id ? "animate-spin" : ""}`} />
                Regenerate Angle
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleCopy(activePost.full_text || activePost.snippet)}
                  className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 px-3.5 py-2 text-xs font-medium text-slate-300 transition-all"
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copied" : "Copy"}
                </button>

                {activePost.published_at && activePost.linkedin_post_url ? (
                  <a
                    href={activePost.linkedin_post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 transition-all"
                  >
                    <ExternalLink className="h-4 w-4" />
                    View Live on LinkedIn
                  </a>
                ) : activePost.approved ? (
                  <button
                    onClick={() => handlePublish(activePost.id)}
                    disabled={publishingId === activePost.id}
                    className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 transition-all disabled:opacity-50"
                  >
                    <Share2 className={`h-4 w-4 ${publishingId === activePost.id ? "animate-spin" : ""}`} />
                    {publishingId === activePost.id ? "Publishing..." : "Publish to LinkedIn"}
                  </button>
                ) : (
                  <button
                    onClick={() => handleApprove(activePost.id)}
                    disabled={approvingId === activePost.id}
                    className="flex items-center gap-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-emerald-500/20 transition-all disabled:opacity-50"
                  >
                    <CheckCircle2 className={`h-4 w-4 ${approvingId === activePost.id ? "animate-spin" : ""}`} />
                    Approve Post
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
