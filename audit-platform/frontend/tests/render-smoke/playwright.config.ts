/**
 * Playwright config — render 冒烟测试集
 *
 * 独立 CI job `render-smoke`，数据驱动按 wp_code 参数化。
 * 先以 continue-on-error 灰度，全量迁移后转 blocking。
 *
 * Feature: platform-global-hardening
 * Requirements: 3.5, 3.6
 */
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  fullyParallel: false, // 顺序执行避免竞态
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // 单 worker，底稿渲染串行
  reporter: [
    ['list'],
    ['html', { outputFolder: '../../playwright-report/render-smoke' }],
  ],
  use: {
    baseURL: process.env.RENDER_SMOKE_BASE_URL || 'http://localhost:3030',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'render-smoke',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // 不启动 webServer — CI 中由外部脚本或 docker 管理前后端服务
})
