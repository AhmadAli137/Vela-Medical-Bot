import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  reporter: [['list'], ['html', {open: 'never'}]],
  use: {
    baseURL: process.env.VELA_WEB_URL || 'http://127.0.0.1:5173',
    ...devices['Desktop Chrome'],
    channel: 'chrome',
    viewport: {width: 1440, height: 1050},
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
