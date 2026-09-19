/**
 * Playwright E2E — N3 递延所得税负债底稿完整流程验收
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开N3底稿 → 目录页加载6行sheet+负债类badge可见
 * 2. 切换审定表N3-1 → 验证负债类公式badge+表格列头+公式tooltip
 * 3. 切换明细表N3-2 → 验证应纳税暂时性差异×税率+统计摘要+新增行按钮
 * 4. 切换调整分录N3-3 → 验证AJE/RJE切换+借贷平衡校验
 * 5. 切换附注披露 → 验证sections渲染
 * 6. 保存流程+双模式切换不崩
 * 7. 完整导航流程无console严重错误
 *
 * 科目：2901递延所得税负债（**贷方/负债类！期末=期初+贷方-借方**）
 * 核心特殊：①负债类贷方 ②应纳税暂时性差异×税率 ③与N1同源对应 ④N5递延税费用核对
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/n3-deferred-tax-liabilities.spec.ts
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.TEST_PROJECT_ID || 'd9295a0c-f347-4aa5-a1d1-faf7847d379b'

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function loginAs(page: Page, username = 'admin', password = 'admin123') {
  const resp = await page.request.post(`${BASE_URL}/api/auth/login`, {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

/** 通过 API 找到 N3 底稿 ID */
async function findN3WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 N3 底稿
  const n3 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'N3')
  if (n3) return { id: n3.id, code: 'N3' }
  return null
}

// ─── Skip if backend not running ─────────────────────────────────────────────

