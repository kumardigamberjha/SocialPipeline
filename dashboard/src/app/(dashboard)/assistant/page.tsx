"use client";

/**
 * The assistant page — ask about your own schedule, in English or Hinglish.
 *
 * The only stateful container in the feature. Everything below it is
 * presentational, except ActionCard, which owns its own confirm lifecycle
 * because a write must not be retried by a parent re-render.
 */

import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import AssistantSidebar from "@/components/assistant/AssistantSidebar";
import ChatComposer from "@/components/assistant/ChatComposer";
import ChatMessage, { type ChatTurn } from "@/components/assistant/ChatMessage";
import DigestStrip from "@/components/assistant/DigestStrip";
import ThinkingIndicator from "@/components/assistant/ThinkingIndicator";
import {
  assistantApi,
  SUGGESTED_PROMPTS,
  type AssistantAction,
  type Conversation,
  type Digest,
} from "@/lib/assistantApi";

export default function AssistantPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState(false);
  const [draft, setDraft] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    assistantApi.digest().then(setDigest).catch(() => setDigest(null));
    assistantApi.listConversations().then(setConversations).catch(() => setConversations([]));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, pending]);

  const openConversation = useCallback(async (id: string) => {
    setConversationId(id);
    setTurns([]);
    try {
      const detail = await assistantApi.getConversation(id);
      const byMessage = new Map<string, AssistantAction[]>();
      // Actions arrive in one batch and are attached client-side, rather than
      // one query per assistant bubble.
      for (const action of detail.actions) {
        const key = action.message_id ?? "";
        byMessage.set(key, [...(byMessage.get(key) ?? []), action]);
      }
      setTurns(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          resolved: m.meta
            ? {
                intent: m.meta.intent ?? "",
                date_from: m.meta.date_from ?? null,
                date_to: m.meta.date_to ?? null,
                platforms: m.meta.platforms ?? [],
              }
            : null,
          actions: byMessage.get(m.id) ?? [],
        })),
      );
    } catch {
      setTurns([
        {
          id: "load-error",
          role: "assistant",
          content: "Couldn't load that conversation.",
          error: true,
        },
      ]);
    }
  }, []);

  const send = useCallback(
    async (question: string) => {
      const localId = `local-${Date.now()}`;
      setTurns((prev) => [...prev, { id: localId, role: "user", content: question }]);
      setPending(true);

      try {
        const res = await assistantApi.ask(question, conversationId);
        setConversationId(res.conversation_id);
        setTurns((prev) => [
          ...prev,
          {
            id: res.message_id,
            role: "assistant",
            content: res.answer_markdown,
            resolved: res.resolved,
            actions: res.actions,
            sources: res.sources,
          },
        ]);
        assistantApi.listConversations().then(setConversations).catch(() => {});
        // A confirmed action can change the numbers; so can simply asking after
        // work happened elsewhere. Cheap enough to refresh every turn.
        assistantApi.digest().then(setDigest).catch(() => {});
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Something went wrong.";
        setTurns((prev) => [
          ...prev,
          { id: `err-${Date.now()}`, role: "assistant", content: detail, error: true },
        ]);
      } finally {
        setPending(false);
      }
    },
    [conversationId],
  );

  const startNew = () => {
    setConversationId(null);
    setTurns([]);
    setDraft("");
  };

  const remove = async (id: string) => {
    try {
      await assistantApi.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (id === conversationId) startNew();
    } catch {
      /* the row stays listed; the next load reconciles it */
    }
  };

  const empty = turns.length === 0;

  return (
    <section className="mx-auto flex w-full max-w-7xl flex-1 gap-6 overflow-hidden px-4 sm:px-6 lg:px-8">
      <AssistantSidebar
        conversations={conversations}
        activeId={conversationId}
        onSelect={openConversation}
        onNew={startNew}
        onDelete={remove}
      />

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center gap-2">
          <div className="h-4 w-1 rounded-full bg-gradient-to-b from-blue-500 to-purple-600" />
          <h1 className="text-[11px] font-bold uppercase tracking-[0.25em] text-slate-400">
            Assistant
          </h1>
        </div>

        <DigestStrip digest={digest} />

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          {empty && (
            <div className="glass-card rounded-xl border border-white/5 p-6 text-center">
              <Sparkles className="mx-auto mb-2 h-5 w-5 text-purple-400" />
              <p className="text-sm text-slate-300">
                Ask about your schedule, drafts or backlog.
              </p>
              <p className="mt-1 text-xs text-slate-500">
                English ya Hinglish — jo comfortable ho.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => setDraft(prompt)}
                    className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <ChatMessage key={turn.id} turn={turn} />
          ))}

          {pending && <ThinkingIndicator />}
          <div ref={bottomRef} />
        </div>

        <ChatComposer onSend={send} disabled={pending} value={draft} onChange={setDraft} />
      </div>
    </section>
  );
}
