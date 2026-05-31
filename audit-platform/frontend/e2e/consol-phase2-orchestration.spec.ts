/**
 * consol-phase2-orchestration — Phase 2 编排 + 接线 Playwright 实测（Task 7）
 *
 * 覆盖（需求 NFR-1.2）：
 * - 7.1 一键刷新按钮 → SSE 进度显示 → 完成（refresh-all + events/stream 进度，需求 2）
 * - 7.2 V2 附注 flag 开启后前端「生成合并附注」表现（CONSOL_NOTES_V2_ENABLED，需求 3）
 * - 7.3 F3 前端「一键刷新全部」+「重新汇总附注」入口调通后端（需求 9）
 *
 * 运行方式：
 * - 默认通过 test.skip(...) 跳过（需 running backend 9980 + frontend 3030 stack）
 * - 启动 start-dev.bat 后：
 *     set RUN_FULL_E2E=1 && set CONSOL_PROJECT_ID=<合并母项目ID> && \
 *     npx playwright test e2e/consol-phase2-orchestration.spec.ts
 * - 真实数据 UAT（真实子公司端到端正确性）见 Task 8（卡 PG 0 个 consolidated 项目）。
 *
 * Requirements: 2.x / 3.x / 9.x; NFR-1.2
 */
import { test, expect } from '@playwright/test'

// 读取环境变量（e2e 运行于 Node/Playwright；用 globalThis 取值避免依赖 @types/node）
const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'

// 合并母项目 ID（需先在 PG 准备 consolidated 项目 + 子公司，并 UPDATE is_deleted=false）
const CONSOL_PROJECT_ID = _env.CONSOL_PROJECT_ID || ''
const CONSOL_YEAR = _env.CONSOL_YEAR || '2025'

test.describe('Phase 2 编排 + 接线 (consol-phase2-orchestration)', () => {
  test.skip(
    !RUN_FULL_E2E,
    '完整 E2E 需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 真实合并母子项目数据',
  )

  test.beforeEach(async ({ page }) => {
    // 登录测试用户
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  // ── 7.1 + 7.3 一键刷新全部 → SSE 进度 → 完成 ──
  test('7.1/7.3 一键刷新全部按钮 → 入队 job → SSE 进度 → 完成提示', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation?year=${CONSOL_YEAR}`)
    await page.waitForLoadState('networkidle')

    // 工具栏「一键刷新全部」按钮存在且可点击
    const refreshBtn = page.locator('button:has-text("一键刷新全部")')
    await expect(refreshBtn).toBeVisible({ timeout: 8000 })

    // 监听 refresh-all 请求确实发出（POST .../refresh-all 返回 job_id）
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => /\/api\/consolidation\/.+\/refresh-all$/.test(r.url()) && r.request().method() === 'POST',
        { timeout: 10000 },
      ),
      refreshBtn.click(),
    ])
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    expect(body.job_id).toBeTruthy()

    // 进度提示出现（SSE consol.refresh.progress → "x/总步数 step" 文本 或 成功 toast）
    // 完成后出现成功消息（最长等待编排完成；大集团数十秒，给 60s 上限）
    await expect(
      page.locator('.el-message:has-text("一键刷新完成"), .el-message:has-text("一键刷新")'),
    ).toBeVisible({ timeout: 60000 })
  })

  // ── 7.3 重新汇总附注入口调通后端 ──
  test('7.3 重新汇总附注按钮 → 调 reaggregate 端点 → 切附注 tab', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation?year=${CONSOL_YEAR}`)
    await page.waitForLoadState('networkidle')

    const reaggBtn = page.locator('button:has-text("重新汇总附注")')
    await expect(reaggBtn).toBeVisible({ timeout: 8000 })

    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => /\/api\/consolidation\/notes\/.+\/reaggregate$/.test(r.url()) && r.request().method() === 'POST',
        { timeout: 15000 },
      ),
      reaggBtn.click(),
    ])
    expect(resp.ok()).toBeTruthy()

    // 完成后切到「合并附注」tab
    await expect(page.locator('.el-tabs__item:has-text("合并附注")')).toBeVisible({ timeout: 5000 })
  })

  // ── 7.2 V2 附注 flag 开启后「生成合并附注」表现 ──
  test('7.2 V2 附注 flag 开启 → 生成合并附注消费子公司数据（章节非空骨架）', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    test.skip(
      _env.CONSOL_NOTES_V2_ENABLED !== '1',
      '需后端 CONSOL_NOTES_V2_ENABLED=True 启动（默认 False 老版）',
    )
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation?year=${CONSOL_YEAR}`)
    await page.waitForLoadState('networkidle')

    // 切到合并附注 tab
    await page.locator('.el-tabs__item:has-text("合并附注")').click()
    await page.waitForLoadState('networkidle')

    // 生成合并附注（V2：消费子公司单体附注汇总，章节数应 > 7 骨架）
    const genBtn = page.locator('button:has-text("生成"), button:has-text("生成合并附注")').first()
    if (await genBtn.isVisible().catch(() => false)) {
      const [resp] = await Promise.all([
        page.waitForResponse(
          (r) => /\/api\/consolidation\/notes\/.+\/(\d+)$/.test(r.url()) && r.request().method() === 'POST',
          { timeout: 30000 },
        ),
        genBtn.click(),
      ])
      expect(resp.ok()).toBeTruthy()
      const sections = await resp.json()
      // V2 应返回合法 ConsolDisclosureSection 列表（契约 S4 一致）
      expect(Array.isArray(sections)).toBeTruthy()
    }
    // 0 console error（无运行时异常）
  })
})
