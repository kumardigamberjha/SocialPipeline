/**
 * Image Studio — prompt in, picture out.
 *
 * Renders are not static files: the backend serves each one through an
 * owner-scoped route (see app/routers/images.py), so the bytes are fetched with
 * credentials and turned into object URLs rather than linked directly.
 */

import { request, requestBlob } from "./apiClient";

const BASE = "/images";

/** Mirrors _ASPECT_RATIO_ENUM in app/services/gemini_image_client.py. */
export const ASPECT_RATIOS = [
  "1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2",
  "9:16", "16:9", "21:9", "1:4", "4:1", "1:8", "8:1",
] as const;
export type AspectRatio = (typeof ASPECT_RATIOS)[number];

export const IMAGE_SIZES = ["512", "1K", "2K", "4K"] as const;
export type ImageSize = (typeof IMAGE_SIZES)[number];

/**
 * Aliases, never raw model ids — the backend only accepts these three so a
 * request cannot bill against an arbitrary model on the account.
 */
export const IMAGE_MODELS = [
  { value: "gemini_flash", label: "Flash", hint: "Balanced — the default" },
  { value: "gemini_flash_lite", label: "Flash Lite", hint: "Fastest, cheapest" },
  { value: "gemini_pro", label: "Pro", hint: "Highest quality, slowest" },
] as const;
export type ImageModel = (typeof IMAGE_MODELS)[number]["value"];

export interface GenerateImagePayload {
  prompt: string;
  negative_prompt?: string | null;
  aspect_ratio: AspectRatio;
  image_size: ImageSize;
  model?: ImageModel | null;
  seed?: number | null;
}

export interface GeneratedImage {
  id: string;
  prompt: string;
  negative_prompt?: string | null;
  model: string;
  aspect_ratio: string;
  image_size: string;
  seed?: number | null;
  duration_s?: number | null;
  created_at?: string | null;
}

export interface GeneratedImageResult extends GeneratedImage {
  /** The render the user is waiting on, inline — saves a second round trip. */
  image_b64: string;
}

export interface GeneratedImageList {
  total: number;
  images: GeneratedImage[];
}

export const imagesApi = {
  generate: (payload: GenerateImagePayload) =>
    request<GeneratedImageResult>(`${BASE}/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  list: (limit = 50, offset = 0) =>
    request<GeneratedImageList>(`${BASE}?limit=${limit}&offset=${offset}`),

  /** Object URL for one stored render. Callers must revokeObjectURL on unmount. */
  fileUrl: async (id: string) =>
    URL.createObjectURL(await requestBlob(`${BASE}/${id}/file`)),

  remove: (id: string) => request<{ deleted: string }>(`${BASE}/${id}`, { method: "DELETE" }),
};
