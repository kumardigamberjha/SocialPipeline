"use client";

import React from "react";

/**
 * The bulleted/numbered list block used by every AI report panel.
 *
 * Extracted from YoutubeStrategyRoadmap so the owner-channel strategy brief and
 * the prospect audit render identically — the two read the same `Strategy`
 * payload, and a divergence between them would show up as the same report
 * looking different depending on whose channel it describes.
 *
 * `solid` swaps the translucent surface for an opaque one. Panels destined for
 * a screenshot or a PDF must set it: the ambient `.glass-card` styling relies
 * on `backdrop-filter`, which prints as a transparent box.
 */
export function Section({
  icon: Icon,
  title,
  tint,
  items,
  ordered = false,
  solid = false,
}: {
  icon: React.ElementType;
  title: string;
  tint: string;
  items: string[];
  ordered?: boolean;
  solid?: boolean;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div
      className={`rounded-xl border p-4 ${
        solid ? "bg-[#0f172a] border-white/10" : "bg-white/[0.02] border-white/5"
      }`}
    >
      <p className={`flex items-center gap-2 text-xs font-bold uppercase tracking-wider mb-3 ${tint}`}>
        <Icon size={14} /> {title}
      </p>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-300 leading-relaxed">
            {ordered ? (
              <span className={`text-xs font-bold tabular-nums ${tint} flex-shrink-0 w-4`}>{i + 1}</span>
            ) : (
              <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${tint.replace("text-", "bg-")}`} />
            )}
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default Section;
