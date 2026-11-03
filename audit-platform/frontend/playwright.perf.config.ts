import { defineConfig, devices } from '@playwright/test'

/**
 * 生成计划弹窗性能裁决专用配置（spec trim-generation-plan-followup-optimizations R6）。
 *
 * - 只跑 e2e/generation-plan-dialog-perf.spec.ts；没有 globalSetup（主配置的 globalSetup 会往共享库播种）；
 * - workers=1、retries=0（并发会抢 CPU、重试会掩盖超门）；trace / screenshot / video 关闭；
 * - 复用已在跑的 Vite 开发服务（默认 http://127.0.0.1:3030，GT_PERF_BASE_URL 可改），不另起服务。
 *
 * 运行：node node_modules/@playwright/test/cli.js test --config=playwright.perf.config.ts
 *       （GT_PERF_STRESS=1 加跑 250 / 500 / 1025 档；GT_PERF_ROUND=1 / 2 给结果文件命名）
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /generation-plan-dialog-perf\.spec\.ts$/,
  fullyParallel: false,
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 10 * 60_000,
  reporter: [['list']],
  outputDir: './test-results/perf-artifacts',
  use: {
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
