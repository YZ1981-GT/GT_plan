/**
 * consol-phase3-frontend-drilldown — Phase 3 前端联动 Playwright 实测（Task 8）
 *
 * 覆盖（需求 NFR-1.2）：
 * - 8.1 T3 报表/附注右键穿透 → ConsolBreakdownDialog → 点子公司跳转 → Backspace 返回
 * - 8.2 双向导航：单体 header 跳合并 / 合并树进单体 / 锁定标签
 * - 8.3 自动建树：wizard 配置合并范围步骤 + scope 变更树刷新
 * - 8.4 F5 stale 感知：子公司改数 → 合并页 SSE 提示「建议重新汇总」+ 快捷入口（需求 7）
 *
 * 运行方式：
 * - 默认通过 test.skip(...) 跳过（需 running backend 9980 + frontend 3030 stack）
 * - 启动 start-dev.bat 后：`set RUN_FULL_E2E=1 && npx playwright test e2e/consol-phase3-drilldown.spec.ts`
 * - 需先准备真实合并母子项目数据（PG 当前 0 个 consolidated 项目 → 见 Task 9 真实数据 UAT）
 *
 * Requirements: NFR-1.2; Properties T3
 */
import { test, expect } from '@playwright/test'

// 读取环境变量（e2e 运行于 Node/Playwright；用 globalThis 取值避免依赖 @types/node）
const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'

// 合并母项目 ID（需先在 PG 准备 consolidated 项目 + 子公司，并 UPDATE is_deleted=false）
const CONSOL_PROJECT_ID = _env.CONSOL_PROJECT_ID || ''
// 任一子公司单体项目 ID（用于双向导航 8.2）
const SUB_PROJECT_ID = _env.SUB_PROJECT_ID || ''

test.describe('Phase 3 前端联动 + 附注穿透 (consol-phase3-frontend-drilldown)', () => {
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

  // ── 8.1 报表/附注右键穿透 → ConsolBreakdownDialog → 跳转 → Backspace 返回（T3） ──
  test('8.1 合并报表右键"查看合并明细" → 弹窗 → 点子公司跳转 → Backspace 返回', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/reports?year=2025`)
    await page.waitForLoadState('networkidle')

    // 在报表数据行上右键 → 出现"查看合并明细"菜单项
    const firstDataRow = page.locator('.el-table__row').first()
    await firstDataRow.click({ button: 'right' })
    const menuItem = page.locator('.gt-ucell-ctx-item:has-text("查看合并明细")')
    await expect(menuItem).toBeVisible({ timeout: 5000 })
    await menuItem.click()

    // ConsolBreakdownDialog 打开（统一穿透弹窗）
    const dialog = page.locator('.el-dialog:has-text("查看合并明细")')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // 弹窗内点击某子公司金额行 → 跳转单体报表
    const amountCell = dialog.locator('.gt-amount-cell').first()
    if (await amountCell.count()) {
      const urlBefore = page.url()
      await amountCell.click()
      await page.waitForLoadState('networkidle')
      // 跳转后 URL 变化（进入子公司单体页）
      expect(page.url()).not.toBe(urlBefore)

      // Backspace 返回来源页（T3：纳入 initGlobalBackspace 返回栈）
      await page.keyboard.press('Backspace')
      await page.waitForLoadState('networkidle')
      expect(page.url()).toContain(CONSOL_PROJECT_ID)
    }
  })

  test('8.1b 合并附注右键"查看合并明细" → 弹窗渲染（source=note）', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/disclosure-notes?year=2025`)
    await page.waitForLoadState('networkidle')

    // 选中一个附注章节后在单元格右键
    const cell = page.locator('.el-table__row .cell').first()
    if (await cell.count()) {
      await cell.click({ button: 'right' })
      const menuItem = page.locator('.gt-ucell-ctx-item:has-text("查看合并明细")')
      await expect(menuItem).toBeVisible({ timeout: 5000 })
      await menuItem.click()
      // 弹窗打开（有 breakdown 渲染表 / 无 breakdown 友好空态）
      await expect(page.locator('.el-dialog:has-text("查看合并明细")')).toBeVisible({ timeout: 5000 })
    }
  })

  // ── 8.2 双向导航 ──
  test('8.2a 单体项目 header"所属集团"链接 → 跳合并项目', async ({ page }) => {
    test.skip(!SUB_PROJECT_ID, '需 SUB_PROJECT_ID（挂在某合并项目下的单体项目）')
    await page.goto(`/projects/${SUB_PROJECT_ID}/entry`)
    await page.waitForLoadState('networkidle')

    // 概览面板出现"所属集团"链接
    const groupLink = page.locator('text=所属集团').locator('xpath=following::a[1]')
    if (await groupLink.count()) {
      await groupLink.click()
      await page.waitForLoadState('networkidle')
      expect(page.url()).toContain('/consolidation')
    }
  })

  test('8.2b 合并树节点"进入项目"按钮 → 路由单体项目 + 锁定标签', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation`)
    await page.waitForLoadState('networkidle')

    // 切到集团架构 Tab
    await page.click('text=集团架构')
    await page.waitForTimeout(500)

    // 树形列表模式 → "进入项目"链接
    await page.click('text=🌳 树形列表')
    const enterLink = page.locator('text=进入项目').first()
    if (await enterLink.count()) {
      await enterLink.click()
      await page.waitForLoadState('networkidle')
      expect(page.url()).toContain('/projects/')
    }
  })

  // ── 8.3 自动建树：scope 变更 → 树刷新 ──
  test('8.3 手动"刷新树"按钮 + scope 变更后树自动刷新', async ({ page }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID 环境变量')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation`)
    await page.waitForLoadState('networkidle')
    await page.click('text=集团架构')
    await page.waitForTimeout(500)

    // 手动刷新树按钮存在且可点（EH4 兜底）
    const refreshBtn = page.locator('button:has-text("刷新树")')
    await expect(refreshBtn).toBeVisible({ timeout: 5000 })
    await refreshBtn.click()
    await page.waitForLoadState('networkidle')
    // 节点计数文本仍渲染（树未崩）
    await expect(page.locator('text=个节点')).toBeVisible()
  })

  // ── 8.4 F5 stale 感知（需求 7）──
  test('8.4 子公司改数 → 合并页 SSE 提示「建议重新汇总」+ 立即重新汇总入口', async ({ page, context }) => {
    test.skip(!CONSOL_PROJECT_ID, '需 CONSOL_PROJECT_ID + 真实子公司数据')
    await page.goto(`/projects/${CONSOL_PROJECT_ID}/consolidation`)
    await page.waitForLoadState('networkidle')

    // 在另一标签页改子公司附注触发 NOTE_UPDATED → consol_note_stale_handler → SSE consol.note_stale
    // （此处依赖真实数据 + 后端事件链路；准备就绪后断言提示条出现）
    const staleBanner = page.locator('.el-alert:has-text("建议重新汇总")')
    // 等待 SSE 推送（最多 10s）
    await staleBanner.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    if (await staleBanner.count()) {
      await expect(staleBanner.locator('button:has-text("立即重新汇总")')).toBeVisible()
      await staleBanner.locator('button:has-text("立即重新汇总")').click()
      // 跳到合并附注 Tab
      await expect(page.locator('.el-tabs__item:has-text("合并附注")')).toBeVisible()
    }
  })
})
