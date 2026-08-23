"use client";

/**
 * Markdown for chat bubbles, styled by an explicit component map.
 *
 * Deliberately NOT `prose prose-invert`: `@tailwindcss/typography` is not
 * installed and `globals.css` has no `@plugin` line, so those classes are inert
 * today. Installing the plugin would retroactively restyle TelemetryLedger and
 * ContentReviewModal — two components this feature does not touch and nobody is
 * testing here — so the blast radius is kept to this page instead. The pattern
 * follows BlogViewer's override map.
 *
 * Two rules are security, not style:
 *   - `img` renders nothing. An injected image URL in model output is an
 *     exfiltration beacon that fires on render.
 *   - `a` always gets rel="noopener noreferrer".
 */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const COMPONENTS: Components = {
  p: ({ children }) => <p className="my-2 leading-relaxed text-slate-300">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-2 ml-5 list-disc space-y-1 marker:text-slate-600">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 ml-5 list-decimal space-y-1 marker:text-slate-600">{children}</ol>
  ),
  li: ({ children }) => <li className="text-slate-300">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-200">{children}</em>,
  // A chat bubble has no heading hierarchy; collapse them all to one weight.
  h1: ({ children }) => <p className="mt-4 mb-1.5 text-sm font-semibold text-white">{children}</p>,
  h2: ({ children }) => <p className="mt-4 mb-1.5 text-sm font-semibold text-white">{children}</p>,
  h3: ({ children }) => <p className="mt-4 mb-1.5 text-sm font-semibold text-white">{children}</p>,
  hr: () => <hr className="my-3 border-white/10" />,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-white/15 pl-3 text-slate-400">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-white/10 px-2 py-1.5 font-semibold text-slate-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-white/5 px-2 py-1.5 text-slate-300">{children}</td>
  ),
  code: ({ children, ...props }) => {
    const inline = !String(props.className ?? "").includes("language-");
    if (inline) {
      return (
        <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em] text-blue-300">
          {children}
        </code>
      );
    }
    return <code className="font-mono text-xs text-slate-200">{children}</code>;
  },
  // No syntax highlighter: the assistant emits no code, and pulling one in
  // would add ~200KB to a page that never uses it.
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-lg bg-black/40 p-3 text-xs">{children}</pre>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-400 underline underline-offset-2 hover:text-blue-300"
    >
      {children}
    </a>
  ),
  img: () => null,
};

export default function MarkdownMessage({ children }: { children: string }) {
  return (
    <div className="text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
