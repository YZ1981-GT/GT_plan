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
    // 🔴 必须用 `localhost` 而不是 `127.0.0.1`：**Vite 只监听 IPv6**
    //（实测 `netstat` 只有 `TCP [::1]:3030 LISTENING`，无任何 IPv4 监听项）。
    //
    // 这个结论本仓早有记录 —— `scripts/check_vite_transform.mjs` 文件头就写着
    //「Vite 只监听 IPv6，故用 localhost 而非 127.0.0.1（实测 127.0.0.1:3030 会
    //『连接被拒绝』，极易误判成服务没起）」—— 只是本文件一直没对齐。
    //
    // 后果是**本机任何 e2e 都跑不起来**，而且极难归因：下面 `webServer.url` 用的是
    // `localhost`，所以 Playwright 的服务探活**能过**，随后所有相对
    // `page.goto('/...')` 走 `baseURL` 却 `ECONNREFUSED 127.0.0.1:3030` ——
    // 看起来像「服务起着但页面打不开」。同文件两处 host 不一致正是这个坑的来源，
    // 故判据是「两处 host 必须一致」（见 test_playwright_base_url_matches_dev_server.py）。
    baseURL: 'http://localhost:3030',
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
    url: 'http://localhost:3030',
    reuseExistingServer: !process.env.CI,
  },
})
