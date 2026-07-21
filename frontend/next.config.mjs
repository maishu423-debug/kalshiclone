const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "https://secondclone-67mh.onrender.com";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
