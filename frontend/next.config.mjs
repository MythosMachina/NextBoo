const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/media/:path*",
        destination: "http://backend:8000/media/:path*"
      }
    ];
  }
};

export default nextConfig;
