import { defineConfig, devices } from '@playwright/test'

/**
 * 只读 UAT 专用配置（spec trim-generation-plan-followup-optimizations R5.4）。
 *
 * - 只跑 e2e-readonly/：防火墙变异测试（不连任何真实服务）+ 真实项目只读走查（只认显式环境变量，缺一即跳过）；
 * - 没有 globalSetup / webServer / 播种：不起服务、不写数据；
 * - trace / screenshot / video 全关，避免真实项目内容落盘；workers=1、retries=0（重试会掩盖偶发写入）；
 * - 每个用例自己用 newGuardedContext 建独立 context（禁用 Service Worker、建 page 前装好防火墙）。
 *
 * 运行：node node_modules/@playwright/test/cli.js test --config=playwright.readonly-uat.config.ts
 */
export default defineConfig({
  testDir: './e2e-readonly',
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [['list']],
  outputDir: './test-results/readonly-uat',
  use: {
    baseURL: process.env.GT_READONLY_UAT_BASE_URL || 'http://127.0.0.1:3030',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], serviceWorkers: 'block' },
    },
  ],
})
