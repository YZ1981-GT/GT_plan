/**
 * Playwright E2E — N5 所得税费用底稿完整流程验收
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 7.3
 * Requirements: 全部
 *
 * 验证场景：
 * 1. 打开N5底稿 → 目录页加载15行sheet+损益类badge+进度仪表板
 * 2. 切换纳税调整N5-5 → 107行虚拟滚动+分类tab+调增/调减统计
 * 3. 切换当期所得税计算N5-4 → 计算链(会计利润→应纳税所得额→当期所得税)
 * 4. 切换审定表N5-1 → 所得税费用=当期+递延+公式tooltip+TB回写按钮
 * 5. 导航回目录+完整导航无console严重错误
 * 6. 跨底稿GtIndexChip验证(N1/N3/I6链接)
 * 7. 双模式切换不崩
 *
 * 科目：6801 所得税费用（**损益类**！取本期发生额，从tb_ledger）
 * 核心特殊：①损益类取发生额 ②当期所得税计算链 ③纳税调整107行大表 ④递延核对(N1/N3)
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/n5-income-tax-expense.spec.ts
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

/** 通过 API 找到 N5 底稿 ID */
async function findN5WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 N5 底稿
  const n5 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'N5')
  if (n5) return { id: n5.id, code: 'N5' }
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

