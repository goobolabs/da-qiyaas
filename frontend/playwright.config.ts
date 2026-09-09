import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:3000', channel: 'msedge', headless: true, viewport: { width: 1440, height: 1100 } },
  webServer: { command: 'node node_modules/next/dist/bin/next start --hostname 127.0.0.1', url: 'http://127.0.0.1:3000', reuseExistingServer: !process.env.CI, timeout: 60000, gracefulShutdown: { signal: 'SIGTERM', timeout: 3000 } },
});