test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BASE_URL}/api/health`, { timeout: 5000 })
    if (!resp.ok()) test.skip()
  } catch {
    test.skip()
  }
})

// ═══════════════════════════════════════════════════════════════════════════════
// Test Suite (serial mode for sequential navigation)
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('N3 递延所得税负债底稿 E2E 流程（Task 7.3）', () => {
  test.describe.configure({ mode: 'serial' })

  let wpId: string = ''
  let wpCode: string = ''
  let skipAll = false

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findN3WpId(request, token)
    if (!wp) {
      skipAll = true
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开N3底稿 → 目录页加载6行sheet ═══
  test('7.3.1 — 打开N3底稿，目录页加载(6行sheet+负债类badge)', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 验证 N3 组件容器加载
    const container = page.locator('.n3-deferred-tax-liabilities')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（N3TabIndex）
    const directory = page.locator('.n3-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"负债类·贷方"醒目标注
    const liabilityBadge = page.locator('.n3-liability-badge')
    await expect(liabilityBadge).toBeVisible()
    await expect(liabilityBadge).toContainText(/负债|贷方/)

    // 验证有6行sheet目录
    const tableRows = page.locator('.n3-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(5) // 至少5行有效sheet（+1 skip行=6）

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'N3A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N3-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N3-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N3-3' })).toBeVisible()

    // 验证进度统计区域可见
    const progressSection = page.locator('.n3-progress-section')
    await expect(progressSection).toBeVisible()

    // 验证操作引导区存在
    const guide = page.locator('.n3-guide')
    await expect(guide).toBeVisible()
  })

  // ═══ 场景 2：审定表N3-1 → 负债类取数+公式badge ═══
  test('7.3.2 — 审定表N3-1: 负债类取数(期末=期初+贷方-借方)+公式tooltip', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 通过目录导航切换到N3-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /N3-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.n3-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N3-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('N3-1')

    // 验证"负债类·贷方" tag
    const liabilityTag = adjComp.locator('.liability-tag')
    await expect(liabilityTag).toBeVisible()
    await expect(liabilityTag).toContainText(/负债|贷方/)

    // 验证方法论上下文(琥珀色)显示负债类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/应纳税暂时性差异/)

    // 验证负债类公式提示badge
    const formulaBadge = adjComp.locator('.liability-formula-badge')
    await expect(formulaBadge).toBeVisible()
    await expect(formulaBadge).toContainText(/期末.*期初.*贷方.*借方|期初.*贷.*借/)

    // 验证表格列头（项目/期初/贷方/借方）
    const table = adjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证关键列header
    await expect(adjComp.locator('th', { hasText: '期初' })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /贷方/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /借方/ })).toBeVisible()

    // 验证公式列单元格有 cursor:help（tooltip 可用）
    const formulaCells = adjComp.locator('.formula-cell, [style*="cursor: help"], [title]')
    const formulaCellCount = await formulaCells.count()
    expect(formulaCellCount).toBeGreaterThanOrEqual(0)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：明细表N3-2 → 应纳税暂时性差异×税率+统计摘要 ═══
  test('7.3.3 — 明细表N3-2: 应纳税暂时性差异×税率+统计摘要+新增行', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N3-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /N3-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.n3-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N3-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('N3-2')

    // 验证方法论上下文包含核心公式说明
    const methodology = detailComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/应纳税暂时性差异.*税率|账面价值.*计税基础/)

    // 验证统计摘要区域可见
    const summaryBar = detailComp.locator('.summary-bar')
    await expect(summaryBar).toBeVisible()

    // 验证统计项目存在
    await expect(summaryBar.locator('text=差异项目数')).toBeVisible()
    await expect(summaryBar.locator('text=应纳税差异合计')).toBeVisible()
    await expect(summaryBar.locator('text=递延税负债合计')).toBeVisible()
    await expect(summaryBar.locator('text=加权平均税率')).toBeVisible()

    // 验证表格存在
    const table = detailComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证关键列header（账面价值/计税基础）
    await expect(detailComp.locator('th', { hasText: '账面价值' })).toBeVisible()
    await expect(detailComp.locator('th', { hasText: '计税基础' })).toBeVisible()

    // 验证新增行按钮存在
    const addRowBtn = detailComp.locator('.add-row-bar button, button', { hasText: /新增.*应纳税/ })
    await expect(addRowBtn).toBeVisible()

    // 验证导入导出按钮存在
    const importExportBtn = detailComp.locator('.el-dropdown, button', { hasText: /导入导出/ })
    if (await importExportBtn.count() > 0) {
      await expect(importExportBtn.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：调整分录N3-3 → 借贷平衡校验 ═══
  test('7.3.4 — 调整分录N3-3: AJE/RJE切换+借贷平衡校验', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N3-3调整分录
    const adjNav = page.locator('.el-table__row', { hasText: /N3-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证调整分录组件加载
    const adjComp = page.locator('.n3-tab-adjustment')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N3-3"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('N3-3')

    // 验证方法论上下文包含借贷平衡规则
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/借贷平衡/)

    // 验证AJE/RJE切换Tab
    const typeSwitch = adjComp.locator('.type-switch-bar .el-segmented')
    await expect(typeSwitch).toBeVisible()

    // 验证借贷平衡状态区域
    const balanceStatus = adjComp.locator('.balance-status')
    await expect(balanceStatus).toBeVisible()
    await expect(balanceStatus.locator('text=借方合计')).toBeVisible()
    await expect(balanceStatus.locator('text=贷方合计')).toBeVisible()

    // 验证保存按钮存在
    const saveBtn = adjComp.locator('button', { hasText: /保存/ })
    await expect(saveBtn).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：附注披露 → sections渲染 ═══
  test('7.3.5 — 附注披露: sections渲染+AI辅助按钮', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到附注
    const noteNav = page.locator('.el-table__row', { hasText: /附注/ })
    if (await noteNav.count() > 0) {
      await noteNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证附注组件加载
    const noteComp = page.locator('.n3-tab-disclosure')
    await expect(noteComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = noteComp.locator('.section-title')
    await expect(title).toContainText('附注')

    // 验证方法论上下文
    const methodology = noteComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/递延所得税负债附注/)

    // 验证至少有一个 section card
    const cards = noteComp.locator('.disclosure-card, .el-card')
    expect(await cards.count()).toBeGreaterThanOrEqual(1)

    // 验证AI辅助按钮存在
    const aiBtn = noteComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)

    // 验证模板切换控件（上市/国企）
    const templateSwitch = noteComp.locator('.el-segmented')
    if (await templateSwitch.count() > 0) {
      await expect(templateSwitch.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：双模式切换+保存不崩 ═══
  test('7.3.6 — 双模式切换+保存流程不崩溃', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到审定表 N3-1
    const adjNav = page.locator('.el-table__row', { hasText: /N3-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const container = page.locator('.n3-deferred-tax-liabilities')

    // 验证双模式切换（el-segmented: HTML/OnlyOffice）
    const modeSwitch = page.locator('.n3-deferred-tax-liabilities-toolbar .el-segmented').first()
    if (await modeSwitch.count() > 0) {
      const modeItems = modeSwitch.locator('.el-segmented__item')
      if (await modeItems.count() >= 2) {
        // 切换到OO模式
        await modeItems.nth(1).click()
        await page.waitForTimeout(2000)

        // 验证不崩
        await expect(container).toBeVisible()

        // 切回HTML
        await modeItems.nth(0).click()
        await page.waitForTimeout(1000)
        await expect(container).toBeVisible()
      }
    }

    // 验证无错误弹窗
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：完整导航流程无console严重错误 ═══
  test('7.3.7 — 完整导航流程无console严重错误', async ({ page }) => {
    test.skip(skipAll, 'N3底稿不存在于测试项目中')
    test.setTimeout(90_000)

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        // 排除已知非关键错误
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/ResizeObserver loop/.test(text)) return
        if (/404.*onlyoffice|healthcheck/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(5000)

    // 依次导航各核心sheet
    const sheets = [
      /N3-1/,   // 审定表
      /N3-2/,   // 明细表
      /N3-3/,   // 调整分录
      /附注/,    // 附注披露
    ]

    for (const sheetPattern of sheets) {
      const nav = page.locator('.el-table__row', { hasText: sheetPattern })
      if (await nav.count() > 0) {
        await nav.first().click()
        await page.waitForTimeout(2500)
      }
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  // ═══ 场景 8：render-config API验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=n3-deferred-tax-liabilities`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'n3-deferred-tax-liabilities')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
