import type { NextConfig } from "next";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  eslint: { ignoreDuringBuilds: true },
  images: {
    // TMDB already serves pre-sized renditions from its CDN; the custom loader maps
    // requested widths onto those sizes (no image-optimisation bill, fast LCP).
    loader: "custom",
    loaderFile: "./lib/image-loader.ts",
  },
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"],
  },
  // Proxy the API through the frontend origin so auth cookies stay first-party.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_INTERNAL_URL}/api/v1/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
