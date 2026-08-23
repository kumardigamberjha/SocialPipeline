"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  TrendingUp,
  CheckCircle2,
  Clock,
  Eye,
  ThumbsUp,
  MessageSquare,
  MousePointerClick,
  BarChart3,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { request } from "@/lib/apiClient";

const PAGE_SIZE = 20;

const PROSE_CLASS =
  "prose prose-invert prose-sm max-w-none prose-headings:text-slate-200 prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-slate-100 prose-code:text-cyan-300";

// Keys whose value should be surfaced as a section heading rather than a label.
const HEADING_KEYS = ["heading", "title", "name"];

function humanizeKey(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function Markdown({ children }: { children: string }) {
  return (
    <div className={PROSE_CLASS}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

// Renders arbitrary parsed JSON as readable, docs-like prose.
function JsonValue({ value }: { value: any }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500 italic">—</span>;
  }
  if (typeof value === "string") {
    return <Markdown>{value}</Markdown>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="text-slate-300">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-500 italic">None</span>;
    const allScalar = value.every((v) => v === null || typeof v !== "object");
    if (allScalar) {
      return (
        <ul className="list-disc pl-5 space-y-1 text-sm text-slate-300">
          {value.map((v, i) => (
            <li key={i}>{String(v)}</li>
          ))}
        </ul>
      );
    }
    return (
      <div className="space-y-4">
        {value.map((v, i) => (
          <div key={i} className="border-l-2 border-white/10 pl-4">
            <JsonValue value={v} />
          </div>
        ))}
      </div>
    );
  }
  // Plain object.
  const entries = Object.entries(value);
  const headingEntry = entries.find(
    ([k, v]) => HEADING_KEYS.includes(k.toLowerCase()) && typeof v === "string"
  );
  return (
    <div className="space-y-3">
      {headingEntry && (
        <h4 className="text-sm font-semibold text-white">{String(headingEntry[1])}</h4>
      )}
      {entries
        .filter(([k]) => !(headingEntry && k === headingEntry[0]))
        .map(([k, v]) => (
          <div key={k}>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
              {humanizeKey(k)}
            </p>
            <JsonValue value={v} />
          </div>
        ))}
    </div>
  );
}

// Step/final outputs may be stored as a JSON string or as plain markdown.
// Render JSON as structured prose, everything else as markdown.
function StepBody({ body }: { body: string }) {
  const trimmed = body.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed !== null && typeof parsed === "object") {
        return <JsonValue value={parsed} />;
      }
    } catch {
      // fall through to markdown
    }
  }
  return <Markdown>{body}</Markdown>;
}

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

interface TaskStep {
  id: number;
  agent_name: string;
  task_name: string;
  output: string;
  status: string;
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
  const [page, setPage] = useState(0);
  const [hasNext, setHasNext] = useState(false);

  // Detail (task_steps) cache keyed by run id, plus a per-id loading flag.
  const [stepsById, setStepsById] = useState<Record<string, TaskStep[]>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setExpandedId(null);
    request<any[]>(`/runs?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`)
      .then((data: any[]) => {
        const mapped = data.map((run) => ({
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
        setHasNext(data.length === PAGE_SIZE);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch runs", err);
        setLoading(false);
      });
  }, [page]);

  const toggleExpanded = useCallback((id: string) => {
    setExpandedId((current) => {
      const next = current === id ? null : id;
      // Fetch pipeline steps on first expand of this run.
      if (next === id && !stepsById[id]) {
        setDetailLoadingId(id);
        request<any>(`/runs/${id}`)
          .then((run: any) => {
            setStepsById((prev) => ({ ...prev, [id]: run.task_steps || [] }));
          })
          .catch((err) => {
            console.error("Failed to fetch run detail", err);
            setStepsById((prev) => ({ ...prev, [id]: [] }));
          })
          .finally(() => setDetailLoadingId((cur) => (cur === id ? null : cur)));
      }
      return next;
    });
  }, [stepsById]);

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
                  onClick={() => toggleExpanded(metric.id)}
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
                
                {/* Expanded Content View — per-stage accordions */}
                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="px-6 py-5 bg-black/20 border-t border-white/5"
                  >
                    <h4 className="text-xs font-bold uppercase tracking-widest text-blue-400 mb-4">
                      Pipeline Stages
                    </h4>

                    {detailLoadingId === metric.id && (
                      <div className="text-sm text-slate-500 animate-pulse py-4">
                        Loading pipeline steps…
                      </div>
                    )}

                    {detailLoadingId !== metric.id && (
                      <div className="space-y-2">
                        {metric.final_result && (
                          <AccordionItem
                            title="Final Result"
                            subtitle="Combined output"
                            body={metric.final_result}
                          />
                        )}

                        {(stepsById[metric.id] || []).map((step) => (
                          <AccordionItem
                            key={step.id}
                            title={step.agent_name}
                            subtitle={step.task_name}
                            body={step.output}
                          />
                        ))}

                        {stepsById[metric.id] &&
                          stepsById[metric.id].length === 0 &&
                          !metric.final_result && (
                            <div className="text-sm text-slate-500 py-4">
                              No pipeline steps recorded for this run.
                            </div>
                          )}
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            );
          })}

          {/* Table Footer */}
          <div className="flex items-center justify-between px-5 py-3 border-t border-white/5">
            <span className="text-[10px] text-slate-600 tracking-wider">
              {metrics.length > 0
                ? `Showing records ${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + metrics.length}`
                : "No records"}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || loading}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-white/10 text-[10px] font-medium tracking-wider uppercase text-blue-400/70 hover:text-blue-400 hover:bg-white/[0.05] transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft className="w-3 h-3" />
                <span>Prev</span>
              </button>
              <span className="text-[10px] text-slate-600 tracking-wider tabular-nums">
                Page {page + 1}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasNext || loading}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-white/10 text-[10px] font-medium tracking-wider uppercase text-blue-400/70 hover:text-blue-400 hover:bg-white/[0.05] transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                <span>Next</span>
                <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AccordionItem({
  title,
  subtitle,
  body,
}: {
  title: string;
  subtitle?: string;
  body: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.04] transition-colors cursor-pointer"
      >
        <div className="min-w-0">
          <p className="text-sm font-medium text-white truncate">{title}</p>
          {subtitle && (
            <p className="text-[11px] text-slate-500 truncate mt-0.5">{subtitle}</p>
          )}
        </div>
        <ChevronDown
          className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-white/5"
          >
            <div className="px-4 py-3 max-h-96 overflow-y-auto custom-scrollbar">
              <StepBody body={body} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
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
