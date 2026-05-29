/**
 * V3 Req 5.3 — 年度切换响应 Playwright e2e（最小骨架）
 *
 * 形式化：∀ view V depending on year, ∀ year change Y → Y':
 *   Y → Y' triggers V.refetch() within 1s
 *
 * 当前覆盖范围（最小版）：
 * - 验证 7 核心视图通过 ?year=YYYY 切换路由查询参数后，前端发起新 API 请求
 *
 * 完整版（计划在 6000 并发压测窗口配套搭建）：
 * - 真实 PG 测试库 + admin/admin123 + 多年度数据
 * - 切换顶栏年度选择器，断言 7 视图的关键 KPI 数字变化
 *
 * 跳过策略：
 * - 默认通过 test.skip(...) 跳过（needs running backend + frontend stack）
 * - 启动 start-dev.bat 后用 `npx playwright test e2e/year-switching.spec.ts --grep year-switch`
 *
 * @see audit-platform/frontend/src/__tests__/property-year-switching-invariant.spec.ts
 *      （vitest + fast-check PBT 替代覆盖，已通过）
 * @see audit-platform/frontend/src/composables/__tests__/audit-context-7-views.test.ts
 *      （7 视图静态扫描守门，已通过）
 */
import { test, expect } from '@playwright/test'

// 7 个核心视图路径（与 5.1 任务接入清单一致）
const SEVEN_VIEW_PATHS = [
  { name: 'Adjustments', path: 'adjustments' },
  { name: 'Misstatements', path: 'misstatements' },
  { name: 'ReportView', path: 'reports' },
  { name: 'DisclosureEditor', path: 'disclosure-editor' },
  { name: 'WorkpaperList', path: 'workpapers' },
  { name: 'TrialBalance', path: 'trial-balance' },
  { name: 'LedgerPenetration', path: 'ledger-penetration' },
] as const

// 仅在显式设置 RUN_FULL_E2E=1 时运行（默认跳过，避免无后端环境时 CI 失败）
const RUN_FULL_E2E = process.env.RUN_FULL_E2E === '1'

test.describe('年度切换响应 (Req 5.3)', () => {
  test.skip(!RUN_FULL_E2E, '完整 E2E 需 RUN_FULL_E2E=1 + 后端 9980 + 前端 3030 + 测试项目数据')

  test.beforeEach(async ({ page }) => {
    // 登录测试用户
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/)
  })

  for (const view of SEVEN_VIEW_PATHS) {
    test(`${view.name} 切换 year 后触发新 API 请求`, async ({ page }) => {
      // 注意：projectId 由测试 fixture 提供（待 6000 并发压测窗口确定）
      const projectId = process.env.E2E_PROJECT_ID ?? 'test-project-id'
      const url = `/projects/${projectId}/${view.path}?year=2024`

      const apiCalls: string[] = []
      page.on('request', (req) => {
        const u = req.url()
        if (u.includes('/api/') && (u.includes('year=') || req.method() !== 'GET')) {
          apiCalls.push(u)
        }
      })

      await page.goto(url)
      await page.waitForLoadState('networkidle')
      const callsAtYear2024 = apiCalls.length

      // 切换 year 到 2023
      await page.goto(`/projects/${projectId}/${view.path}?year=2023`)
      await page.waitForLoadState('networkidle')

      // 不变量：切换 year 后必有新的 API 请求被发出
      expect(apiCalls.length).toBeGreaterThan(callsAtYear2024)
      const newCalls = apiCalls.slice(callsAtYear2024)
      // 新请求中至少一个 URL 含 year=2023
      expect(newCalls.some((u) => u.includes('year=2023'))).toBe(true)
    })
  }
})
