import { defineConfig, devices } from '@playwright/test'

// Intentionally isolated: no real login, shared storage, or server startup.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'consol-note-runtime.synthetic.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:3030',
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium-synthetic', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile-synthetic', use: { ...devices['Pixel 7'] } },
  ],
})
