/**
 * Simple API client for the Wings of AI backend.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_API || "http://127.0.0.1:8000";
const API_BASE_URL = `${BACKEND_URL}/api`;

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
  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) throw new Error("Backend health check failed");
    return response.json();
  },

  async generateContent(topic: string, provider: string = "nvidia"): Promise<GenerateResponse> {
    const response = await fetch(`${API_BASE_URL}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, provider }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Generation failed");
    }
    return response.json();
  },
};
