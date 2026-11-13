/**
 * 公式链路 E2E 专用 Playwright 配置 — formula-e2e-ci-gate ADR-FEC-01/02/04。
 *
 * 与主 playwright.config.ts 的区别：
 * - testDir 只含 formula-hub 目录
 * - globalSetup 失败即终止（不告警继续）
 * - 无「环境不就绪即 skip」— 环境缺失必须让 job 失败（ADR-FEC-04）
 *
 * 本地运行：
 *   npx playwright test --config=playwright.formula-e2e.config.ts
 *   会写公式数据的用例只在一次性库上跑（helpers.requireIsolatedDb）：本地另起一套指向一次性库的后端 / 前端，
 *   用 PLAYWRIGHT_BACKEND_URL / PLAYWRIGHT_BASE_URL 指过去，不要对着共享开发服务（9980 / 3030）跑
 *
 * CI 运行：
 *   由 .github/workflows/formula-e2e.yml 调用
 */
import { defineConfig, devices } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3030'

export default defineConfig({
  testDir: './e2e/formula-hub',
  globalSetup: './e2e/formula-hub/global-setup.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // 规格间可能写同一项目数据，串行防污染
  timeout: 60_000, // 共享库后端偶尔响应慢，CI 一次性库上会更快
  reporter: process.env.CI ? [['github'], ['list']] : 'html',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000, // CI 首次编译可能较慢
  },
})
