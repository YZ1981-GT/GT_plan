import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    // Vite 显式监听 0.0.0.0；测试和 webServer 探活统一走 IPv4 loopback。
    // 不能混用 localhost/127.0.0.1，否则 IPv6 loopback 异常时会出现假就绪或拒连。
    baseURL: 'http://127.0.0.1:3030',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3030',
    reuseExistingServer: !process.env.CI,
  },
})
