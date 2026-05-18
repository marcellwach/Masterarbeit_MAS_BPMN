/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config) => {
    // bpmn-js uses ES modules and requires proper handling
    config.resolve.fallback = { fs: false, path: false };
    return config;
  },
};

export default nextConfig;