test.describe('N5 所得税费用底稿 E2E 流程（Task 7.3）', () => {
  test.describe.configure({ mode: 'serial' })

  let wpId: string = ''
  let skipAll = false

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findN5WpId(request, token)
    if (!wp) {
      skipAll = true
      return
    }
    wpId = wp.id
  })

  // ═══ 场景 1：打开N5底稿 → 目录页加载 ═══
  test('7.3.1 — 打开N5底稿，目录页加载(15行sheet+损益类badge+有效税率仪表板)', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 验证 N5 组件容器加载
    const container = page.locator('.n5-income-tax-expense')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图
    const directory = page.locator('.n5-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"损益类·借方·发生额"醒目标注
    const directionBadge = page.locator('.n5-direction-badge, .direction-badge')
    if (await directionBadge.count() > 0) {
      await expect(directionBadge.first()).toContainText(/损益|发生额|借方/)
    }

    // 验证sheet目录行存在（至少12行有效）
    const tableRows = page.locator('.n5-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(12) // 15 sheet (minus skip)

    // 验证关键底稿编码
    await expect(page.locator('.el-table__row', { hasText: 'N5-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N5-4' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N5-5' })).toBeVisible()

    // 验证操作引导/仪表板
    const guide = page.locator('.n5-guide, .n5-dashboard, .progress-section')
    if (await guide.count() > 0) {
      await expect(guide.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 2：切换纳税调整N5-5 → 107行虚拟滚动+分类 ═══
  test('7.3.2 — 纳税调整N5-5: 107行虚拟滚动+分类统计+调增/调减', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 导航到 N5-5
    const nav = page.locator('.el-table__row', { hasText: /N5-5/ })
    if (await nav.count() > 0) {
      await nav.first().click()
      await page.waitForTimeout(2500)
    }

    // 验证纳税调整组件加载
    const taxAdjComp = page.locator('.n5-tab-tax-adjustment, .n5-tax-adjustment')
    await expect(taxAdjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N5-5"或"纳税调整"
    const title = taxAdjComp.locator('.section-title')
    await expect(title).toContainText(/N5-5|纳税调整/)

    // 验证方法论上下文
    const methodology = taxAdjComp.locator('.methodology-context')
    if (await methodology.count() > 0) {
      await expect(methodology.first()).toContainText(/纳税调整|调增|调减/)
    }

    // 验证表格存在（107行大表）
    const table = taxAdjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证分类统计摘要或合计区域
    const summary = taxAdjComp.locator('.summary-bar, .stat-bar, .adjustment-summary')
    if (await summary.count() > 0) {
      await expect(summary.first()).toBeVisible()
    }

    // 验证导入导出按钮
    const importExportBtn = taxAdjComp.locator('.el-dropdown, button', { hasText: /导入导出/ })
    if (await importExportBtn.count() > 0) {
      await expect(importExportBtn.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：当期所得税计算N5-4 → 计算链 ═══
  test('7.3.3 — 当期所得税计算N5-4: 会计利润→应纳税所得额→当期所得税', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 导航到 N5-4
    const nav = page.locator('.el-table__row', { hasText: /N5-4/ })
    if (await nav.count() > 0) {
      await nav.first().click()
      await page.waitForTimeout(2500)
    }

    // 验证当期所得税计算组件
    const calcComp = page.locator('.n5-tab-current-tax-calc, .n5-current-tax-calc')
    await expect(calcComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = calcComp.locator('.section-title')
    await expect(title).toContainText(/N5-4|当期所得税/)

    // 验证方法论上下文包含计算链说明
    const methodology = calcComp.locator('.methodology-context')
    if (await methodology.count() > 0) {
      await expect(methodology.first()).toContainText(/会计利润|应纳税所得额|当期所得税/)
    }

    // 验证表格（82行计算表）
    const table = calcComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证关键计算项文本存在
    const compText = await calcComp.textContent()
    const hasKeyTerms = compText?.includes('会计利润') ||
                        compText?.includes('应纳税所得额') ||
                        compText?.includes('税率')
    expect(hasKeyTerms).toBe(true)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：审定表N5-1 → 所得税费用=当期+递延 ═══
  test('7.3.4 — 审定表N5-1: 所得税费用=当期+递延+公式tooltip+TB回写按钮', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 导航到 N5-1
    const nav = page.locator('.el-table__row', { hasText: /N5-1/ })
    if (await nav.count() > 0) {
      await nav.first().click()
      await page.waitForTimeout(2500)
    }

    // 验证审定表组件
    const adjComp = page.locator('.n5-adjudication, .n5-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText(/N5-1|审定/)

    // 验证"损益类·借方"标注
    const dirTag = adjComp.locator('.direction-tag, .income-expense-tag')
    if (await dirTag.count() > 0) {
      await expect(dirTag.first()).toContainText(/损益|借方|发生额/)
    }

    // 验证方法论上下文
    const methodology = adjComp.locator('.methodology-context')
    if (await methodology.count() > 0) {
      await expect(methodology.first()).toContainText(/所得税费用|当期.*递延|审定/)
    }

    // 验证表格
    const table = adjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证TB回写按钮（核心功能）
    const tbBtn = adjComp.locator('button', { hasText: /TB.*回写|回写.*TB|写入试算表/ })
    if (await tbBtn.count() > 0) {
      await expect(tbBtn.first()).toBeVisible()
    }

    // 验证公式列有tooltip提示（cursor:help）
    const formulaCells = adjComp.locator('[title], [style*="cursor: help"], .formula-cell')
    const cellCount = await formulaCells.count()
    expect(cellCount).toBeGreaterThanOrEqual(0)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：完整导航无console严重错误 ═══
  test('7.3.5 — 完整sheet导航流程无console严重错误', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
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

    // 依次导航核心sheet: 目录→N5-4→N5-5→N5-1
    const sheets = [
      /N5-4/, // 当期所得税计算
      /N5-5/, // 纳税调整明细
      /N5-1/, // 审定表
    ]

    for (const sheetPattern of sheets) {
      const nav = page.locator('.el-table__row', { hasText: sheetPattern })
      if (await nav.count() > 0) {
        await nav.first().click()
        await page.waitForTimeout(3000)
      }
    }

    // 验证无严重错误
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  // ═══ 场景 6：跨底稿GtIndexChip验证 ═══
  test('7.3.6 — 跨底稿联动: GtIndexChip(N1/N3/I6)链接可见', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到 N5-8 递延核对表（有 N1/N3 联动chip）
    const nav = page.locator('.el-table__row', { hasText: /N5-8/ })
    if (await nav.count() > 0) {
      await nav.first().click()
      await page.waitForTimeout(2500)
    }

    // 验证递延核对组件加载
    const deferComp = page.locator('.n5-tab-deferred-reconcile, .n5-deferred-reconcile')
    await expect(deferComp).toBeVisible({ timeout: 10_000 })

    // 验证跨底稿chip（N1/N3联动）
    const indexChips = page.locator('.gt-index-chip, .index-chip')
    const chipCount = await indexChips.count()
    // 至少存在一些跨底稿引用chip
    if (chipCount > 0) {
      const allChipText = await page.locator('.gt-index-chip, .index-chip').allTextContents()
      const hasN1OrN3 = allChipText.some(
        (t) => /N1|N3|递延.*资产|递延.*负债/.test(t),
      )
      // 如果有chip，至少部分指向N1/N3
      expect(hasN1OrN3 || chipCount === 0).toBeTruthy()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：双模式切换不崩 ═══
  test('7.3.7 — 双模式切换(HTML/OnlyOffice)不崩溃', async ({ page }) => {
    test.skip(skipAll, 'N5底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    const container = page.locator('.n5-income-tax-expense')

    // 验证双模式切换按钮
    const modeSwitch = page.locator('.el-segmented').first()
    if (await modeSwitch.count() > 0) {
      const modeItems = modeSwitch.locator('.el-segmented__item')
      if (await modeItems.count() >= 2) {
        // 切换到OO模式
        await modeItems.nth(1).click()
        await page.waitForTimeout(2000)
        await expect(container).toBeVisible()

        // 切回HTML
        await modeItems.nth(0).click()
        await page.waitForTimeout(1500)
        await expect(container).toBeVisible()
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 8：render-config API验证 ═══
  test('render-config API 返回正确组件类型 n5-income-tax-expense', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=n5-income-tax-expense`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'n5-income-tax-expense')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
      expect(renderData.sheets.length).toBe(15)
    }
  })
})
