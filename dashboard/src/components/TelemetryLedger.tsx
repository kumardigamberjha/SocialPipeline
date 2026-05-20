"use client";

import { motion } from "framer-motion";
import {
  TrendingUp,
  CheckCircle2,
  Clock,
  Eye,
  ThumbsUp,
  MessageSquare,
  MousePointerClick,
  BarChart3,
} from "lucide-react";

import { useState, useEffect } from "react";

interface PostMetric {
  id: string;
  topic: string;
  status: "published" | "running" | "failed" | "completed";
  final_result: string | null;
  duration_seconds: number | null;
  // Mocked for display
  impressions: string;
  likes: string;
  comments: string;
  ctr: string;
  trendUp: boolean;
}

const statusBadge: Record<string, any> = {
  completed: {
    icon: CheckCircle2,
    color: "text-green-400",
    bg: "bg-green-500/10 border-green-500/20",
  },
  published: {
    icon: CheckCircle2,
    color: "text-green-400",
    bg: "bg-green-500/10 border-green-500/20",
  },
  running: {
    icon: Clock,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
  },
  failed: {
    icon: Clock,
    color: "text-red-400",
    bg: "bg-red-500/10 border-red-500/20",
  },
};


export default function TelemetryLedger() {
  const [metrics, setMetrics] = useState<PostMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_BACKEND_API || "http://127.0.0.1:8000";
    fetch(`${baseUrl}/api/runs`)
      .then(res => res.json())
      .then((data: any[]) => {
        const mapped = data.map((run, i) => ({
          id: run.id,
          topic: run.topic || "Unknown Topic",
          status: run.status || "running",
          final_result: run.final_result,
          duration_seconds: run.duration_seconds,
          impressions: run.status === "completed" ? Math.floor(Math.random() * 10000 + 1000).toLocaleString() : "—",
          likes: run.status === "completed" ? Math.floor(Math.random() * 500 + 50).toString() : "—",
          comments: run.status === "completed" ? Math.floor(Math.random() * 100 + 10).toString() : "—",
          ctr: run.status === "completed" ? (Math.random() * 5 + 1).toFixed(1) + "%" : "—",
          trendUp: run.status === "completed",
        }));
        setMetrics(mapped);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch runs", err);
        setLoading(false);
      });
  }, []);

  return (
    <section className="w-full">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="flex items-center gap-2 mb-6">
          <div className="w-1 h-4 bg-gradient-to-b from-cyan-500 to-blue-500 rounded-full" />
          <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
            Telemetry Ledger
          </h2>
          <span className="text-[10px] text-slate-600 ml-2">
            Historical Data
          </span>
          <div className="flex-1 h-px bg-gradient-to-r from-white/10 to-transparent ml-2" />
        </div>

        {/* Table */}
        <div className="glass-card rounded-xl overflow-hidden">
          {/* Table Header */}
          <div className="hidden md:grid grid-cols-12 gap-4 px-5 py-3 border-b border-white/5 text-[10px] font-bold tracking-[0.2em] uppercase text-slate-500">
            <div className="col-span-4 flex items-center gap-1.5">
              <BarChart3 className="w-3 h-3" />
              Topic
            </div>
            <div className="col-span-1 text-center">Status</div>
            <div className="col-span-2 text-center flex items-center justify-center gap-1">
              <Eye className="w-3 h-3" />
              Impressions
            </div>
            <div className="col-span-1 text-center flex items-center justify-center gap-1">
              <ThumbsUp className="w-3 h-3" />
              Likes
            </div>
            <div className="col-span-2 text-center flex items-center justify-center gap-1">
              <MessageSquare className="w-3 h-3" />
              Comments
            </div>
            <div className="col-span-2 text-center flex items-center justify-center gap-1">
              <MousePointerClick className="w-3 h-3" />
              CTR
            </div>
          </div>

          {metrics.length === 0 && !loading && (
            <div className="p-8 text-center text-slate-500 text-sm">No historical runs found in Supabase.</div>
          )}
          {loading && (
            <div className="p-8 text-center text-slate-500 text-sm animate-pulse">Loading telemetry from backend...</div>
          )}

          {/* Table Rows */}
          {metrics.map((metric, index) => {
            const badge = statusBadge[metric.status] || statusBadge.running;
            const BadgeIcon = badge.icon;
            const isExpanded = expandedId === metric.id;

            return (
              <div key={metric.id} className="border-b border-white/5 last:border-b-0">
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05, duration: 0.3 }}
                  onClick={() => setExpandedId(isExpanded ? null : metric.id)}
                  className={`
                    grid grid-cols-1 md:grid-cols-12 gap-2 md:gap-4 
                    px-5 py-4 cursor-pointer
                    hover:bg-white/[0.05] transition-colors duration-200
                    group
                  `}
                >
                  {/* Topic */}
                  <div className="col-span-1 md:col-span-4 flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-xs font-mono text-slate-500">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white group-hover:text-blue-300 transition-colors line-clamp-2">
                        {metric.topic}
                      </p>
                      {/* Mobile-only status */}
                      <div className="flex md:hidden items-center gap-1 mt-1">
                        <BadgeIcon className={`w-3 h-3 ${badge.color}`} />
                        <span
                          className={`text-[10px] font-medium tracking-wider uppercase ${badge.color}`}
                        >
                          {metric.status}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Status (Desktop) */}
                  <div className="hidden md:flex col-span-1 items-center justify-center">
                    <span
                      className={`
                      flex items-center gap-1 px-2 py-1 rounded-md border
                      text-[9px] font-bold tracking-wider uppercase
                      ${badge.bg} ${badge.color}
                    `}
                    >
                      <BadgeIcon className="w-3 h-3" />
                      {metric.status}
                    </span>
                  </div>

                  {/* Mobile metrics grid */}
                  <div className="grid grid-cols-4 gap-3 md:hidden">
                    <MetricCell label="Views" value={metric.impressions} trendUp={metric.trendUp} />
                    <MetricCell label="Likes" value={metric.likes} trendUp={metric.trendUp} />
                    <MetricCell label="Comments" value={metric.comments} trendUp={metric.trendUp} />
                    <MetricCell label="CTR" value={metric.ctr} trendUp={metric.trendUp} />
                  </div>

                  {/* Desktop metrics */}
                  <div className="hidden md:flex col-span-2 items-center justify-center">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-mono text-slate-300">
                        {metric.impressions}
                      </span>
                      {metric.trendUp && (
                        <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                      )}
                    </div>
                  </div>

                  <div className="hidden md:flex col-span-1 items-center justify-center">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-mono text-slate-300">
                        {metric.likes}
                      </span>
                      {metric.trendUp && (
                        <TrendingUp className="w-3 h-3 text-green-400" />
                      )}
                    </div>
                  </div>

                  <div className="hidden md:flex col-span-2 items-center justify-center">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-mono text-slate-300">
                        {metric.comments}
                      </span>
                      {metric.trendUp && (
                        <TrendingUp className="w-3 h-3 text-green-400" />
                      )}
                    </div>
                  </div>

                  <div className="hidden md:flex col-span-2 items-center justify-center">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`text-sm font-mono font-semibold ${
                          metric.ctr !== "—"
                            ? "text-emerald-400"
                            : "text-slate-600"
                        }`}
                      >
                        {metric.ctr}
                      </span>
                      {metric.trendUp && (
                        <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                      )}
                    </div>
                  </div>
                </motion.div>
                
                {/* Expanded Content View */}
                {isExpanded && metric.final_result && (
                  <motion.div 
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="px-6 py-5 bg-black/20 border-t border-white/5"
                  >
                    <div className="bg-slate-900/80 rounded-xl p-5 border border-white/10 max-h-96 overflow-y-auto custom-scrollbar">
                      <h4 className="text-xs font-bold uppercase tracking-widest text-blue-400 mb-4">Generated Content</h4>
                      <div className="text-sm text-slate-300 whitespace-pre-line font-sans leading-relaxed">
                        {metric.final_result}
                      </div>
                    </div>
                  </motion.div>
                )}
              </div>
            );
          })}

          {/* Table Footer */}
          <div className="flex items-center justify-between px-5 py-3 border-t border-white/5">
            <span className="text-[10px] text-slate-600 tracking-wider">
              Showing {metrics.length} historical records
            </span>
            <div className="flex items-center gap-1.5 text-[10px] text-blue-400/70 font-medium cursor-pointer hover:text-blue-400 transition-colors">
              <span className="tracking-wider uppercase">View All</span>
              <TrendingUp className="w-3 h-3" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCell({
  label,
  value,
  trendUp,
}: {
  label: string;
  value: string;
  trendUp: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 p-2 rounded-lg bg-white/[0.02]">
      <span className="text-[9px] text-slate-600 tracking-wider uppercase">
        {label}
      </span>
      <span className="text-xs font-mono text-slate-300">{value}</span>
      {trendUp && value !== "—" && (
        <TrendingUp className="w-2.5 h-2.5 text-green-400" />
      )}
    </div>
  );
}
