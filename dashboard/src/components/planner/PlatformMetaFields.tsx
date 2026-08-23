"use client";

import { Image as ImageIcon, Layers, MessageSquare } from "lucide-react";
import {
  INSTAGRAM_POST_TYPES,
  instagramMeta,
  InstagramMeta,
  Platform,
} from "@/lib/plannerApi";

interface Props {
  platform: Platform;
  meta: Record<string, unknown>;
  /** Called with only the keys that changed — the server shallow-merges them. */
  onChange: (patch: Record<string, unknown>) => void;
}

const INPUT =
  "mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50";
const LABEL =
  "block text-[10px] uppercase tracking-wider text-slate-500";

/**
 * The platform-specific half of a plan item, edited in place.
 *
 * These fields live in `plan_items.meta` (JSONB) rather than as columns,
 * because only one platform each cares about them. Instagram's set is what the
 * retired Instagram board's edit modal used to offer, so nothing was lost when
 * that board was removed in favour of this planner.
 *
 * Renders nothing for platforms with no extra fields — YouTube's format and
 * dates are real columns and are edited by the row itself.
 */
export default function PlatformMetaFields({ platform, meta, onChange }: Props) {
  if (platform !== "instagram") return null;

  const ig = instagramMeta(meta);
  const set = <K extends keyof InstagramMeta>(key: K, value: InstagramMeta[K]) =>
    onChange({ [key]: value });

  return (
    <div className="space-y-2 rounded-lg border border-pink-500/15 bg-pink-500/[0.03] p-2.5">
      <p className="text-[10px] uppercase tracking-wider text-pink-400/70 font-semibold">
        Instagram
      </p>

      <div className="flex gap-2">
        <label className={`${LABEL} flex-1`}>
          Post type
          <select
            value={ig.type}
            onChange={(e) => set("type", e.target.value as InstagramMeta["type"])}
            className={`${INPUT} capitalize`}
          >
            {INSTAGRAM_POST_TYPES.map((t) => (
              <option key={t} value={t} className="bg-slate-900 capitalize">
                {t}
              </option>
            ))}
          </select>
        </label>

        {ig.type === "carousel" && (
          <label className={`${LABEL} w-28`}>
            <span className="inline-flex items-center gap-1">
              <Layers className="w-3 h-3" /> Slides
            </span>
            <input
              type="number"
              min={2}
              max={20}
              value={ig.slides_count}
              onChange={(e) => set("slides_count", Number(e.target.value) || 2)}
              className={INPUT}
            />
          </label>
        )}
      </div>

      <label className={LABEL}>
        <span className="inline-flex items-center gap-1">
          <MessageSquare className="w-3 h-3" /> Caption
        </span>
        <textarea
          value={ig.caption}
          onChange={(e) => set("caption", e.target.value)}
          rows={3}
          placeholder="Hook, body, CTA, hashtags…"
          className={`${INPUT} resize-y`}
        />
      </label>

      <label className={LABEL}>
        <span className="inline-flex items-center gap-1">
          <ImageIcon className="w-3 h-3" /> Image prompt
        </span>
        <textarea
          value={ig.image_prompt}
          onChange={(e) => set("image_prompt", e.target.value)}
          rows={2}
          placeholder="Visual direction for the generated graphic…"
          className={`${INPUT} resize-y`}
        />
      </label>
    </div>
  );
}

/**
 * Post-performance numbers, shown read-only once a post has been published and
 * its metrics synced back into meta. Separate from the editor because these are
 * measurements, not plan inputs.
 */
export function PlatformMetaStats({ platform, meta }: Omit<Props, "onChange">) {
  if (platform !== "instagram") return null;

  const ig = instagramMeta(meta);
  const stats = (
    [
      ["Reach", ig.reach],
      ["Likes", ig.likes],
      ["Saves", ig.saves],
      ["Shares", ig.shares],
    ] as const
  ).filter(([, v]) => (v ?? 0) > 0);

  if (stats.length === 0) return null;

  return (
    <div className="flex items-center gap-3 text-[10px] text-slate-500">
      {stats.map(([label, value]) => (
        <span key={label}>
          <span className="text-slate-300 font-mono">{value!.toLocaleString()}</span> {label}
        </span>
      ))}
    </div>
  );
}
