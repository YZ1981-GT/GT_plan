import { defineConfig, devices } from '@playwright/test'

/**
 * Sprint C.3.16 / C.0.23 / C.6.1 UAT 配置.
 * 
 * 运行：
 *   npx playwright test --config=playwright-uat.config.ts
 */
export default defineConfig({
  testDir: './e2e-uat',
  timeout: 60_000,
  fullyParallel: false,  // UAT 顺序执行，避免并发干扰
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-uat-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://localhost:3030',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 10_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
