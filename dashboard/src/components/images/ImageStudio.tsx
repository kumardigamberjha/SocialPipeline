"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  Image as ImageIcon,
  Loader2,
  Settings2,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";

import {
  ASPECT_RATIOS,
  GeneratedImage,
  GeneratedImageResult,
  IMAGE_MODELS,
  IMAGE_SIZES,
  imagesApi,
  type AspectRatio,
  type ImageModel,
  type ImageSize,
} from "@/lib/imagesApi";

const EXAMPLE_PROMPTS = [
  "A lone red bicycle against a whitewashed wall, harsh midday sun, deep shadows",
  "Cross-section of a mechanical keyboard switch, technical illustration, blueprint style",
  "Bioluminescent jellyfish drifting through a dark ocean trench, volumetric light",
  "A cosy home office at dawn, warm lamp light, plants, film grain",
];

// ─── Stored render thumbnail ──────────────────────────────────────────────────

/**
 * Loads its own bytes. The file route is owner-scoped rather than a static
 * mount, so the URL cannot go straight into `src` — it is fetched with
 * credentials and held as an object URL for this component's lifetime.
 */
function GalleryThumb({
  image,
  onOpen,
  onDelete,
}: {
  image: GeneratedImage;
  onOpen: (url: string, image: GeneratedImage) => void;
  onDelete: (id: string) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;

    imagesApi
      .fileUrl(image.id)
      .then((u) => {
        if (revoked) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
      })
      .catch(() => setFailed(true));

    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image.id]);

  return (
    <div className="group relative overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03]">
      <div className="flex aspect-square items-center justify-center bg-black/20">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={image.prompt}
            className="h-full w-full cursor-zoom-in object-cover"
            onClick={() => onOpen(url, image)}
          />
        ) : failed ? (
          <AlertTriangle size={18} className="text-slate-600" />
        ) : (
          <Loader2 size={18} className="animate-spin text-slate-600" />
        )}
      </div>

      <div className="p-2.5">
        <p className="line-clamp-2 text-[11px] leading-snug text-slate-400">{image.prompt}</p>
        <p className="mt-1 text-[10px] text-slate-600">
          {image.aspect_ratio} · {image.image_size}
          {image.seed != null ? ` · seed ${image.seed}` : ""}
        </p>
      </div>

      <button
        onClick={() => onDelete(image.id)}
        title="Delete"
        className="absolute right-2 top-2 rounded-lg bg-black/60 p-1.5 text-slate-300 opacity-0 transition-opacity hover:bg-red-600 hover:text-white group-hover:opacity-100"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function ImageStudio() {
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("1:1");
  const [imageSize, setImageSize] = useState<ImageSize>("1K");
  const [model, setModel] = useState<ImageModel>("gemini_flash");
  const [seed, setSeed] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<GeneratedImageResult | null>(null);

  const [gallery, setGallery] = useState<GeneratedImage[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(true);
  const [lightbox, setLightbox] = useState<{ url: string; image: GeneratedImage } | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);

  const loadGallery = useCallback(async () => {
    try {
      const res = await imagesApi.list();
      setGallery(res.images);
    } catch {
      /* the gallery is secondary; a failure here must not block generating */
    } finally {
      setGalleryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  const handleGenerate = async () => {
    const text = prompt.trim();
    if (!text || generating) return;

    setGenerating(true);
    setError(null);
    try {
      const parsedSeed = seed.trim() === "" ? null : Number(seed);
      const result = await imagesApi.generate({
        prompt: text,
        negative_prompt: negativePrompt.trim() || null,
        aspect_ratio: aspectRatio,
        image_size: imageSize,
        model,
        seed: Number.isFinite(parsedSeed as number) ? (parsedSeed as number) : null,
      });
      setCurrent(result);
      // Prepend rather than refetch — the new render is already the newest row.
      setGallery((prev) => [result, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image generation failed.");
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id: string) => {
    const previous = gallery;
    setGallery((prev) => prev.filter((g) => g.id !== id));
    if (current?.id === id) setCurrent(null);
    try {
      await imagesApi.remove(id);
    } catch {
      setGallery(previous); // put it back; the delete did not happen
    }
  };

  const downloadCurrent = () => {
    if (!current) return;
    const a = document.createElement("a");
    a.href = `data:image/png;base64,${current.image_b64}`;
    a.download = `${current.prompt.slice(0, 40).replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.png`;
    a.click();
  };

  const onPromptKeyDown = (e: React.KeyboardEvent) => {
    // Cmd/Ctrl+Enter submits; plain Enter keeps making newlines.
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleGenerate();
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="h-4 w-1 rounded-full bg-gradient-to-b from-fuchsia-500 to-violet-500" />
        <h1 className="text-sm font-bold uppercase tracking-[0.2em] text-slate-300">
          Image Studio
        </h1>
        <div className="ml-2 h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* ── Prompt panel ───────────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
            <label
              htmlFor="prompt"
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400"
            >
              Prompt
            </label>
            <textarea
              id="prompt"
              ref={promptRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={onPromptKeyDown}
              rows={5}
              placeholder="Describe the image you want…"
              className="w-full resize-y rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-violet-500/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
            />

            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[11px] text-slate-500">Aspect ratio</label>
                <select
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value as AspectRatio)}
                  className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
                >
                  {ASPECT_RATIOS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-slate-500">Size</label>
                <select
                  value={imageSize}
                  onChange={(e) => setImageSize(e.target.value as ImageSize)}
                  className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
                >
                  {IMAGE_SIZES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            <button
              onClick={() => setShowAdvanced((v) => !v)}
              className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500 transition-colors hover:text-slate-300"
            >
              <Settings2 size={12} />
              {showAdvanced ? "Hide" : "Show"} advanced
            </button>

            {showAdvanced && (
              <div className="mt-3 space-y-3 border-t border-white/[0.06] pt-3">
                <div>
                  <label className="mb-1 block text-[11px] text-slate-500">Model</label>
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value as ImageModel)}
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-slate-200 focus:border-violet-500/50 focus:outline-none"
                  >
                    {IMAGE_MODELS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label} — {m.hint}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-[11px] text-slate-500">
                    Avoid (negative prompt)
                  </label>
                  <input
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    placeholder="text, watermark, blurry…"
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-violet-500/50 focus:outline-none"
                  />
                  <p className="mt-1 text-[10px] text-slate-600">
                    Gemini has no separate negative field — this is appended to your prompt
                    as an instruction.
                  </p>
                </div>

                <div>
                  <label className="mb-1 block text-[11px] text-slate-500">Seed</label>
                  <input
                    value={seed}
                    onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
                    inputMode="numeric"
                    placeholder="random"
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-violet-500/50 focus:outline-none"
                  />
                  <p className="mt-1 text-[10px] text-slate-600">
                    Same prompt + same seed reproduces the same image.
                  </p>
                </div>
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-500"
            >
              {generating ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Wand2 size={15} />
                  Generate
                </>
              )}
            </button>
            <p className="mt-2 text-center text-[10px] text-slate-600">
              ⌘/Ctrl + Enter to generate
            </p>
          </div>

          {/* Starters — only while the canvas is untouched */}
          {!current && !generating && (
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <Sparkles size={12} /> Try one
              </p>
              <div className="space-y-1.5">
                {EXAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setPrompt(p);
                      promptRef.current?.focus();
                    }}
                    className="block w-full rounded-lg border border-white/[0.06] px-2.5 py-2 text-left text-[11px] leading-snug text-slate-400 transition-colors hover:border-violet-500/30 hover:text-slate-200"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Canvas ─────────────────────────────────────────────────── */}
        <div className="space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-300">
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}

          <div className="flex min-h-[360px] items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
            {generating ? (
              <div className="flex flex-col items-center gap-3 text-slate-500">
                <Loader2 size={28} className="animate-spin text-violet-400" />
                <p className="text-xs">Rendering your prompt…</p>
              </div>
            ) : current ? (
              <div className="w-full space-y-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:image/png;base64,${current.image_b64}`}
                  alt={current.prompt}
                  className="mx-auto max-h-[62vh] w-auto max-w-full rounded-lg"
                />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-slate-500">
                    {current.model} · {current.aspect_ratio} · {current.image_size}
                    {current.seed != null ? ` · seed ${current.seed}` : ""}
                    {current.duration_s != null ? ` · ${current.duration_s}s` : ""}
                  </p>
                  <button
                    onClick={downloadCurrent}
                    className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-white/5"
                  >
                    <Download size={13} />
                    Download
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-center text-slate-600">
                <ImageIcon size={30} />
                <p className="text-xs">Your generated image will appear here.</p>
              </div>
            )}
          </div>

          {/* ── Gallery ──────────────────────────────────────────────── */}
          <div className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Your renders
            </h2>
            {galleryLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 size={18} className="animate-spin text-slate-600" />
              </div>
            ) : gallery.length === 0 ? (
              <p className="py-8 text-center text-xs text-slate-600">
                Nothing generated yet.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {gallery.map((img) => (
                  <GalleryThumb
                    key={img.id}
                    image={img}
                    onOpen={(url, image) => setLightbox({ url, image })}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-black/80 p-6"
        >
          <div className="max-w-4xl space-y-2" onClick={(e) => e.stopPropagation()}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightbox.url}
              alt={lightbox.image.prompt}
              className="max-h-[80vh] w-auto max-w-full rounded-lg"
            />
            <p className="text-center text-xs text-slate-400">{lightbox.image.prompt}</p>
          </div>
        </div>
      )}
    </div>
  );
}
