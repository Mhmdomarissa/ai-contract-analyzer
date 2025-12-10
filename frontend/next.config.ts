import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lucide-react"],
    serverActions: {
      allowedOrigins: [],
    },
  },
};

export default nextConfig;
