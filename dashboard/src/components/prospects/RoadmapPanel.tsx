"use client";

import React from "react";
import { CalendarDays, Map } from "lucide-react";
import { fmtDate, type ProspectChannel, type Roadmap } from "@/lib/youtubeProspectsApi";

/**
 * Screenshot target #2: the 30-day content roadmap.
 *
 * Dates come from the backend (`_assign_roadmap_dates`), never from the model —
 * the roadmap prompt explicitly forbids the model from emitting them.
 */

const FORMAT_TINTS: Record<string, string> = {
  tutorial: "bg-blue-500/10 text-blue-300 border-blue-500/20",
  shorts: "bg-pink-500/10 text-pink-300 border-pink-500/20",
  "deep-dive": "bg-purple-500/10 text-purple-300 border-purple-500/20",
  series: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  comparison: "bg-teal-500/10 text-teal-300 border-teal-500/20",
};

function FormatBadge({ format }: { format: string }) {
  if (!format) return null;
  const tint =
    FORMAT_TINTS[format.toLowerCase().trim()] ||
    "bg-slate-500/10 text-slate-300 border-slate-500/20";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${tint}`}
    >
      {format}
    </span>
  );
}

export default function RoadmapPanel({
  channel,
  roadmap,
}: {
  channel: ProspectChannel;
  roadmap: Roadmap;
}) {
  const weeks = roadmap.weeks || [];

  return (
    <section className="share-card rounded-2xl border border-white/10 bg-[#0b1120] overflow-hidden">
      <header className="p-6 border-b border-white/5">
        <p className="text-[11px] font-bold tracking-[0.25em] uppercase text-purple-400">
          30-Day Content Plan
        </p>
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Map size={18} className="text-purple-400" />
          {weeks.length}-week roadmap for {channel.title}
        </h2>
        {roadmap.cadence ? (
          <p className="text-xs text-slate-500 mt-1">
            Recommended cadence: <span className="text-slate-300">{roadmap.cadence}</span>
          </p>
        ) : null}
      </header>

      {weeks.length === 0 ? (
        <div className="p-6 text-sm text-slate-500 italic">No roadmap weeks were generated.</div>
      ) : (
        <div className="p-6 grid gap-4 md:grid-cols-2">
          {weeks.map((week) => (
            <div
              key={week.week_number}
              className="rounded-xl bg-[#0f172a] border border-white/10 p-4 flex flex-col"
            >
              <div className="flex items-baseline justify-between mb-1">
                <p className="text-xs font-bold uppercase tracking-wider text-purple-300">
                  Week {week.week_number}
                </p>
                <p className="text-[11px] text-slate-500 flex items-center gap-1">
                  <CalendarDays size={11} />
                  {fmtDate(week.start_date)}
                </p>
              </div>
              {week.focus ? (
                <p className="text-sm text-slate-300 font-medium mb-3">{week.focus}</p>
              ) : null}

              <ul className="space-y-3 flex-1">
                {(week.items || []).map((item, i) => (
                  <li key={i} className="border-l-2 border-purple-500/25 pl-3">
                    <p className="text-sm text-white font-medium leading-snug">{item.title}</p>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                      <FormatBadge format={item.format} />
                      {item.date ? (
                        <span className="text-[10px] text-slate-500 tabular-nums">
                          {fmtDate(item.date)}
                        </span>
                      ) : null}
                      {item.theme ? (
                        <span className="text-[10px] text-slate-600">· {item.theme}</span>
                      ) : null}
                    </div>
                    {item.rationale ? (
                      <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                        {item.rationale}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
