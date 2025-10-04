/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const target = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    // Proxy backend routes so local dev & tests avoid CORS preflight issues.
    return [
      {
        source: "/backend/:path*",
        destination: `${target}/:path*`
      }
    ];
  }
};

export default nextConfig;
