import type { NextConfig } from "next";
import path from "path";

const BACKEND = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  /**
   * Build output directory. Overridable so a second build (the demo-film
   * capture run, which needs its own backend origin) can live beside the one
   * `next dev` is using instead of overwriting it.
   */
  distDir: process.env.NEXT_DIST_DIR ?? ".next",

  /**
   * Proxy every /api/* request from the Next.js origin (localhost:3000) to the
   * FastAPI backend (127.0.0.1:8001).  This is *required* for cookie-based auth
   * to work in development: the browser's cookie jar is keyed by origin, so
   * Set-Cookie headers from 127.0.0.1:8001 are invisible to localhost:3000.  By
   * routing through Next.js the frontend and the backend share the same origin
   * and the session cookies are always present on incoming Next.js requests —
   * which means the proxy.ts route-guard can read them correctly.
   */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
