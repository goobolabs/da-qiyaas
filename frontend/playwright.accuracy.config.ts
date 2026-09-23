import { defineConfig } from '@playwright/test';
process.env.NEXT_BUILD_DIR = '.next-accuracy';
export default defineConfig({
  testDir: './tests', workers: 1,
  use: { baseURL: 'http://127.0.0.1:3002', channel: 'msedge', headless: true, viewport: { width: 1440, height: 1100 } },
  webServer: { command: 'node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3002', url: 'http://127.0.0.1:3002', reuseExistingServer: false, timeout: 60000, gracefulShutdown: { signal: 'SIGTERM', timeout: 3000 } }
});
