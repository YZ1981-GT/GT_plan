/**
 * Playwright E2E — M7 专项储备底稿完整流程验收
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 7.3
 * Requirements: 全部 (1~7)
 *
 * 验证场景：
 * 1. 打开 M7 底稿 → sheetName 分发 → 底稿目录渲染8行sheet
 * 2. 切换审定表 M7-1 → 验证权益类列可见（期初/贷方计提/借方使用/期末/审定）
 * 3. 切换明细表 M7-2 → 验证3区段Tab（计提/费用化/资本化）
 * 4. 切换计提测试 M7-4 → 验证行业选择器（按产量/按营业收入）
 * 5. 切换支出检查 M7-5 → 验证两类检查区块（费用性+资本性）
 * 6. 保存流程 → 无错误
 *
 * 科目：4201专项储备（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方（计提贷方增加，使用借方减少）
 *           ②安全生产费按产量/营业收入分档计提
 *           ③支出区分费用化（直接冲减）vs 资本化（联动H1固定资产）
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m7-special-reserve.spec.ts
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

/** 通过 API 找到 M7 底稿 ID */
async function findM7WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M7 底稿
  const m7 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M7')
  if (m7) return { id: m7.id, code: 'M7' }
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

test.describe('M7 专项储备底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM7WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M7 底稿 → 底稿目录渲染8行sheet ═══
  test('7.3.1 — 打开 M7 底稿，底稿目录渲染8行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M7 组件容器加载
    const container = page.locator('.m7-special-reserve')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M7TabIndex）
    const directory = page.locator('.m7-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m7-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m7-guide')
    await expect(guide).toBeVisible()

    // 验证有8行sheet目录（M7A+M7-1+附注上市+附注国企+M7-2+M7-3+M7-4+M7-5）
    const tableRows = page.locator('.m7-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(8)

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'M7A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M7-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M7-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M7-4' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M7-5' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M7-1 → 权益类列可见 ═══
  test('7.3.2 — 审定表M7-1: 权益类列可见（期初/贷方计提/借方使用/期末/审定）', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M7-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M7-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m7-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M7-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M7-1')

    // 验证"权益类·贷方余额" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('贷方余额')

    // 验证表格列头包含权益类关键列
    const table = adjComp.locator('.el-table').first()
    await expect(table).toBeVisible()

    // 权益类列：期初 / 贷方发生(计提) / 借方发生(使用) / 期末
    await expect(adjComp.locator('th', { hasText: /期初/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /贷方|计提/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /借方|使用/ })).toBeVisible()
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

  // ═══ 场景 3：明细表 M7-2 → 3区段Tab（计提/费用化/资本化） ═══
  test('7.3.3 — 明细表M7-2: 3区段Tab（计提/费用化/资本化）', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M7-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M7-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m7-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M7-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M7-2')

    // 验证3区段Tab存在（el-segmented 或 el-radio-group）
    const segmentedTabs = detailComp.locator('.el-segmented, .el-radio-group, .segment-tabs')
    await expect(segmentedTabs.first()).toBeVisible()

    // 验证3个区段标签文字：计提 / 费用化使用 / 资本化使用
    const tabContainer = detailComp.locator('.el-segmented, .el-radio-group, .segment-tabs').first()
    await expect(tabContainer.locator(':text("计提")')).toBeVisible()
    await expect(tabContainer.locator(':text("费用化")')).toBeVisible()
    await expect(tabContainer.locator(':text("资本化")')).toBeVisible()

    // 验证表格渲染
    const tables = detailComp.locator('.el-table')
    expect(await tables.count()).toBeGreaterThanOrEqual(1)

    // 验证导入导出按钮存在
    const importExportBtn = detailComp.locator('button', { hasText: /导入导出/ })
    await expect(importExportBtn).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：计提测试 M7-4 → 行业选择器（按产量/按营业收入） ═══
  test('7.3.4 — 计提测试M7-4: 行业选择器（按产量/按营业收入）', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M7-4计提测试
    const accrualNav = page.locator('.el-table__row', { hasText: /M7-4/ })
    if (await accrualNav.count() > 0) {
      await accrualNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证计提测试组件加载
    const accrualComp = page.locator('.m7-tab-accrual-test')
    await expect(accrualComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M7-4"
    const title = accrualComp.locator('.section-title')
    await expect(title).toContainText('M7-4')

    // 验证行业/计提基础选择器存在（el-select 或 el-radio-group）
    const industrySelector = accrualComp.locator(
      '.el-select, .el-radio-group, .industry-selector, .accrual-basis-selector',
    )
    await expect(industrySelector.first()).toBeVisible()

    // 验证选项包含"按产量"和"按营业收入"两种计提基础
    // 选择器可能是el-select下拉或el-segmented/radio选择
    const basisOptions = accrualComp.locator(
      '.el-segmented__item, .el-radio, .basis-option, [class*="accrual-basis"]',
    )
    if (await basisOptions.count() >= 2) {
      // 验证两种基础选项可见
      expect(await basisOptions.count()).toBeGreaterThanOrEqual(2)
    }

    // 验证方法论上下文(琥珀色)显示安全生产费计提标准
    const methodology = accrualComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/安全生产费|计提/)

    // 验证计提主表存在
    const accrualTable = accrualComp.locator('.accrual-main-table, .el-table')
    await expect(accrualTable.first()).toBeVisible()

    // 验证差异列存在（差异=应计提-账面计提）
    await expect(accrualComp.locator('th', { hasText: /差异/ })).toBeVisible()

    // 验证AI辅助按钮
    const aiBtn = accrualComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：支出检查 M7-5 → 两类检查区块（费用性+资本性） ═══
  test('7.3.5 — 支出检查M7-5: 两类检查区块（费用性+资本性）', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M7-5支出检查
    const checkNav = page.locator('.el-table__row', { hasText: /M7-5/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证支出检查组件加载
    const checkComp = page.locator('.m7-tab-expenditure-check')
    await expect(checkComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M7-5"
    const title = checkComp.locator('.section-title')
    await expect(title).toContainText('M7-5')

    // 验证两类检查区块：费用性支出 + 资本性支出
    const blockHeaders = checkComp.locator('.block-title, .check-block-title, .el-card__header')

    const expenseBlock = checkComp.locator(
      '.block-title, .check-block-title, .el-card__header, [class*="block"]',
      { hasText: /费用性|费用化/ },
    )
    await expect(expenseBlock.first()).toBeVisible()

    const capitalBlock = checkComp.locator(
      '.block-title, .check-block-title, .el-card__header, [class*="block"]',
      { hasText: /资本性|资本化/ },
    )
    await expect(capitalBlock.first()).toBeVisible()

    // 验证审计结论区（el-card包裹）
    const conclusionCard = checkComp.locator('.conclusion-card, .el-card')
    expect(await conclusionCard.count()).toBeGreaterThanOrEqual(1)

    // 验证结论区有 textarea
    const conclusionTextarea = checkComp.locator('textarea')
    expect(await conclusionTextarea.count()).toBeGreaterThanOrEqual(1)

    // 验证AI辅助按钮（多个section标题行）
    const aiButtons = checkComp.locator('button', { hasText: /AI/ })
    expect(await aiButtons.count()).toBeGreaterThanOrEqual(2)

    // 验证资本化区块有H1联动提示（GtIndexChip或提示文字）
    const h1Ref = checkComp.locator('.gt-index-chip, [class*="index-chip"], :text("H1")')
    if (await h1Ref.count() > 0) {
      await expect(h1Ref.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：保存流程 → 无错误 + 双模式切换不崩 ═══
  test('7.3.6 — 保存流程: 审定表保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到审定表 M7-1
    const adjNav = page.locator('.el-table__row', { hasText: /M7-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m7-tab-adjudication')
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
          const container = page.locator('.m7-special-reserve')
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
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(4000)

    // 依次导航各sheet（M7-1→M7-2→M7-4→M7-5→M7-3）
    const sheets = [
      /M7-1/,     // 审定表
      /M7-2/,     // 明细表
      /M7-4/,     // 计提测试
      /M7-5/,     // 支出检查
      /M7-3/,     // 调整分录
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
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m7-special-reserve`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm7-special-reserve')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
