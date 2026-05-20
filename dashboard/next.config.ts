import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Fix for HMR cross-origin issues */
  devIndicators: {
    appIsrStatus: false,
  },
  experimental: {
    allowedDevOrigins: ["127.0.0.1", "localhost:3000", "localhost:3001"],
  },
};

export default nextConfig;
