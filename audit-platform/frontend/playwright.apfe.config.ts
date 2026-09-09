import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'attachment-preview-format-expansion.spec.ts',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:3031',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium-apfe',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npx vite --mode apfe-e2e --port 3031 --strictPort',
    url: 'http://localhost:3031',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
