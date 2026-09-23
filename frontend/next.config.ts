import type { NextConfig } from 'next';
const config: NextConfig = {
  distDir: process.env.NEXT_BUILD_DIR || '.next',
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:5000'}/api/:path*` }];
  },
};
export default config;
