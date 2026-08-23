/**
 * Simple API client for the Wings of AI backend.
 */

import { request } from "@/lib/apiClient";

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  providers: string[];
  agents_available: number;
}

export interface GenerateResponse {
  status: string;
  topic: string;
  provider_used: string;
  duration_seconds: number;
  result: string;
}

export const api = {
  // Public endpoint — no session required, so it's exempt from the
  // apiClient's 401 -> refresh -> redirect cycle (there's no session to lose).
  getHealth: () => request<HealthResponse>("/health", { skipAuthRetry: true }),

  generateContent: (topic: string, provider: string = "ollama") =>
    request<GenerateResponse>("/generate", {
      method: "POST",
      body: JSON.stringify({ topic, provider }),
    }),
};
