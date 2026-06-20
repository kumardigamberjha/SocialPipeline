"use client";

/**
 * BlogViewer — renders a long-form (~20,000 word) markdown blog post.
 *
 * Features:
 *  - Markdown rendering with GFM tables + syntax-highlighted code blocks
 *  - Auto-generated Table of Contents from ## (H2) headings, sticky on desktop,
 *    collapsing to a dropdown on mobile
 *  - Reading-progress bar pinned to the top of the viewport
 *  - Word count + reading time in the header
 *  - Per-code-block "Copy" button, plus a "Copy full markdown" button
 *  - Section jump links with active-section highlighting (scrollspy)
 *  - Dark theme consistent with the rest of the dashboard
 *
 * Requires (add to dashboard/package.json):
 *   react-markdown  remark-gfm  react-syntax-highlighter  @types/react-syntax-highlighter
 */

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  Check,
  ChevronDown,
  Clock,
  Copy,
  FileText,
  List,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

export interface BlogViewerProps {
  /** Full markdown body of the post (the H1 title + sections). */
  content: string;
  /** Optional explicit title; otherwise derived from the first H1. */
  title?: string;
  wordCount?: number;
  readingTimeMinutes?: number;
  niche?: string;
}

interface TocItem {
  id: string;
  text: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Stable, URL-safe id from heading text — must match the id we set on <h2>. */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

/** Recursively flatten React children into a plain text string. */
function childrenToText(children: ReactNode): string {
  if (children == null || typeof children === "boolean") return "";
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (Array.isArray(children)) return children.map(childrenToText).join("");
  if (typeof children === "object" && "props" in children) {
    // React element — recurse into its children.
    const el = children as { props?: { children?: ReactNode } };
    return childrenToText(el.props?.children);
  }
  return "";
}

/** Parse ## headings out of the raw markdown for the TOC (ignores ### and code fences). */
function extractToc(markdown: string): TocItem[] {
  const items: TocItem[] = [];
  const seen = new Map<string, number>();
  let inFence = false;

  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trimEnd();
    if (line.startsWith("```")) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    // Match "## Heading" but not "### Heading".
    const match = /^##\s+(?!#)(.*)$/.exec(line);
    if (!match) continue;

    const text = match[1].replace(/[*_`]/g, "").trim();
    if (!text) continue;

    let id = slugify(text);
    // Disambiguate duplicate headings so jump links stay unique.
    const count = seen.get(id) ?? 0;
    seen.set(id, count + 1);
    if (count > 0) id = `${id}-${count}`;

    items.push({ id, text });
  }
  return items;
}

// ── Code block with copy button ──────────────────────────────────────────────

function CodeBlock({
  language,
  value,
}: {
  language: string;
  value: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — no-op */
    }
  };

  return (
    <div className="relative group my-5">
      <div className="flex items-center justify-between px-4 py-1.5 rounded-t-lg bg-white/5 border border-white/10 border-b-0">
        <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-white transition-colors"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-green-400" /> Copied
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" /> Copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: "0 0 0.5rem 0.5rem",
          fontSize: "0.85rem",
          border: "1px solid rgba(255,255,255,0.1)",
          borderTop: "none",
        }}
        PreTag="div"
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
}

// ── Heading id tracking (so scrollspy ids stay unique & match the TOC) ────────

function makeHeadingCounter() {
  const seen = new Map<string, number>();
  return (text: string): string => {
    let id = slugify(text);
    const count = seen.get(id) ?? 0;
    seen.set(id, count + 1);
    if (count > 0) id = `${id}-${count}`;
    return id;
  };
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function BlogViewer({
  content,
  title,
  wordCount,
  readingTimeMinutes,
  niche,
}: BlogViewerProps) {
  const [progress, setProgress] = useState(0);
  const [activeId, setActiveId] = useState<string>("");
  const [mobileTocOpen, setMobileTocOpen] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const articleRef = useRef<HTMLElement>(null);

  const toc = useMemo(() => extractToc(content), [content]);

  // Derived title/word count fall back to parsing the markdown.
  const derivedTitle = useMemo(() => {
    if (title) return title;
    const h1 = /^#\s+(.+)$/m.exec(content);
    return h1 ? h1[1].trim() : "Untitled Post";
  }, [title, content]);

  const derivedWordCount = useMemo(
    () => wordCount ?? content.split(/\s+/).filter(Boolean).length,
    [wordCount, content],
  );
  const derivedReadingTime = useMemo(
    () => readingTimeMinutes ?? Math.max(1, Math.round(derivedWordCount / 238)),
    [readingTimeMinutes, derivedWordCount],
  );

  // Reading-progress bar driven by article scroll position.
  useEffect(() => {
    const onScroll = () => {
      const el = articleRef.current;
      if (!el) return;
      const total = el.scrollHeight - window.innerHeight;
      const scrolled = window.scrollY - el.offsetTop;
      const pct = total > 0 ? (scrolled / total) * 100 : 0;
      setProgress(Math.min(100, Math.max(0, pct)));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [content]);

  // Scrollspy — highlight the TOC entry for the section currently in view.
  useEffect(() => {
    if (toc.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target.id) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -70% 0px", threshold: 0 },
    );
    for (const { id } of toc) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [toc]);

  const jumpTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      setMobileTocOpen(false);
    }
  };

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 1500);
    } catch {
      /* no-op */
    }
  };

  // Fresh heading counter per render so ids stay deterministic and match the TOC.
  const nextHeadingId = makeHeadingCounter();

  return (
    <div className="relative w-full text-slate-200">
      {/* Reading progress bar */}
      <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-transparent">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-[width] duration-150 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight">
            {derivedTitle}
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {derivedReadingTime} min read
            </span>
            <span className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" />
              {derivedWordCount.toLocaleString()} words
            </span>
            {niche && (
              <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 tracking-wide">
                {niche}
              </span>
            )}
            <button
              type="button"
              onClick={copyAll}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:text-white transition-colors"
            >
              {copiedAll ? (
                <>
                  <Check className="w-3.5 h-3.5 text-green-400" /> Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" /> Copy full markdown
                </>
              )}
            </button>
          </div>
        </header>

        {/* Mobile TOC dropdown */}
        {toc.length > 0 && (
          <div className="lg:hidden mb-6">
            <button
              type="button"
              onClick={() => setMobileTocOpen((v) => !v)}
              className="w-full flex items-center justify-between px-4 py-3 rounded-xl glass-card border border-white/10"
            >
              <span className="flex items-center gap-2 text-sm font-medium text-white">
                <List className="w-4 h-4" /> Table of Contents
              </span>
              <ChevronDown
                className={`w-4 h-4 transition-transform ${mobileTocOpen ? "rotate-180" : ""}`}
              />
            </button>
            {mobileTocOpen && (
              <nav className="mt-2 p-2 rounded-xl glass-card border border-white/10 max-h-72 overflow-y-auto custom-scrollbar">
                {toc.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => jumpTo(item.id)}
                    className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                      activeId === item.id
                        ? "bg-blue-500/10 text-blue-300"
                        : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                  >
                    {item.text}
                  </button>
                ))}
              </nav>
            )}
          </div>
        )}

        <div className="flex gap-10">
          {/* Desktop sticky TOC */}
          {toc.length > 0 && (
            <aside className="hidden lg:block w-64 shrink-0">
              <nav className="sticky top-16 max-h-[calc(100vh-5rem)] overflow-y-auto custom-scrollbar pr-2">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-1 h-4 bg-gradient-to-b from-blue-500 to-purple-500 rounded-full" />
                  <h2 className="text-[11px] font-bold tracking-[0.25em] uppercase text-slate-400">
                    Contents
                  </h2>
                </div>
                <ul className="space-y-0.5 border-l border-white/10">
                  {toc.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => jumpTo(item.id)}
                        className={`block w-full text-left -ml-px pl-4 py-1.5 border-l text-sm transition-colors ${
                          activeId === item.id
                            ? "border-blue-500 text-blue-300"
                            : "border-transparent text-slate-500 hover:text-white hover:border-white/30"
                        }`}
                      >
                        {item.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            </aside>
          )}

          {/* Article */}
          <article
            ref={articleRef}
            className="min-w-0 flex-1 blog-prose"
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Skip the H1 — it's already shown in the header above.
                h1: () => null,
                h2: ({ children }) => {
                  const text = childrenToText(children);
                  const id = nextHeadingId(text);
                  return (
                    <h2
                      id={id}
                      className="scroll-mt-20 mt-12 mb-4 text-2xl font-bold text-white border-b border-white/10 pb-2"
                    >
                      {children}
                    </h2>
                  );
                },
                h3: ({ children }) => (
                  <h3 className="mt-8 mb-3 text-xl font-semibold text-slate-100">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="my-4 leading-7 text-slate-300">{children}</p>
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
                ul: ({ children }) => (
                  <ul className="my-4 ml-5 list-disc space-y-1.5 text-slate-300 marker:text-slate-600">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="my-4 ml-5 list-decimal space-y-1.5 text-slate-300 marker:text-slate-600">
                    {children}
                  </ol>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="my-5 pl-4 border-l-2 border-blue-500/50 text-slate-400 italic">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="my-6 overflow-x-auto custom-scrollbar rounded-lg border border-white/10">
                    <table className="w-full text-sm border-collapse">{children}</table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="bg-white/5">{children}</thead>
                ),
                th: ({ children }) => (
                  <th className="px-4 py-2 text-left font-semibold text-white border-b border-white/10">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-4 py-2 text-slate-300 border-b border-white/5 align-top">
                    {children}
                  </td>
                ),
                hr: () => <hr className="my-10 border-white/10" />,
                code(props) {
                  const { children, className, ...rest } = props as {
                    children?: ReactNode;
                    className?: string;
                    inline?: boolean;
                  };
                  const match = /language-(\w+)/.exec(className || "");
                  const text = String(children ?? "").replace(/\n$/, "");
                  // Block code (fenced) → highlighter; inline code → styled span.
                  if (match || text.includes("\n")) {
                    return <CodeBlock language={match?.[1] ?? ""} value={text} />;
                  }
                  return (
                    <code
                      className="px-1.5 py-0.5 rounded bg-white/10 text-blue-300 font-mono text-[0.85em]"
                      {...rest}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {content}
            </ReactMarkdown>
          </article>
        </div>
      </div>
    </div>
  );
}
