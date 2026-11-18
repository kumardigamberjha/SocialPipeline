"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Linkedin,
  TrendingUp,
  Users,
  Sparkles,
  RefreshCw,
  Clock,
  CheckCircle2,
  Cpu,
  Target,
  FileText,
  BarChart3,
  Calendar,
  Share2,
  Plus,
  Layers,
  HelpCircle,
  ExternalLink,
  ShieldCheck,
  Radio,
  Eye,
  MessageSquare,
  ThumbsUp,
  LogOut,
  AlertCircle,
} from "lucide-react";
import {
  LinkedinAnalytics,
  EMPTY_LINKEDIN_ANALYTICS,
  linkedinApi,
} from "@/lib/linkedinApi";
import {
  AnglePerformanceChart,
  WordCountBreakdownChart,
  OfficialEngagementChart,
} from "./LinkedinCharts";
import LinkedinAgentPipelineCard from "./LinkedinAgentPipelineCard";
import LinkedinPostsTable from "./LinkedinPostsTable";
import LinkedinLeadProspector from "./LinkedinLeadProspector";
import LinkedinGeneratorModal from "./LinkedinGeneratorModal";

export default function LinkedinAnalyticsDashboard() {
  const [analytics, setAnalytics] = useState<LinkedinAnalytics>(EMPTY_LINKEDIN_ANALYTICS);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [timeRange, setTimeRange] = useState("all_time");
  const [tab, setTab] = useState<"overview" | "pipeline" | "ledger" | "leads">("overview");
  const [isGeneratorOpen, setIsGeneratorOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await linkedinApi.getAnalytics(timeRange);
      setAnalytics(data);
    } catch (err) {
      console.error("Failed to load LinkedIn analytics:", err);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleConnectOAuth() {
    setConnecting(true);
    try {
      const res = await linkedinApi.getAuthUrl();
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err) {
      console.error("Failed to start LinkedIn OAuth:", err);
      alert("Failed to start LinkedIn OAuth. Please verify LINKEDIN_CLIENT_ID in app/.env.");
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm("Are you sure you want to disconnect your LinkedIn account?")) return;
    try {
      await linkedinApi.disconnect();
      loadData();
    } catch (err) {
      console.error("Failed to disconnect LinkedIn:", err);
    }
  }

  const [publishingId, setPublishingId] = useState<string | null>(null);

  async function handlePublishPost(postId: string) {
    if (!confirm("Are you sure you want to publish this post live to your connected LinkedIn profile?")) return;
    setPublishingId(postId);
    try {
      const res = await linkedinApi.publishPost(postId);
      if (res.success) {
        alert("Post successfully published live to your LinkedIn profile! Metrics will begin streaming.");
        await loadData();
      }
    } catch (err: any) {
      console.error("Publishing error:", err);
      alert(`Publishing failed: ${err.message || "Please check your LinkedIn API connection"}`);
    } finally {
      setPublishingId(null);
    }
  }

  const readyPost = analytics.recent_posts?.find((p) => p.approved && !p.published_at);

  const kpis = [
    {
      title: "Posts Generated",
      value: analytics.total_posts.toString(),
      sub: `${analytics.approval_rate}% Approved (${analytics.approved_posts}/${analytics.total_posts})`,
      icon: FileText,
      color: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    },
    {
      title: "LinkedIn API Status",
      value: analytics.api_connected ? "Connected" : "Not Linked",
      sub: analytics.api_connected
        ? (analytics.account?.name || "Official API Live")
        : "Connect for official stats",
      icon: Linkedin,
      color: analytics.api_connected
        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
        : "text-amber-400 bg-amber-500/10 border-amber-500/20",
    },
    {
      title: "Official API Impressions",
      value: analytics.official_stats?.impressions != null
        ? analytics.official_stats.impressions.toLocaleString()
        : "—",
      sub: analytics.api_connected ? "Direct from LinkedIn API" : "Requires API connection",
      icon: Eye,
      color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
    },
    {
      title: "Official API Engagement",
      value: analytics.official_stats?.engagement_rate != null
        ? `${analytics.official_stats.engagement_rate}%`
        : "—",
      sub: analytics.api_connected ? "Reactions, comments, reshares" : "Awaiting API connection",
      icon: ThumbsUp,
      color: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
    },
    {
      title: "QA First-Pass Rate",
      value: `${analytics.pipeline_health.cycle_1_pass_rate}%`,
      sub: `${analytics.pipeline_health.avg_rewrite_cycles} avg rewrite cycles`,
      icon: Cpu,
      color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    },
    {
      title: "B2B Outreach Leads",
      value: analytics.leads_funnel.total_leads.toLocaleString(),
      sub: `${analytics.leads_funnel.high_fit_count} High-Fit Scores (≥9.0)`,
      icon: Target,
      color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
    },
  ];

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
      {/* ── Top Header & Actions ── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-white/5 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="flex h-6 items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-blue-400">
              <Linkedin className="h-3 w-3" />
              Official API & Multi-Agent Engine
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            LinkedIn Automation & Analytics
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Pure LinkedIn API Metrics, 4-Agent Generation Telemetry & B2B Lead Prospecting
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Time Range Pills */}
          <div className="flex rounded-xl border border-white/10 bg-slate-900/80 p-1">
            {[
              { id: "7d", label: "7D" },
              { id: "30d", label: "30D" },
              { id: "90d", label: "90D" },
              { id: "all_time", label: "All" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTimeRange(t.id)}
                className={`rounded-lg px-3 py-1 text-xs font-mono transition-all ${
                  timeRange === t.id
                    ? "bg-blue-600 text-white font-bold shadow-md shadow-blue-500/20"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Refresh Button */}
          <button
            onClick={loadData}
            disabled={loading}
            className="flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 text-xs font-medium text-slate-300 hover:bg-white/10 transition-colors disabled:opacity-50"
            title="Refresh Telemetry"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          {/* Generate Post CTA */}
          <button
            onClick={() => setIsGeneratorOpen(true)}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 hover:from-blue-500 hover:to-indigo-500 transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>Generate Post</span>
          </button>
        </div>
      </div>

      {/* ── Official LinkedIn API Integration Banner ── */}
      <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-4 backdrop-blur-xl shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#0A66C2] text-white shadow-lg shadow-blue-500/20">
              <Linkedin className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">
                  LinkedIn Developer API
                </h3>
                {analytics.api_connected ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-emerald-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Connected & Verified
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-amber-400">
                    Awaiting Connection
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {analytics.api_connected
                  ? `Authenticated as ${analytics.account?.name || "LinkedIn Member"} (${analytics.account?.email || "No email"}). Live impressions and reactions stream purely via API.`
                  : "Connect your LinkedIn profile or company page via OAuth 2.0 to stream official API impressions, reactions, and engagement metrics directly."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {analytics.api_connected ? (
              <button
                onClick={handleDisconnect}
                className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-300 transition-all"
              >
                <LogOut className="h-3.5 w-3.5" />
                Disconnect
              </button>
            ) : (
              <button
                onClick={handleConnectOAuth}
                disabled={connecting}
                className="flex items-center gap-2 rounded-xl bg-[#0A66C2] hover:bg-[#004182] px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 transition-all disabled:opacity-50"
              >
                <Linkedin className="h-4 w-4" />
                {connecting ? "Connecting..." : "Connect LinkedIn Account"}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Top KPI Matrix Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.title}
              className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 backdrop-blur-xl shadow-lg flex flex-col justify-between hover:border-white/15 transition-all"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-medium text-slate-400 truncate">
                  {kpi.title}
                </span>
                <div className={`flex h-7 w-7 items-center justify-center rounded-lg border ${kpi.color}`}>
                  <Icon className="h-3.5 w-3.5" />
                </div>
              </div>
              <div>
                <div className="text-2xl font-bold font-mono text-white tracking-tight">
                  {kpi.value}
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-1 truncate">
                  {kpi.sub}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Navigation Tabs ── */}
      <div className="flex border-b border-white/10 gap-2">
        {[
          { id: "overview", label: "Overview & Growth", icon: BarChart3 },
          { id: "pipeline", label: "AI Agent Pipeline & QA", icon: Cpu },
          { id: "ledger", label: "Content Ledger & Archive", icon: FileText },
          { id: "leads", label: "B2B Leads & Outreach", icon: Target },
        ].map((item) => {
          const active = tab === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setTab(item.id as any)}
              className={`relative flex items-center gap-2 pb-3 pt-2 px-3 text-xs font-semibold transition-all ${
                active ? "text-blue-400" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
              {active && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
              )}
            </button>
          );
        })}
      </div>

      {/* ── Tab Content Views ── */}
      {tab === "overview" && (
        <div className="space-y-6">
          {/* Row 1: Official API Telemetry & Official Engagement Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
              <div className="flex items-center justify-between mb-4 border-b border-white/5 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Official LinkedIn API Telemetry
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Live measurements fetched directly from LinkedIn Developer endpoints
                  </p>
                </div>
                <span className="rounded-md border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-mono text-blue-400">
                  Official API Data
                </span>
              </div>

              {analytics.api_connected ? (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-3">
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
                      <div className="text-[11px] text-slate-400">Published Posts</div>
                      <div className="text-2xl font-bold font-mono text-white mt-1">
                        {analytics.official_stats?.posts_published ?? 0}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
                      <div className="text-[11px] text-slate-400">Total Impressions</div>
                      <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">
                        {analytics.official_stats?.impressions ?? 0}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
                      <div className="text-[11px] text-slate-400">Reactions & Likes</div>
                      <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
                        {analytics.official_stats?.reactions ?? 0}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
                      <div className="text-[11px] text-slate-400">Comments & Reshares</div>
                      <div className="text-2xl font-bold font-mono text-indigo-400 mt-1">
                        {(analytics.official_stats?.comments ?? 0) + (analytics.official_stats?.reposts ?? 0)}
                      </div>
                    </div>
                  </div>

                  {/* Contextual Action Banner for 0 Published Posts */}
                  {(analytics.official_stats?.posts_published ?? 0) === 0 && (
                    <div className="mt-3 rounded-xl border border-blue-500/20 bg-gradient-to-r from-blue-950/40 via-indigo-950/30 to-slate-900/60 p-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 mt-0.5">
                            <Sparkles className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="text-xs font-bold text-white">
                                {readyPost
                                  ? "1 Approved Post Ready to Publish!"
                                  : "Draft Posts in Pipeline Queue"}
                              </h4>
                              <span className="rounded-full bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 text-[10px] font-mono text-blue-300">
                                Official API Verification
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-300 mt-1 max-w-xl leading-relaxed">
                              {readyPost ? (
                                <>
                                  Why are impressions 0? Your LinkedIn account is verified, but none of your {analytics.total_posts} generated posts have been published yet. Post: <strong className="text-white">"{readyPost.topic}"</strong> has passed QA and is ready!
                                </>
                              ) : (
                                <>
                                  Metrics are 0 because no posts have been published to LinkedIn yet. Review and approve your draft posts in the Content Ledger to publish them live.
                                </>
                              )}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          {readyPost && (
                            <button
                              onClick={() => handlePublishPost(readyPost.id)}
                              disabled={publishingId === readyPost.id}
                              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 px-3.5 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 transition-all disabled:opacity-50"
                            >
                              <Share2 className={`h-3.5 w-3.5 ${publishingId === readyPost.id ? "animate-spin" : ""}`} />
                              <span>{publishingId === readyPost.id ? "Publishing..." : "Publish Post Now"}</span>
                            </button>
                          )}
                          <button
                            onClick={() => setTab("ledger")}
                            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-2 text-xs font-medium text-slate-300 transition-colors"
                          >
                            <span>View All Posts ({analytics.total_posts})</span>
                            <ExternalLink className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* If posts are published, show live posts summary */}
                  {(analytics.official_stats?.posts_published ?? 0) > 0 && (
                    <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-emerald-400 font-semibold">
                          <CheckCircle2 className="h-4 w-4" />
                          <span>{analytics.official_stats?.posts_published} Post(s) Published Live to LinkedIn</span>
                        </div>
                        <button
                          onClick={() => setTab("ledger")}
                          className="text-xs text-slate-300 hover:text-white flex items-center gap-1 font-mono"
                        >
                          <span>Manage Posts</span>
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex h-56 flex-col items-center justify-center p-6 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 mb-3">
                    <Radio className="h-6 w-6" />
                  </div>
                  <h4 className="text-sm font-semibold text-white mb-1">
                    Connect LinkedIn API for Live Stream Metrics
                  </h4>
                  <p className="text-xs text-slate-400 max-w-md leading-relaxed mb-4">
                    Zero fake or estimated reach numbers. Click below to authenticate your account and stream official API performance metrics.
                  </p>
                  <button
                    onClick={handleConnectOAuth}
                    className="flex items-center gap-2 rounded-xl bg-[#0A66C2] hover:bg-[#004182] px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-500/20 transition-all"
                  >
                    <Linkedin className="h-4 w-4" />
                    Connect LinkedIn Account
                  </button>
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
              <div className="mb-3 border-b border-white/5 pb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Official Engagement Share
                </h3>
                <p className="text-[11px] text-slate-500">
                  Strictly from LinkedIn API reaction & comment edges
                </p>
              </div>
              <OfficialEngagementChart
                stats={analytics.official_stats}
                apiConnected={analytics.api_connected}
              />
            </div>
          </div>

          {/* Row 2: Real Database Content Analytics */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
              <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Content Angle Distribution (Database)
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Real post generation breakdown & approval count by angle type
                  </p>
                </div>
                <span className="text-[10px] font-mono text-slate-400">
                  {analytics.total_posts} Real Posts
                </span>
              </div>
              <AnglePerformanceChart data={analytics.angle_distribution} />
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
              <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Word Count Distribution (Database)
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Actual length distribution across generated posts in database
                  </p>
                </div>
                <span className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-mono text-indigo-300">
                  Avg: {analytics.avg_word_count} words
                </span>
              </div>
              <WordCountBreakdownChart posts={analytics.recent_posts} />
            </div>
          </div>

          {/* Publishing Windows Card */}
          <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
            <div className="flex items-center gap-2 mb-3 border-b border-white/5 pb-3">
              <Calendar className="h-4 w-4 text-blue-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Recommended LinkedIn Publishing Windows
              </h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
                <div className="font-semibold text-white flex items-center justify-between">
                  <span>Tuesday - Thursday</span>
                  <span className="text-emerald-400 font-mono text-[11px]">Primary Peak</span>
                </div>
                <div className="text-slate-400 text-[11px] mt-1">
                  08:00 AM - 10:30 AM (Target timezone)
                </div>
                <p className="text-slate-500 text-[10px] mt-2">
                  Highest executive feed consumption window during morning transit & prep.
                </p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
                <div className="font-semibold text-white flex items-center justify-between">
                  <span>Wednesday Mid-Day</span>
                  <span className="text-blue-400 font-mono text-[11px]">Secondary</span>
                </div>
                <div className="text-slate-400 text-[11px] mt-1">
                  12:30 PM - 02:00 PM (Target timezone)
                </div>
                <p className="text-slate-500 text-[10px] mt-2">
                  Lunchtime professional catch-up with highest comment conversation rates.
                </p>
              </div>

              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
                <div className="font-semibold text-white flex items-center justify-between">
                  <span>Sunday Evening Prep</span>
                  <span className="text-purple-400 font-mono text-[11px]">Strategy Spike</span>
                </div>
                <div className="text-slate-400 text-[11px] mt-1">
                  06:30 PM - 08:30 PM (Target timezone)
                </div>
                <p className="text-slate-500 text-[10px] mt-2">
                  High-intent reading for deep-dive technical blogs & framework posts.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "pipeline" && (
        <LinkedinAgentPipelineCard pipelineHealth={analytics.pipeline_health} />
      )}

      {tab === "ledger" && (
        <LinkedinPostsTable
          posts={analytics.recent_posts}
          onRefresh={loadData}
        />
      )}

      {tab === "leads" && (
        <LinkedinLeadProspector leadsFunnel={analytics.leads_funnel} />
      )}

      {/* ── Quick Generator Modal ── */}
      <LinkedinGeneratorModal
        isOpen={isGeneratorOpen}
        onClose={() => setIsGeneratorOpen(false)}
        onSuccess={loadData}
      />
    </div>
  );
}
