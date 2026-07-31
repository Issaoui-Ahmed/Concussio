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
    proxyTimeout: 120000,
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
