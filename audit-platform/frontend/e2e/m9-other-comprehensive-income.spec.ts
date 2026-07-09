/**
 * Playwright E2E — M9 其他综合收益底稿完整流程验收
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 M9 底稿 → sheetName 分发 → 底稿目录渲染7行sheet
 * 2. 切换审定表 M9-1 → 验证双区块(不可重分类/可重分类) + 权益类列
 * 3. 输入期初/贷方/借方→验证期末公式列(期初+贷方-借方)自动更新
 * 4. 切换明细表 M9-2 → 验证区段Tab(不可重分类/可重分类/税额)
 * 5. 切换OCI核对表 M9-4 → 验证多来源核对rows + 核对差异公式列
 * 6. 保存流程 → 无错误
 *
 * 科目：4103其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方（OCI增加贷方，减少/重分类借方）
 *           ②双大类：不能重分类(G8/J2) + 能重分类(债权/套期/外币)
 *           ③OCI核对多来源 ④税后净额列示
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m9-other-comprehensive-income.spec.ts
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.TEST_PROJECT_ID || '37814426-a29e-4fc2-9313-a59d229bf7b0'

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

/** 通过 API 找到 M9 底稿 ID */
async function findM9WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M9 底稿
  const m9 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M9')
  if (m9) return { id: m9.id, code: 'M9' }
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
// Test Suite
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('M9 其他综合收益底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM9WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M9 底稿 → 底稿目录渲染7行sheet ═══
  test('7.3.1 — 打开 M9 底稿，底稿目录渲染7行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 验证 M9 组件容器加载
    const container = page.locator('.m9-other-comprehensive-income')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M9TabIndex）
    const directory = page.locator('.m9-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m9-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m9-guide')
    await expect(guide).toBeVisible()

    // 验证有7行sheet目录（M9A+M9-1+M9-2+M9-3+M9-4+附注上市+附注国企）
    const tableRows = page.locator('.m9-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(7)

    // 验证关键底稿编码存在
    await expect(page.locator('.el-table__row', { hasText: 'M9A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M9-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M9-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M9-3' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M9-4' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M9-1 → 双区块(不可/可重分类) + 权益类列 ═══
  test('7.3.2 — 审定表M9-1: 双区块(不可/可重分类) + 权益类列可见', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M9-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M9-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m9-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M9-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M9-1')

    // 验证"权益类·贷方余额" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('贷方余额')

    // 验证双区块标题：不可重分类 + 可重分类
    const nonReclassBlock = adjComp.locator('.block-title', { hasText: /不能重分类|不可重分类/ })
    await expect(nonReclassBlock.first()).toBeVisible()

    const reclassBlock = adjComp.locator('.block-title', { hasText: /能重分类|可重分类/ })
    await expect(reclassBlock.first()).toBeVisible()

    // 验证表格列头包含权益类关键列
    await expect(adjComp.locator('th', { hasText: /期初/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /贷方/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /借方/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /期末/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /审定/ })).toBeVisible()

    // 验证方法论上下文(琥珀色)显示权益类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('期末')

    // 验证公式列header有tooltip
    const formulaHeaders = adjComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：审定表输入数据 → 验证期末公式列自动更新 ═══
  test('7.3.3 — 审定表M9-1: 输入期初/贷方/借方，期末公式列自动更新', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 切换到M9-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M9-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m9-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 找到第一个数据行的输入框（期初/贷方/借方）
    const firstRow = adjComp.locator('.el-table__row').first()
    const inputNumbers = firstRow.locator('.el-input-number input')

    // 如果有输入框，尝试输入测试数据
    if (await inputNumbers.count() >= 3) {
      // 期初 = 1000
      await inputNumbers.nth(0).click()
      await inputNumbers.nth(0).fill('1000')
      await inputNumbers.nth(0).press('Tab')
      await page.waitForTimeout(500)

      // 贷方发生(OCI增加) = 500
      await inputNumbers.nth(1).click()
      await inputNumbers.nth(1).fill('500')
      await inputNumbers.nth(1).press('Tab')
      await page.waitForTimeout(500)

      // 借方发生(减少) = 200
      await inputNumbers.nth(2).click()
      await inputNumbers.nth(2).fill('200')
      await inputNumbers.nth(2).press('Tab')
      await page.waitForTimeout(500)

      // 验证期末公式列显示 = 1000 + 500 - 200 = 1300
      const formulaValues = firstRow.locator('.formula-value')
      if (await formulaValues.count() > 0) {
        const endBalanceText = await formulaValues.first().textContent()
        // 期末应该是 1300 (1000+500-200)
        expect(endBalanceText).toContain('1,300')
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：明细表 M9-2 → 区段Tab(不可重分类/可重分类/税额) ═══
  test('7.3.4 — 明细表M9-2: 区段Tab(不可重分类/可重分类/税额) + 税后净额', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 切换到M9-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M9-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m9-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M9-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M9-2')

    // 验证3区段Tab存在（el-segmented）
    const segmentedTabs = detailComp.locator('.el-segmented, .segment-bar')
    await expect(segmentedTabs.first()).toBeVisible()

    // 验证3个区段标签文字：不可重分类 / 可重分类 / 税额区段
    const tabContainer = segmentedTabs.first()
    await expect(tabContainer.locator(':text("不可重分类")')).toBeVisible()
    await expect(tabContainer.locator(':text("可重分类")')).toBeVisible()
    await expect(tabContainer.locator(':text("税额")')).toBeVisible()

    // 点击"可重分类"Tab切换
    const reclassTab = tabContainer.locator(':text("可重分类")').first()
    await reclassTab.click()
    await page.waitForTimeout(1000)

    // 验证表格渲染
    const tables = detailComp.locator('.el-table')
    expect(await tables.count()).toBeGreaterThanOrEqual(1)

    // 点击"税额区段"Tab切换
    const taxTab = tabContainer.locator(':text("税额")').first()
    await taxTab.click()
    await page.waitForTimeout(1000)

    // 验证表格仍然渲染（区段切换不崩溃）
    expect(await tables.count()).toBeGreaterThanOrEqual(1)

    // 验证导入导出按钮存在
    const importExportBtn = detailComp.locator('button', { hasText: /导入导出/ })
    await expect(importExportBtn).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：OCI核对表 M9-4 → 多来源核对rows + 核对差异公式列 ═══
  test('7.3.5 — OCI核对表M9-4: 多来源核对rows + 核对差异公式列', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 切换到M9-4 OCI核对表
    const reconcileNav = page.locator('.el-table__row', { hasText: /M9-4/ })
    if (await reconcileNav.count() > 0) {
      await reconcileNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证核对表组件加载
    const reconcileComp = page.locator('.m9-tab-oci-reconcile')
    await expect(reconcileComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M9-4"
    const title = reconcileComp.locator('.section-title')
    await expect(title).toContainText('M9-4')

    // 验证"核心"badge
    const coreBadge = reconcileComp.locator('.core-badge')
    await expect(coreBadge).toBeVisible()
    await expect(coreBadge).toContainText('核心')

    // 验证双区块标题：不可重分类来源 + 可重分类来源
    const nonReclassBlock = reconcileComp.locator('.block-title', { hasText: /不能重分类|不可重分类/ })
    await expect(nonReclassBlock.first()).toBeVisible()

    const reclassBlock = reconcileComp.locator('.block-title', { hasText: /能重分类|可重分类/ })
    await expect(reclassBlock.first()).toBeVisible()

    // 验证核对表列头包含关键列
    await expect(reconcileComp.locator('th', { hasText: /来源底稿/ })).toBeVisible()
    await expect(reconcileComp.locator('th', { hasText: /来源金额/ })).toBeVisible()
    await expect(reconcileComp.locator('th', { hasText: /账面OCI/ })).toBeVisible()
    await expect(reconcileComp.locator('th', { hasText: /核对差异/ })).toBeVisible()

    // 验证核对差异列有公式tooltip
    const formulaHeaders = reconcileComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    // 验证 GtIndexChip 存在（G8/J2来源联动标识）
    const indexChips = reconcileComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await indexChips.count() > 0) {
      // 验证有G8或J2的交叉索引
      const chipTexts = await indexChips.allTextContents()
      const hasG8OrJ2 = chipTexts.some((t) => /G8|J2/.test(t))
      expect(hasG8OrJ2).toBe(true)
    }

    // 验证方法论上下文(琥珀色)
    const methodology = reconcileComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('核对差异')

    // 验证AI辅助按钮存在
    const aiBtn = reconcileComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：保存流程 → 无错误 + 双模式切换不崩 ═══
  test('7.3.6 — 保存流程: 审定表保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 切换到审定表 M9-1
    const adjNav = page.locator('.el-table__row', { hasText: /M9-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m9-tab-adjudication')
    if (await adjComp.count() > 0) {
      // 验证双模式切换（el-segmented: 结构化/OO）
      const modeSwitch = adjComp.locator('.section-header .el-segmented').first()
      if (await modeSwitch.count() > 0) {
        const modeItems = modeSwitch.locator('.el-segmented__item')
        if (await modeItems.count() >= 2) {
          // 切换到第二个模式（OO）
          await modeItems.nth(1).click()
          await page.waitForTimeout(2000)

          // 验证组件没崩
          const container = page.locator('.m9-other-comprehensive-income')
          await expect(container).toBeVisible()

          // 切回第一个模式（结构化）
          await modeItems.nth(0).click()
          await page.waitForTimeout(1000)
          await expect(container).toBeVisible()
        }
      }

      // 验证保存按钮存在并点击
      const saveBtn = adjComp.locator('button', { hasText: /保存/ })
      if (await saveBtn.count() > 0) {
        await saveBtn.first().click()
        await page.waitForTimeout(2000)
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：完整导航流程无 console 严重错误 ═══
  test('7.3.7 — 完整导航流程无 console 严重错误', async ({ page }) => {
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
    await page.waitForTimeout(4000)

    // 依次导航各sheet（M9-1→M9-2→M9-4→M9-3）
    const sheets = [
      /M9-1/,     // 审定表（双大类）
      /M9-2/,     // 明细表（区段Tab）
      /M9-4/,     // OCI核对（多来源）
      /M9-3/,     // 调整分录
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

  // ═══ 场景 8：render-config API 验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m9-other-comprehensive-income`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm9-other-comprehensive-income')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
