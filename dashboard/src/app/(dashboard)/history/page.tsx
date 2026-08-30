"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowUpDown,
  BarChart3,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Cpu,
  Filter,
  Layers,
  ListFilter,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Terminal,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { request } from "@/lib/apiClient";

const PROSE_CLASS =
  "prose prose-invert prose-sm max-w-none prose-headings:text-slate-200 prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-slate-100 prose-code:text-cyan-300";

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

function JsonValue({ value }: { value: any }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500 italic">—</span>;
  }
  if (typeof value === "string") {
    return <Markdown>{value}</Markdown>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="text-slate-300 font-mono">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-500 italic">Empty list</span>;
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
      <div className="space-y-3">
        {value.map((v, i) => (
          <div key={i} className="border-l-2 border-white/10 pl-3.5">
            <JsonValue value={v} />
          </div>
        ))}
      </div>
    );
  }
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

function StepBody({ body }: { body: string }) {
  const trimmed = body?.trim() || "";
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed !== null && typeof parsed === "object") {
        return <JsonValue value={parsed} />;
      }
    } catch {
      // Fall through to markdown
    }
  }
  return <Markdown>{trimmed || "No output recorded."}</Markdown>;
}

interface RunItem {
  id: string;
  topic: string;
  provider_used: string;
  status: "pending" | "running" | "completed" | "failed" | "published";
  final_result: string | null;
  duration_seconds: number | null;
  image_url: string | null;
  created_at: string;
  completed_at: string | null;
}

interface TaskStep {
  id: number;
  run_id: string;
  agent_name: string;
  task_name: string;
  output: string;
  status: string;
  created_at?: string;
}

interface RunStats {
  total: number;
  completed: number;
  failed: number;
  running: number;
  pending: number;
  avg_duration: number;
  success_rate: number;
  providers: string[];
}

const statusConfig: Record<string, { label: string; icon: any; color: string; bg: string; border: string }> = {
  completed: {
    label: "Succeeded",
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/25",
  },
  published: {
    label: "Published",
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/25",
  },
  running: {
    label: "Running",
    icon: Clock,
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/25",
  },
  pending: {
    label: "Pending",
    icon: Loader2,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/25",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    color: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/25",
  },
};

function formatDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || isNaN(sec)) return "—";
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export default function HistoryPage() {
  // Data state
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);

  // Filter state
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [timeRangeFilter, setTimeRangeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("created_at_desc");

  // Pagination state
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);

  // Expanded runs cache & steps
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [stepsById, setStepsById] = useState<Record<string, TaskStep[]>>({});
  const [stepsLoadingId, setStepsLoadingId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Auto-refresh timer
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(0); // 0 = off

  // Search debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Load stats
  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await request<RunStats>("/runs/stats");
      setStats(data);
    } catch (err) {
      console.error("Failed to load run stats", err);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Load runs
  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(pageSize));
      params.set("offset", String(page * pageSize));

      if (statusFilter !== "all") params.set("status", statusFilter);
      if (providerFilter !== "all") params.set("provider", providerFilter);
      if (timeRangeFilter !== "all") params.set("time_range", timeRangeFilter);
      if (sortBy) params.set("sort_by", sortBy);
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());

      const res: any = await request(`/runs?${params.toString()}`);
      const items: RunItem[] = Array.isArray(res) ? res : res?.items || [];
      const total = typeof res?.total === "number" ? res.total : items.length;

      setRuns(items);
      setTotalCount(total);
    } catch (err) {
      console.error("Failed to load runs", err);
      setRuns([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, statusFilter, providerFilter, timeRangeFilter, sortBy, debouncedSearch]);

  // Initial load
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Auto refresh
  useEffect(() => {
    if (autoRefreshInterval <= 0) return;
    const interval = setInterval(() => {
      loadRuns();
      loadStats();
    }, autoRefreshInterval * 1000);
    return () => clearInterval(interval);
  }, [autoRefreshInterval, loadRuns, loadStats]);

  // Toggle run row expansion and load steps
  const toggleExpand = useCallback(
    (id: string) => {
      setExpandedId((curr) => {
        const next = curr === id ? null : id;
        if (next === id && !stepsById[id]) {
          setStepsLoadingId(id);
          request<any>(`/runs/${id}`)
            .then((res: any) => {
              setStepsById((prev) => ({ ...prev, [id]: res?.task_steps || [] }));
            })
            .catch((err) => {
              console.error("Failed to load task steps for run", id, err);
              setStepsById((prev) => ({ ...prev, [id]: [] }));
            })
            .finally(() => {
              setStepsLoadingId((current) => (current === id ? null : current));
            });
        }
        return next;
      });
    },
    [stepsById]
  );

  const handleCopyId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleCopyText = (text: string, id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const resetAllFilters = () => {
    setSearch("");
    setDebouncedSearch("");
    setStatusFilter("all");
    setProviderFilter("all");
    setTimeRangeFilter("all");
    setSortBy("created_at_desc");
    setPage(0);
  };

  const isFiltered =
    debouncedSearch.trim() !== "" ||
    statusFilter !== "all" ||
    providerFilter !== "all" ||
    timeRangeFilter !== "all" ||
    sortBy !== "created_at_desc";

  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  // Generate pagination page numbers
  const pageNumbers = useMemo(() => {
    const pages: (number | string)[] = [];
    const maxVisible = 5;
    if (totalPages <= maxVisible + 2) {
      for (let i = 0; i < totalPages; i++) pages.push(i);
    } else {
      pages.push(0);
      if (page > 2) pages.push("...");

      const start = Math.max(1, page - 1);
      const end = Math.min(totalPages - 2, page + 1);

      for (let i = start; i <= end; i++) {
        if (!pages.includes(i)) pages.push(i);
      }

      if (page < totalPages - 3) pages.push("...");
      if (!pages.includes(totalPages - 1)) pages.push(totalPages - 1);
    }
    return pages;
  }, [page, totalPages]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full space-y-6">
      {/* ── Page Header ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-5 bg-gradient-to-b from-blue-500 via-indigo-500 to-purple-500 rounded-full" />
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2.5">
              Pipeline Execution History
              <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400">
                AUDIT & TELEMETRY
              </span>
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1 pl-3.5">
            Full historical ledger of autonomous pipeline runs, task agent steps, and generated deliverables.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          {/* Auto Refresh Dropdown */}
          <div className="flex items-center gap-1.5 bg-slate-900/80 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-300">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[11px] text-slate-400">Auto:</span>
            <select
              value={autoRefreshInterval}
              onChange={(e) => setAutoRefreshInterval(Number(e.target.value))}
              className="bg-transparent text-xs text-blue-400 font-medium focus:outline-hidden cursor-pointer"
            >
              <option value={0} className="bg-slate-900 text-slate-300">Off</option>
              <option value={15} className="bg-slate-900 text-slate-300">15s</option>
              <option value={30} className="bg-slate-900 text-slate-300">30s</option>
              <option value={60} className="bg-slate-900 text-slate-300">60s</option>
            </select>
          </div>

          {/* Manual Refresh */}
          <button
            type="button"
            onClick={() => {
              loadRuns();
              loadStats();
            }}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-medium text-slate-200 transition-colors cursor-pointer disabled:opacity-50"
            title="Refresh runs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-blue-400" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* ── KPI Stat Cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        {/* Total Runs */}
        <div className="glass-card rounded-xl p-4 border border-white/5 bg-slate-900/40 relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider">Total Runs</span>
            <Layers className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-xl sm:text-2xl font-bold font-mono text-white">
            {statsLoading ? "—" : stats?.total ?? 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">All agent executions</div>
        </div>

        {/* Succeeded */}
        <div className="glass-card rounded-xl p-4 border border-emerald-500/15 bg-emerald-950/10 relative overflow-hidden">
          <div className="flex items-center justify-between text-emerald-400 mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider">Succeeded</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl sm:text-2xl font-bold font-mono text-emerald-300">
              {statsLoading ? "—" : stats?.completed ?? 0}
            </span>
            {stats && (
              <span className="text-[11px] font-mono text-emerald-400/80">
                ({stats.success_rate}%)
              </span>
            )}
          </div>
          <div className="text-[10px] text-emerald-500/80 mt-1">Completed deliverables</div>
        </div>

        {/* Failed */}
        <div className="glass-card rounded-xl p-4 border border-rose-500/15 bg-rose-950/10 relative overflow-hidden">
          <div className="flex items-center justify-between text-rose-400 mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider">Failed</span>
            <XCircle className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-xl sm:text-2xl font-bold font-mono text-rose-300">
            {statsLoading ? "—" : stats?.failed ?? 0}
          </div>
          <div className="text-[10px] text-rose-500/80 mt-1">Halted / error state</div>
        </div>

        {/* In Progress / Active */}
        <div className="glass-card rounded-xl p-4 border border-amber-500/15 bg-amber-950/10 relative overflow-hidden">
          <div className="flex items-center justify-between text-amber-400 mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider">In Flight</span>
            <Activity className="w-4 h-4 text-amber-400 animate-pulse" />
          </div>
          <div className="text-xl sm:text-2xl font-bold font-mono text-amber-300">
            {statsLoading ? "—" : (stats?.running || 0) + (stats?.pending || 0)}
          </div>
          <div className="text-[10px] text-amber-500/80 mt-1">
            {stats?.running || 0} active, {stats?.pending || 0} queued
          </div>
        </div>

        {/* Avg Duration */}
        <div className="glass-card rounded-xl p-4 border border-white/5 bg-slate-900/40 col-span-2 sm:col-span-1 relative overflow-hidden">
          <div className="flex items-center justify-between text-slate-400 mb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider">Avg Runtime</span>
            <Clock className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-xl sm:text-2xl font-bold font-mono text-purple-300">
            {statsLoading ? "—" : formatDuration(stats?.avg_duration)}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Per successful execution</div>
        </div>
      </div>

      {/* ── Filter Bar ── */}
      <div className="glass-card rounded-xl p-4 border border-white/5 bg-slate-900/50 space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by topic, ID, or keywords…"
              className="w-full pl-9 pr-8 py-2 rounded-lg bg-white/[0.04] border border-white/10 text-xs text-white placeholder:text-slate-500 focus:outline-hidden focus:border-blue-500/50 focus:bg-white/[0.07] transition-all"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Filter Dropdowns Grid */}
          <div className="flex flex-wrap items-center gap-2 sm:gap-2.5">
            {/* Status Filter */}
            <div className="flex items-center gap-1.5 bg-white/[0.03] border border-white/10 rounded-lg px-2.5 py-1.5">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(0);
                }}
                className="bg-transparent text-xs text-slate-200 font-medium focus:outline-hidden cursor-pointer"
              >
                <option value="all" className="bg-slate-900 text-slate-200">All Statuses</option>
                <option value="completed" className="bg-slate-900 text-emerald-400">Succeeded / Done</option>
                <option value="failed" className="bg-slate-900 text-rose-400">Failed</option>
                <option value="running" className="bg-slate-900 text-amber-400">Running</option>
                <option value="pending" className="bg-slate-900 text-blue-400">Pending</option>
              </select>
            </div>

            {/* Provider Filter */}
            <div className="flex items-center gap-1.5 bg-white/[0.03] border border-white/10 rounded-lg px-2.5 py-1.5">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Provider:</span>
              <select
                value={providerFilter}
                onChange={(e) => {
                  setProviderFilter(e.target.value);
                  setPage(0);
                }}
                className="bg-transparent text-xs text-slate-200 font-medium focus:outline-hidden cursor-pointer"
              >
                <option value="all" className="bg-slate-900 text-slate-200">All Providers</option>
                <option value="gemini" className="bg-slate-900 text-slate-200">Gemini</option>
                <option value="openai" className="bg-slate-900 text-slate-200">OpenAI</option>
                <option value="groq" className="bg-slate-900 text-slate-200">Groq</option>
                <option value="ollama" className="bg-slate-900 text-slate-200">Ollama</option>
                {stats?.providers
                  ?.filter((p) => !["gemini", "openai", "groq", "ollama"].includes(p.toLowerCase()))
                  .map((p) => (
                    <option key={p} value={p} className="bg-slate-900 text-slate-200">
                      {p}
                    </option>
                  ))}
              </select>
            </div>

            {/* Time Range Filter */}
            <div className="flex items-center gap-1.5 bg-white/[0.03] border border-white/10 rounded-lg px-2.5 py-1.5">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Time:</span>
              <select
                value={timeRangeFilter}
                onChange={(e) => {
                  setTimeRangeFilter(e.target.value);
                  setPage(0);
                }}
                className="bg-transparent text-xs text-slate-200 font-medium focus:outline-hidden cursor-pointer"
              >
                <option value="all" className="bg-slate-900 text-slate-200">All Time</option>
                <option value="today" className="bg-slate-900 text-slate-200">Today</option>
                <option value="24h" className="bg-slate-900 text-slate-200">Past 24 Hours</option>
                <option value="7d" className="bg-slate-900 text-slate-200">Past 7 Days</option>
                <option value="30d" className="bg-slate-900 text-slate-200">Past 30 Days</option>
              </select>
            </div>

            {/* Sort Order */}
            <div className="flex items-center gap-1.5 bg-white/[0.03] border border-white/10 rounded-lg px-2.5 py-1.5">
              <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value);
                  setPage(0);
                }}
                className="bg-transparent text-xs text-slate-200 font-medium focus:outline-hidden cursor-pointer"
              >
                <option value="created_at_desc" className="bg-slate-900 text-slate-200">Newest First</option>
                <option value="created_at_asc" className="bg-slate-900 text-slate-200">Oldest First</option>
                <option value="duration_desc" className="bg-slate-900 text-slate-200">Duration (Longest)</option>
                <option value="duration_asc" className="bg-slate-900 text-slate-200">Duration (Shortest)</option>
              </select>
            </div>

            {/* Reset Filters */}
            {isFiltered && (
              <button
                type="button"
                onClick={resetAllFilters}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 text-xs font-medium transition-colors cursor-pointer"
                title="Reset all filters"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Run Records Table ── */}
      <div className="glass-card rounded-xl overflow-hidden border border-white/5 bg-slate-900/60 shadow-xl">
        {/* Table Header (Desktop) */}
        <div className="hidden md:grid grid-cols-12 gap-4 px-6 py-3.5 border-b border-white/5 text-[10px] font-bold tracking-[0.2em] uppercase text-slate-500 bg-white/[0.01]">
          <div className="col-span-5 flex items-center gap-1.5">
            <BarChart3 className="w-3 h-3" />
            <span>Topic / Execution ID</span>
          </div>
          <div className="col-span-2 text-center">Status</div>
          <div className="col-span-2 text-center flex items-center justify-center gap-1">
            <Cpu className="w-3 h-3" />
            <span>Provider</span>
          </div>
          <div className="col-span-1 text-center flex items-center justify-center gap-1">
            <Clock className="w-3 h-3" />
            <span>Duration</span>
          </div>
          <div className="col-span-2 text-right">Created At</div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="py-16 text-center space-y-3">
            <div className="inline-block h-7 w-7 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <p className="text-xs font-mono text-slate-500">Querying telemetry ledger from database...</p>
          </div>
        )}

        {/* Empty State */}
        {!loading && runs.length === 0 && (
          <div className="py-16 px-4 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-white/[0.03] border border-white/10 flex items-center justify-center mx-auto text-slate-500">
              <ListFilter className="w-6 h-6" />
            </div>
            <div className="text-sm font-medium text-slate-300">No matching pipeline runs found</div>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              {isFiltered
                ? "Try relaxing your search terms or clearing the selected filters to view other records."
                : "No pipeline runs have been executed yet. Generate content to see telemetry logs."}
            </p>
            {isFiltered && (
              <button
                type="button"
                onClick={resetAllFilters}
                className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 text-xs font-medium transition-colors cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset All Filters</span>
              </button>
            )}
          </div>
        )}

        {/* Run Rows */}
        {!loading &&
          runs.map((run, index) => {
            const badge = statusConfig[run.status] || statusConfig.running;
            const BadgeIcon = badge.icon;
            const isExpanded = expandedId === run.id;

            return (
              <div key={run.id} className="border-b border-white/5 last:border-b-0">
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.02, duration: 0.2 }}
                  onClick={() => toggleExpand(run.id)}
                  className={`
                    grid grid-cols-1 md:grid-cols-12 gap-3 md:gap-4
                    px-5 sm:px-6 py-4 cursor-pointer
                    hover:bg-white/[0.04] transition-colors duration-200
                    items-center group
                    ${isExpanded ? "bg-white/[0.03]" : ""}
                  `}
                >
                  {/* Topic & ID */}
                  <div className="col-span-1 md:col-span-5 flex items-start gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0 mt-0.5 border border-white/5 group-hover:border-blue-500/30 transition-colors">
                      <span className="text-xs font-mono text-slate-400">
                        {String(page * pageSize + index + 1).padStart(2, "0")}
                      </span>
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-white group-hover:text-blue-300 transition-colors truncate">
                          {run.topic}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 mt-1">
                        <button
                          type="button"
                          onClick={(e) => handleCopyId(run.id, e)}
                          className="inline-flex items-center gap-1 font-mono text-[10px] text-slate-500 hover:text-slate-300 bg-white/[0.02] hover:bg-white/[0.06] px-1.5 py-0.5 rounded border border-white/5 transition-colors cursor-pointer"
                          title="Click to copy Run ID"
                        >
                          <span>{run.id.slice(0, 8)}…</span>
                          {copiedId === run.id ? (
                            <Check className="w-2.5 h-2.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-2.5 h-2.5 opacity-60" />
                          )}
                        </button>

                        {/* Mobile Status */}
                        <div className="flex md:hidden items-center gap-1">
                          <span
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${badge.bg} ${badge.border} ${badge.color}`}
                          >
                            <BadgeIcon className="w-2.5 h-2.5" />
                            {badge.label}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Status (Desktop) */}
                  <div className="hidden md:flex col-span-2 items-center justify-center">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[10px] font-bold tracking-wider uppercase ${badge.bg} ${badge.border} ${badge.color}`}
                    >
                      <BadgeIcon className="w-3 h-3" />
                      {badge.label}
                    </span>
                  </div>

                  {/* Provider (Desktop) */}
                  <div className="hidden md:flex col-span-2 items-center justify-center">
                    <span className="text-xs font-mono text-slate-300 px-2 py-0.5 rounded bg-white/[0.03] border border-white/5 uppercase tracking-wide">
                      {run.provider_used || "default"}
                    </span>
                  </div>

                  {/* Duration (Desktop) */}
                  <div className="hidden md:flex col-span-1 items-center justify-center">
                    <span className="text-xs font-mono text-slate-300">
                      {formatDuration(run.duration_seconds)}
                    </span>
                  </div>

                  {/* Timestamp & Expand (Desktop) */}
                  <div className="hidden md:flex col-span-2 items-center justify-end gap-2 text-right">
                    <span className="text-xs text-slate-400 font-mono">
                      {formatDate(run.created_at)}
                    </span>
                    <ChevronDown
                      className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${
                        isExpanded ? "rotate-180 text-blue-400" : ""
                      }`}
                    />
                  </div>

                  {/* Mobile details row */}
                  <div className="flex md:hidden items-center justify-between text-xs text-slate-400 pt-1 border-t border-white/5">
                    <span className="font-mono text-[11px]">{run.provider_used}</span>
                    <span className="font-mono text-[11px]">{formatDuration(run.duration_seconds)}</span>
                    <span className="text-[10px] font-mono">{formatDate(run.created_at)}</span>
                  </div>
                </motion.div>

                {/* ── Expanded View: Final Output & Step Telemetry ── */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25 }}
                      className="px-6 py-5 bg-black/40 border-t border-white/5 space-y-6"
                    >
                      {/* Top Bar: Summary details */}
                      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/5 text-xs">
                        <div className="flex items-center gap-4 flex-wrap">
                          <div>
                            <span className="text-slate-500 text-[10px] uppercase block font-semibold">Run ID</span>
                            <span className="font-mono text-slate-300 select-all">{run.id}</span>
                          </div>
                          <div>
                            <span className="text-slate-500 text-[10px] uppercase block font-semibold">Started</span>
                            <span className="font-mono text-slate-300">{formatDate(run.created_at)}</span>
                          </div>
                          {run.completed_at && (
                            <div>
                              <span className="text-slate-500 text-[10px] uppercase block font-semibold">Completed</span>
                              <span className="font-mono text-slate-300">{formatDate(run.completed_at)}</span>
                            </div>
                          )}
                          <div>
                            <span className="text-slate-500 text-[10px] uppercase block font-semibold">Duration</span>
                            <span className="font-mono text-slate-300">{formatDuration(run.duration_seconds)}</span>
                          </div>
                        </div>

                        {run.final_result && (
                          <button
                            type="button"
                            onClick={(e) => handleCopyText(run.final_result!, `res-${run.id}`, e)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 border border-blue-500/20 text-[11px] font-medium transition-colors cursor-pointer"
                          >
                            {copiedId === `res-${run.id}` ? (
                              <>
                                <Check className="w-3 h-3 text-emerald-400" />
                                <span>Copied Output</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>Copy Final Output</span>
                              </>
                            )}
                          </button>
                        )}
                      </div>

                      {/* Final Deliverable Result */}
                      {run.final_result && (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-400">
                            <Sparkles className="w-3.5 h-3.5" />
                            <span>Generated Deliverable (Final Output)</span>
                          </div>
                          <div className="p-4 rounded-xl border border-white/10 bg-slate-900/80 max-h-96 overflow-y-auto custom-scrollbar">
                            <StepBody body={run.final_result} />
                          </div>
                        </div>
                      )}

                      {/* Pipeline Task Steps Telemetry */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-purple-400">
                            <Terminal className="w-3.5 h-3.5" />
                            <span>Agent Pipeline Execution Stages</span>
                          </div>
                          <span className="text-[10px] font-mono text-slate-500">
                            {(stepsById[run.id] || []).length} stage(s) recorded
                          </span>
                        </div>

                        {stepsLoadingId === run.id && (
                          <div className="p-6 text-center text-xs text-slate-500 animate-pulse font-mono">
                            Loading pipeline step logs…
                          </div>
                        )}

                        {stepsLoadingId !== run.id && (stepsById[run.id] || []).length === 0 && (
                          <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-slate-500 text-center">
                            No granular pipeline task steps recorded for this run.
                          </div>
                        )}

                        {stepsLoadingId !== run.id &&
                          (stepsById[run.id] || []).map((step, sIdx) => (
                            <StepAccordionItem
                              key={step.id || sIdx}
                              index={sIdx + 1}
                              step={step}
                              copiedId={copiedId}
                              onCopy={(text, id, e) => handleCopyText(text, id, e)}
                            />
                          ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}

        {/* ── Table Footer & Pagination ── */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-6 py-4 border-t border-white/5 bg-slate-950/40">
          {/* Record Count & Page Size Selector */}
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="tracking-wide">
              {totalCount > 0
                ? `Showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, totalCount)} of ${totalCount} runs`
                : "No records found"}
            </span>

            <div className="flex items-center gap-1.5 border-l border-white/10 pl-4">
              <span className="text-[11px] text-slate-500">Per page:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(0);
                }}
                className="bg-slate-900 border border-white/10 rounded px-2 py-1 text-xs text-slate-300 font-mono focus:outline-hidden cursor-pointer"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          {/* Page Buttons */}
          <div className="flex items-center gap-1.5">
            {/* Prev Button */}
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-white/10 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Prev</span>
            </button>

            {/* Numbered Page Buttons */}
            <div className="hidden sm:flex items-center gap-1">
              {pageNumbers.map((p, pIdx) => {
                if (typeof p === "string") {
                  return (
                    <span key={`dots-${pIdx}`} className="px-2 text-xs text-slate-600 font-mono">
                      …
                    </span>
                  );
                }
                const isActive = p === page;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPage(p)}
                    disabled={loading}
                    className={`min-w-8 h-8 px-2 rounded-lg text-xs font-mono font-medium transition-colors cursor-pointer ${
                      isActive
                        ? "bg-blue-600 text-white shadow-lg shadow-blue-500/20"
                        : "text-slate-400 hover:text-white hover:bg-white/5 border border-transparent hover:border-white/10"
                    }`}
                  >
                    {p + 1}
                  </button>
                );
              })}
            </div>

            {/* Mobile Page indicator */}
            <span className="sm:hidden text-xs font-mono text-slate-500 px-2">
              {page + 1} / {totalPages}
            </span>

            {/* Next Button */}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1 || loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-white/10 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StepAccordionItem({
  index,
  step,
  copiedId,
  onCopy,
}: {
  index: number;
  step: TaskStep;
  copiedId: string | null;
  onCopy: (text: string, id: string, e: React.MouseEvent) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/70 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.03] transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-5 h-5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center text-[10px] font-mono font-bold flex-shrink-0">
            {index}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-white truncate">{step.agent_name || "Agent"}</p>
              <span className="text-[10px] text-slate-600">//</span>
              <span className="text-xs text-slate-400 truncate">{step.task_name || "Task"}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[9px] font-mono uppercase tracking-wider text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
            {step.status || "done"}
          </span>
          <ChevronDown
            className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${
              open ? "rotate-180 text-purple-400" : ""
            }`}
          />
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-white/5 bg-slate-950/60"
          >
            <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-500 uppercase">Agent Step Output</span>
              {step.output && (
                <button
                  type="button"
                  onClick={(e) => onCopy(step.output, `step-${step.id || index}`, e)}
                  className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-white transition-colors cursor-pointer"
                >
                  {copiedId === `step-${step.id || index}` ? (
                    <>
                      <Check className="w-2.5 h-2.5 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-2.5 h-2.5" />
                      <span>Copy Step Output</span>
                    </>
                  )}
                </button>
              )}
            </div>
            <div className="px-4 py-3 max-h-80 overflow-y-auto custom-scrollbar">
              <StepBody body={step.output} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
