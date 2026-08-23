"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays, Loader2, Layers } from "lucide-react";
import {
  Platform,
  PlanItem,
  ProductionStatus,
  plannerApi,
  statusesFor,
} from "@/lib/plannerApi";

/**
 * Kanban view of a platform's items, grouped by production status.
 *
 * The column set comes from the platform, not from this component: YouTube
 * runs the six-stage video pipeline, everything else the four-stage board. The
 * backend sends its own `statuses` order alongside the items, and that wins —
 * so a platform added server-side shows up here with no change needed.
 */

const COLUMN_TINTS: Record<string, string> = {
  pending: "border-slate-600/50",
  idea: "border-slate-600/50",
  script_generated: "border-amber-500/50",
  in_production: "border-amber-500/50",
  presentation_created: "border-orange-500/50",
  video_created: "border-blue-500/50",
  video_edited: "border-indigo-500/50",
  scheduled: "border-blue-500/50",
  video_published: "border-green-500/50",
  published: "border-green-500/50",
};

export default function PlanBoard({
  platform,
  planId,
  onOpenPlan,
}: {
  platform: Platform;
  planId?: string;
  onOpenPlan?: (planId: string) => void;
}) {
  const [items, setItems] = useState<PlanItem[] | null>(null);
  const [statuses, setStatuses] = useState<ProductionStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const board = await plannerApi.getBoard(platform, planId);
      setItems(board.items);
      // Trust the server's column order; fall back to the local table only if
      // an older backend omits it.
      setStatuses(
        board.statuses?.length
          ? board.statuses
          : statusesFor(platform).map((s) => s.value),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the board");
      setItems([]);
    }
  }, [platform, planId]);

  useEffect(() => {
    load();
  }, [load]);

  const moveItem = async (item: PlanItem, status: ProductionStatus) => {
    setMovingId(item.id);
    // Optimistic: the card jumps columns immediately, and we reload on failure.
    setItems((prev) =>
      (prev ?? []).map((i) =>
        i.id === item.id ? { ...i, production_status: status } : i,
      ),
    );
    try {
      await plannerApi.updateItem(item.plan_id, item.id, { production_status: status });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move that card");
      load();
    } finally {
      setMovingId(null);
    }
  };

  const labelFor = (status: ProductionStatus) =>
    statusesFor(platform).find((s) => s.value === status)?.label ??
    status.replace(/_/g, " ");

  if (items === null) {
    return (
      <div className="flex items-center justify-center gap-2 text-slate-500 py-16">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading board…
      </div>
    );
  }

  return (
    <div>
      {error && <p className="text-xs text-red-400 mb-4">{error}</p>}

      {items.length === 0 && (
        <div className="text-center py-16 border border-dashed border-white/10 rounded-2xl">
          <p className="text-sm text-slate-500">Nothing on this board yet.</p>
          <p className="text-xs text-slate-600 mt-1">
            Generate a roadmap and add it to the planner, or create a plan.
          </p>
        </div>
      )}

      {items.length > 0 && (
        // The board scrolls inside its own container so the page never scrolls
        // sideways on a narrow screen.
        <div className="overflow-x-auto -mx-1 px-1 pb-2">
          <div className="flex gap-3 min-w-max">
            {statuses.map((status) => {
              const columnItems = items.filter((i) => i.production_status === status);
              return (
                <div
                  key={status}
                  className={`w-[260px] flex-shrink-0 rounded-xl border-t-2 bg-white/[0.02] border border-white/5 ${
                    COLUMN_TINTS[status] ?? "border-t-white/10"
                  }`}
                >
                  <div className="px-3 py-2.5 border-b border-white/5 flex items-center justify-between">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
                      {labelFor(status)}
                    </p>
                    <span className="text-[10px] tabular-nums text-slate-500">
                      {columnItems.length}
                    </span>
                  </div>

                  <div className="p-2 space-y-2 min-h-[80px]">
                    {columnItems.map((item) => (
                      <div
                        key={item.id}
                        className={`rounded-lg bg-white/[0.03] border border-white/5 p-2.5 transition-opacity ${
                          movingId === item.id ? "opacity-50" : ""
                        }`}
                      >
                        <p className="text-xs font-medium text-white leading-snug">
                          {item.topic}
                        </p>

                        <div className="flex items-center gap-1.5 mt-1.5 text-[10px] text-slate-500">
                          <CalendarDays size={11} />
                          <span className="tabular-nums">
                            {item.scheduled_date ?? "No date"}
                          </span>
                          {typeof item.meta?.type === "string" && (
                            <span className="flex items-center gap-1">
                              · <Layers size={10} /> {item.meta.type as string}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5 mt-2">
                          <select
                            value={status}
                            onChange={(e) =>
                              moveItem(item, e.target.value as ProductionStatus)
                            }
                            aria-label={`Move "${item.topic}" to another column`}
                            className="flex-1 min-w-0 text-[10px] rounded bg-white/5 border border-white/10 px-1.5 py-1 text-slate-300 focus:outline-none focus:border-blue-500/50"
                          >
                            {statuses.map((s) => (
                              <option key={s} value={s} className="bg-[#0f172a]">
                                {labelFor(s)}
                              </option>
                            ))}
                          </select>
                          {onOpenPlan && (
                            <button
                              onClick={() => onOpenPlan(item.plan_id)}
                              className="text-[10px] px-1.5 py-1 rounded text-slate-400 hover:text-blue-300 hover:bg-white/5 transition-colors"
                            >
                              Open
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
