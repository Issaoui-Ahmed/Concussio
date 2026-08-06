import type { NextConfig } from "next";

const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // Lets a second dev server run alongside an existing one: `next dev` takes a lock on
  // <distDir>/dev/lock, so a separate directory avoids "Unable to acquire lock".
  distDir: process.env.NEXT_DIST_DIR || ".next",
  experimental: {
    // Matches `maxDuration` in vercel.json. Below it, a slow /api/admin/pipeline/run would be
    // cut off by the dev proxy rather than by the function, so local behaviour would differ
    // from deployed for the one route where the difference is hardest to diagnose.
    proxyTimeout: 300000,
  },
  rewrites: async () => {
    if (process.env.NODE_ENV === "development") {
      return [
        {
          source: "/api/:path*",
          destination: `${apiBaseUrl}/api/:path*`,
        },
      ];
    }

    return [];
  },
};

export default nextConfig;
