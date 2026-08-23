"use client";

import { Send } from "lucide-react";
import { useState } from "react";

const MAX_CHARS = 2000;

export default function ChatComposer({
  onSend,
  disabled,
  value,
  onChange,
}: {
  onSend: (question: string) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}) {
  const [internal, setInternal] = useState("");
  const text = value ?? internal;
  const setText = onChange ?? setInternal;

  const submit = () => {
    const question = text.trim();
    if (!question || disabled) return;
    onSend(question);
    setText("");
  };

  return (
    <div className="glass-card rounded-xl border border-white/5 p-2">
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          disabled={disabled}
          placeholder="Aaj kya post karna hai?"
          className="max-h-40 min-h-[38px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={disabled || !text.trim()}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-purple-600 text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          aria-label="Send"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      {text.length > MAX_CHARS - 200 && (
        <div className="px-2 pb-1 text-right text-[10px] text-slate-600">
          {text.length}/{MAX_CHARS}
        </div>
      )}
    </div>
  );
}
