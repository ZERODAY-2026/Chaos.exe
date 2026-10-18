import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Keep the dev-only indicator clear of the sidebar footer.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
