"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Users,
  Search,
  Filter,
  Mail,
  ExternalLink,
  Copy,
  Check,
  Award,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Briefcase,
  Target,
  Send,
  UserCheck,
} from "lucide-react";
import { LeadsFunnel, LinkedinLead, linkedinApi } from "@/lib/linkedinApi";

interface Props {
  leadsFunnel: LeadsFunnel;
}

export default function LinkedinLeadProspector({ leadsFunnel }: Props) {
  const [leads, setLeads] = useState<LinkedinLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalLeads, setTotalLeads] = useState(0);
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null);
  const [copiedPitch, setCopiedPitch] = useState<string | null>(null);

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    try {
      const res = await linkedinApi.getLeads({
        page,
        limit: 15,
        search: search.trim() || undefined,
        status: selectedStatus === "all" ? undefined : selectedStatus,
        category: selectedCategory === "all" ? undefined : selectedCategory,
      });
      setLeads(res.leads);
      setTotalPages(res.total_pages || 1);
      setTotalLeads(res.total || 0);
    } catch (err) {
      console.error("Failed to load leads:", err);
    } finally {
      setLoading(false);
    }
  }, [page, search, selectedStatus, selectedCategory]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchLeads();
    }, 250);
    return () => clearTimeout(timer);
  }, [fetchLeads]);

  const handleCopyEmail = (email: string) => {
    navigator.clipboard.writeText(email);
    setCopiedEmail(email);
    setTimeout(() => setCopiedEmail(null), 2000);
  };

  const handleCopyPitch = (pitch: string, id: string) => {
    navigator.clipboard.writeText(pitch);
    setCopiedPitch(id);
    setTimeout(() => setCopiedPitch(null), 2000);
  };

  const funnelSteps = [
    { label: "Scraped Leads", count: leadsFunnel.total_leads, color: "text-blue-400 border-blue-500/30 bg-blue-500/10" },
    { label: "Verified Emails", count: leadsFunnel.verified_emails, color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10" },
    { label: "High Fit (≥9.0)", count: leadsFunnel.high_fit_count, color: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10" },
    { label: "Outreach Ready", count: leadsFunnel.outreach_ready, color: "text-amber-400 border-amber-500/30 bg-amber-500/10" },
    { label: "Contacted", count: leadsFunnel.contacted, color: "text-purple-400 border-purple-500/30 bg-purple-500/10" },
    { label: "Converted", count: leadsFunnel.converted, color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* ── B2B Outreach Funnel Cards ── */}
      <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl">
        <div className="flex items-center justify-between border-b border-white/5 pb-4 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
              <Target className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                B2B Lead Prospector & Outreach Funnel
              </h3>
              <p className="text-[11px] text-slate-400">
                High-intent YouTube creators & tech founders discovered and scored via lead_finder.py
              </p>
            </div>
          </div>
          <span className="text-xs font-mono text-slate-400">
            Total Database: <strong className="text-white">{leadsFunnel.total_leads} Leads</strong>
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {funnelSteps.map((step, idx) => (
            <div
              key={step.label}
              className={`rounded-xl border p-3 flex flex-col justify-between transition-all hover:scale-[1.02] ${step.color}`}
            >
              <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80">
                {step.label}
              </span>
              <div className="text-xl font-bold font-mono mt-2">{step.count.toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Search & Filter Controls ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-900/60 p-4 backdrop-blur-xl">
        <div className="relative min-w-[240px] flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search leads by creator name, company, niche, country..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full rounded-xl border border-white/10 bg-slate-950/60 py-2 pl-9 pr-3 text-xs text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-slate-300 focus:border-blue-500 focus:outline-none"
          >
            <option value="all">All Outreach Statuses</option>
            <option value="ready">Ready for Outreach</option>
            <option value="contacted">Contacted</option>
            <option value="converted">Converted</option>
          </select>
        </div>
      </div>

      {/* ── Enriched Leads Table ── */}
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-900/60 backdrop-blur-xl shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="border-b border-white/10 bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="py-3.5 pl-5 pr-3 font-semibold">Creator & Channel</th>
                <th className="py-3.5 px-3 font-semibold">Audience / Niche</th>
                <th className="py-3.5 px-3 font-semibold">Product Fit</th>
                <th className="py-3.5 px-3 font-semibold">Personalized Hook</th>
                <th className="py-3.5 px-3 font-semibold">Status</th>
                <th className="py-3.5 pl-3 pr-5 text-right font-semibold">Outreach Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-xs text-slate-500 font-mono">
                    <div className="inline-flex items-center gap-2">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                      Loading enriched leads...
                    </div>
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-xs text-slate-500 font-mono">
                    No leads found matching your criteria.
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <tr key={lead.lead_id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-4 pl-5 pr-3">
                      <div className="font-semibold text-white flex items-center gap-1.5">
                        {lead.name}
                        {lead.url && (
                          <a
                            href={lead.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-500 hover:text-blue-400"
                            title="Open Channel / Profile"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-2 font-mono">
                        <span>{lead.company}</span>
                        {lead.country && (
                          <>
                            <span className="text-slate-600">•</span>
                            <span className="text-slate-500">{lead.country}</span>
                          </>
                        )}
                      </div>
                    </td>

                    <td className="py-4 px-3 max-w-[200px]">
                      <div className="text-xs text-slate-200 font-medium truncate">
                        {lead.audience_size || "—"}
                      </div>
                      <div className="text-[11px] text-slate-400 truncate" title={lead.niche}>
                        {lead.niche}
                      </div>
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-mono font-bold text-emerald-400">
                        <Award className="h-3 w-3" />
                        {lead.fit_score || "9.5/10"}
                      </span>
                    </td>

                    <td className="py-4 px-3 max-w-xs">
                      <p className="text-[11px] text-slate-300 line-clamp-2 italic font-mono">
                        "{lead.pitch_hook}"
                      </p>
                    </td>

                    <td className="py-4 px-3 whitespace-nowrap">
                      <span className="inline-flex items-center rounded-lg border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-medium text-slate-300">
                        {lead.status}
                      </span>
                    </td>

                    <td className="py-4 pl-3 pr-5 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        {lead.email && (
                          <button
                            onClick={() => handleCopyEmail(lead.email)}
                            className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-mono text-slate-300 hover:border-blue-500/40 hover:bg-blue-500/10 hover:text-blue-300 transition-all"
                            title={lead.email}
                          >
                            {copiedEmail === lead.email ? (
                              <Check className="h-3 w-3 text-emerald-400" />
                            ) : (
                              <Mail className="h-3 w-3" />
                            )}
                            {copiedEmail === lead.email ? "Copied" : "Email"}
                          </button>
                        )}
                        <button
                          onClick={() => handleCopyPitch(lead.pitch_hook, lead.lead_id)}
                          className="flex items-center gap-1 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-[10px] font-medium text-indigo-300 hover:bg-indigo-500/20 transition-all"
                          title="Copy personalized outreach hook"
                        >
                          {copiedPitch === lead.lead_id ? (
                            <Check className="h-3 w-3 text-emerald-400" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                          {copiedPitch === lead.lead_id ? "Copied Hook" : "Pitch Hook"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="flex items-center justify-between border-t border-white/5 px-5 py-3 text-xs text-slate-400">
          <div>
            Showing <strong className="text-white">{leads.length}</strong> of{" "}
            <strong className="text-white">{totalLeads}</strong> leads
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
              className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-300 hover:bg-white/10 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="font-mono text-xs text-slate-300">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || loading}
              className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-300 hover:bg-white/10 disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
