import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Output standalone build for optimized Docker/Vercel deployment
  output: "standalone",

  // Enable React strict mode for better development experience
  reactStrictMode: true,

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Configure allowed image domains (if using next/image with external sources)
  images: {
    remotePatterns: [
      // Add external image domains here if needed
      // { protocol: 'https', hostname: 'example.com' },
    ],
  },

  // Environment variable validation at build time
  env: {
    // These are validated at build time
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  },
};

export default nextConfig;

