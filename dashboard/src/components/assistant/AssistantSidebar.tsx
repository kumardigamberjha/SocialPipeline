"use client";

import { MessageSquarePlus, Trash2 } from "lucide-react";

import type { Conversation } from "@/lib/assistantApi";

export default function AssistantSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col gap-2 lg:flex">
      <button
        onClick={onNew}
        className="flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-white/5"
      >
        <MessageSquarePlus className="h-3.5 w-3.5" />
        New chat
      </button>

      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {conversations.length === 0 && (
          <p className="px-3 py-2 text-[11px] text-slate-600">No conversations yet.</p>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`group flex items-center gap-1 rounded-lg px-2.5 py-2 transition-colors ${
              c.id === activeId ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
            }`}
          >
            <button
              onClick={() => onSelect(c.id)}
              className="min-w-0 flex-1 truncate text-left text-xs text-slate-300"
              title={c.title}
            >
              {c.title}
            </button>
            <button
              onClick={() => onDelete(c.id)}
              className="opacity-0 transition-opacity group-hover:opacity-100"
              aria-label="Delete conversation"
            >
              <Trash2 className="h-3 w-3 text-slate-600 hover:text-rose-400" />
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
