import type { NextConfig } from "next";

const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.NODE_ENV === "development"
            ? `${apiBaseUrl}/api/:path*`
            : "/api/",
      },
    ];
  },
};

export default nextConfig;
