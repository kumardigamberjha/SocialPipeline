"use client";

import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import {
  AngleDistributionItem,
  OfficialStats,
  LinkedinPostItem,
} from "@/lib/linkedinApi";
import { Lock, Radio, AlertCircle } from "lucide-react";

const AXIS_COLOR = "#94a3b8";
const GRID_COLOR = "rgba(255, 255, 255, 0.06)";

const TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: "#090d16",
  border: "1px solid rgba(255, 255, 255, 0.12)",
  borderRadius: "12px",
  padding: "10px 14px",
  fontSize: "12px",
  color: "#f1f5f9",
  boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
};

interface AnglePerformanceChartProps {
  data: AngleDistributionItem[];
}

export function AnglePerformanceChart({ data }: AnglePerformanceChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-xs text-slate-500 font-mono">
        No post angles recorded in database yet.
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 10, right: 20, left: 40, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} horizontal={false} />
          <XAxis type="number" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
          <YAxis
            type="category"
            dataKey="angle"
            stroke={AXIS_COLOR}
            fontSize={11}
            tickLine={false}
            width={130}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(val: any, name: any) => [
              val,
              name === "count" ? "Total Generated" : "Approved",
            ]}
          />
          <Bar dataKey="count" name="Generated" fill="#0284c7" radius={[0, 4, 4, 0]} barSize={14} />
          <Bar dataKey="approved" name="Approved" fill="#10b981" radius={[0, 4, 4, 0]} barSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface WordCountBreakdownChartProps {
  posts: LinkedinPostItem[];
}

export function WordCountBreakdownChart({ posts }: WordCountBreakdownChartProps) {
  const brackets = [
    { bracket: "< 150 words", count: 0, approved: 0 },
    { bracket: "150 - 220 words", count: 0, approved: 0 },
    { bracket: "220 - 300 words", count: 0, approved: 0 },
    { bracket: "300 - 380 words", count: 0, approved: 0 },
    { bracket: "> 380 words", count: 0, approved: 0 },
  ];

  posts.forEach((p) => {
    const wc = p.word_count || 0;
    let idx = 0;
    if (wc < 150) idx = 0;
    else if (wc < 220) idx = 1;
    else if (wc < 300) idx = 2;
    else if (wc < 380) idx = 3;
    else idx = 4;

    brackets[idx].count += 1;
    if (p.approved) brackets[idx].approved += 1;
  });

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={brackets} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey="bracket" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
          <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} allowDecimals={false} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(val: any, name: any) => [
              val,
              name === "count" ? "Generated Posts" : "Approved Posts",
            ]}
          />
          <Bar dataKey="count" name="Generated" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={28} />
          <Bar dataKey="approved" name="Approved" fill="#10b981" radius={[4, 4, 0, 0]} barSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface OfficialEngagementChartProps {
  stats: OfficialStats;
  apiConnected: boolean;
}

export function OfficialEngagementChart({ stats, apiConnected }: OfficialEngagementChartProps) {
  if (!apiConnected) {
    return (
      <div className="flex h-72 w-full flex-col items-center justify-center p-6 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 border border-white/10 text-slate-400 mb-3">
          <Lock className="h-5 w-5" />
        </div>
        <h4 className="text-xs font-semibold text-white mb-1">
          LinkedIn API Not Connected
        </h4>
        <p className="text-[11px] text-slate-400 max-w-xs leading-relaxed">
          Authenticate your LinkedIn account to stream official engagement statistics directly from LinkedIn.
        </p>
      </div>
    );
  }

  const reactions = stats.reactions || 0;
  const comments = stats.comments || 0;
  const reposts = stats.reposts || 0;
  const clicks = stats.clicks || 0;
  const total = reactions + comments + reposts + clicks;

  if (total === 0) {
    return (
      <div className="flex h-72 w-full flex-col items-center justify-center p-6 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-400 mb-3">
          <Radio className="h-5 w-5" />
        </div>
        <h4 className="text-xs font-semibold text-white mb-1">
          Awaiting Official API Engagements
        </h4>
        <p className="text-[11px] text-slate-400 max-w-xs leading-relaxed">
          LinkedIn API is connected. Official reactions, comments, and reshares will reflect here as they are published.
        </p>
      </div>
    );
  }

  const data = [
    { name: "Reactions", value: reactions, color: "#0284c7" },
    { name: "Comments", value: comments, color: "#10b981" },
    { name: "Reposts", value: reposts, color: "#8b5cf6" },
    { name: "Clicks", value: clicks, color: "#f59e0b" },
  ].filter((d) => d.value > 0);

  return (
    <div className="flex h-72 w-full flex-col items-center justify-center">
      <ResponsiveContainer width="100%" height={210}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} stroke="rgba(0,0,0,0.5)" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(val: any) => [val, "Official Count"]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-400">
        {data.map((item) => (
          <div key={item.name} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
            <span>{item.name}:</span>
            <span className="font-mono text-white font-semibold">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
