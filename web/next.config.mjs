/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The embed viewer page is intended to be loaded inside third-party <iframe>s.
  // We don't set X-Frame-Options here; if you add a CSP later, scope it to /embed.
  experimental: {
    // gaussian-splats-3d is an ESM-only package — Next 14 handles this fine,
    // but we explicitly transpile in case of nested CJS interop quirks.
  },
  transpilePackages: ['@mkkellogg/gaussian-splats-3d'],
};
export default nextConfig;
