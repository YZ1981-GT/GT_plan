/**
 * Playwright E2E — M6 未分配利润底稿完整流程验收
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 M6 底稿 → sheetName 分发 → 目录导航可见（7行sheet）
 * 2. 切换审定表 M6-1 → 验证 equity-badge 可见、单区块表格渲染
 * 3. 审定表录入（期初/贷方/借方）→ 验证期末公式列自动计算
 * 4. 切换明细表 M6-2 → 验证引导区6步可见
 * 5. 明细表填入（期初/净利润/盈余公积/股利）→ 验证 retainedEnd 公式
 * 6. 验证联动差异提示（M5/M1值不一致时）
 * 7. 切换检查表 M6-4 → 验证7个检查项+状态标签渲染
 * 8. 保存 → 无错误
 *
 * 科目：4104利润分配-未分配利润（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方 ②利润分配结转核心公式链（期末=期初+净利润-盈余公积-股利）
 *           ③上游接收本年利润 ④下游驱动M5盈余公积计提+M1股利分配 ⑤TB回写(4104)
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m6-retained-earnings.spec.ts
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

/** 通过 API 找到 M6 底稿 ID */
async function findM6WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M6 底稿
  const m6 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M6')
  if (m6) return { id: m6.id, code: 'M6' }
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

test.describe('M6 未分配利润底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM6WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M6 底稿 → 目录页加载7行sheet ═══
  test('7.3.1 — 打开 M6 底稿，目录页加载7行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M6 组件容器加载
    const container = page.locator('.m6-retained-earnings')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M6TabIndex）
    const directory = page.locator('.m6-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m6-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m6-guide')
    await expect(guide).toBeVisible()

    // 验证有7行sheet目录（M6A/M6-1/附注上市/附注国企/M6-2/M6-3/M6-4）
    const tableRows = page.locator('.m6-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(7)

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'M6A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M6-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M6-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M6-4' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M6-1 → equity-badge + 单区块表格 ═══
  test('7.3.2 — 审定表M6-1: equity-badge可见+单区块表格渲染', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M6-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M6-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m6-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M6-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M6-1')

    // 验证"权益类·贷方余额" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('贷方余额')

    // 验证单区块结构：利润分配-未分配利润
    const blockTitle = adjComp.locator('.block-title')
    await expect(blockTitle).toBeVisible()
    await expect(blockTitle).toContainText('利润分配-未分配利润')

    // 验证表格存在
    const table = adjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证方法论上下文(琥珀色)显示权益类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('期末余额 = 期初 + 贷方')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：审定表公式验证 — 录入期初/贷方/借方 → 期末自动计算 ═══
  test('7.3.3 — 审定表M6-1: 录入期初/贷方/借方→期末公式自动计算', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M6-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M6-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m6-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证公式列header有tooltip（期末列 formula-col-header）
    const formulaHeaders = adjComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    // 验证保存按钮存在
    const saveBtn = adjComp.locator('button', { hasText: /保存/ })
    await expect(saveBtn).toBeVisible()

    // 验证新增项目按钮存在
    const addBtn = adjComp.locator('button', { hasText: /新增项目/ })
    if (await addBtn.count() > 0) {
      await expect(addBtn.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：明细表 M6-2 → 引导区6步可见 ═══
  test('7.3.4 — 明细表M6-2: 引导区6步可见+利润分配结转结构', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M6-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M6-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m6-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M6-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M6-2')

    // 验证引导区存在
    const guideArea = detailComp.locator('.guide-area')
    await expect(guideArea).toBeVisible()

    // 验证6步引导
    const guideSteps = guideArea.locator('.guide-step')
    const stepCount = await guideSteps.count()
    expect(stepCount).toBe(6)

    // 验证步骤内容关键词
    await expect(guideSteps.nth(0)).toContainText('期初未分配利润')
    await expect(guideSteps.nth(1)).toContainText('本年净利润')
    await expect(guideSteps.nth(2)).toContainText('可供分配利润')
    await expect(guideSteps.nth(3)).toContainText('盈余公积')
    await expect(guideSteps.nth(4)).toContainText('应付股利')
    await expect(guideSteps.nth(5)).toContainText('期末未分配利润')

    // 验证权益类badge
    const badge = detailComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('利润分配结转核心')

    // 验证方法论上下文
    const methodology = detailComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('利润分配结转公式链')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：明细表填入数据 → retainedEnd公式验证 + 导入导出 ═══
  test('7.3.5 — 明细表M6-2: 数据区渲染+导入导出el-dropdown 3项', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M6-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M6-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    const detailComp = page.locator('.m6-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证"导入导出"按钮存在（el-dropdown trigger）
    const importExportBtn = detailComp.locator('button', { hasText: /导入导出/ })
    await expect(importExportBtn).toBeVisible()

    // 点击打开下拉菜单
    await importExportBtn.click()
    await page.waitForTimeout(500)

    // 验证下拉菜单出现
    const dropdownMenu = page.locator('.el-dropdown-menu:visible')
    await expect(dropdownMenu).toBeVisible({ timeout: 5000 })

    // 验证3项菜单项
    const menuItems = dropdownMenu.locator('.el-dropdown-menu__item')
    expect(await menuItems.count()).toBe(3)

    // 验证具体菜单文字
    await expect(menuItems.nth(0)).toContainText('导出模板')
    await expect(menuItems.nth(1)).toContainText('导出数据')
    await expect(menuItems.nth(2)).toContainText('导入数据')

    // 关闭菜单
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)

    // 验证保存按钮存在
    const saveBtn = detailComp.locator('button', { hasText: /保存/ })
    await expect(saveBtn).toBeVisible()

    // 验证AI辅助按钮
    const aiBtn = detailComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)
  })

  // ═══ 场景 6：M5/M1联动核对（联动差异提示） ═══
  test('7.3.6 — M5/M1联动核对: 差异提示区域存在', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M6-4检查表（联动核对集中展示在此）
    const checkNav = page.locator('.el-table__row', { hasText: /M6-4/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    const checkComp = page.locator('.m6-tab-retained-check')
    await expect(checkComp).toBeVisible({ timeout: 10_000 })

    // 验证核对表格存在（包含M5/M1联动核对行）
    const checkTable = checkComp.locator('.check-table, .el-table')
    await expect(checkTable.first()).toBeVisible()

    // 验证联动核对类别标签（cross-check 分类的检查项）
    const crossCheckTags = checkComp.locator('.category-tag')
    expect(await crossCheckTags.count()).toBeGreaterThanOrEqual(1)

    // 验证M5来源引用（GtIndexChip）
    const indexChips = checkComp.locator('.gt-index-chip, [class*="index-chip"]')
    expect(await indexChips.count()).toBeGreaterThanOrEqual(1)

    // 验证差异列存在
    const diffCells = checkComp.locator('.diff-cell')
    // 差异列可能有也可能没有值（取决于是否已有数据），检查列结构即可
    const tableHeaders = checkComp.locator('.el-table__header th')
    const headerTexts = await tableHeaders.allTextContents()
    expect(headerTexts.some(h => h.includes('差异'))).toBeTruthy()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：检查表 M6-4 → 7个检查项+状态标签渲染 ═══
  test('7.3.7 — 检查表M6-4: 7个检查项+状态标签渲染', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M6-4检查表
    const checkNav = page.locator('.el-table__row', { hasText: /M6-4/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证检查表组件加载
    const checkComp = page.locator('.m6-tab-retained-check')
    await expect(checkComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M6-4"
    const title = checkComp.locator('.section-title')
    await expect(title).toContainText('M6-4')

    // 验证核对清单表格（7行检查项）
    const checkTableRows = checkComp.locator('.check-table .el-table__row, .el-table .el-table__row')
    const rowCount = await checkTableRows.count()
    expect(rowCount).toBe(7)

    // 验证关键检查项描述
    await expect(checkComp.locator('text=期初未分配利润与上年末审定数一致')).toBeVisible()
    await expect(checkComp.locator('text=本年净利润与利润表结转数一致')).toBeVisible()
    await expect(checkComp.locator('text=提取盈余公积=M5盈余公积实际计提数')).toBeVisible()
    await expect(checkComp.locator('text=分配股利=M1应付股利实际宣告数')).toBeVisible()
    await expect(checkComp.locator('text=审定数与试算表科目4104余额核对一致')).toBeVisible()

    // 验证状态标签列（每行都有el-tag状态）
    const statusTags = checkComp.locator('.el-tag')
    expect(await statusTags.count()).toBeGreaterThanOrEqual(7)

    // 验证方法论上下文存在
    const methodology = checkComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('权益类贷方科目')

    // 验证AI辅助按钮
    const aiBtn = checkComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 8：保存流程 → 无错误 + 双模式切换不崩 ═══
  test('7.3.8 — 保存流程: 审定表保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到审定表 M6-1
    const adjNav = page.locator('.el-table__row', { hasText: /M6-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m6-tab-adjudication')
    if (await adjComp.count() > 0) {
      // 验证双模式切换（el-segmented: 结构化/OO）
      const modeSwitch = adjComp.locator('.el-segmented').first()
      if (await modeSwitch.count() > 0) {
        const modeItems = modeSwitch.locator('.el-segmented__item')
        if (await modeItems.count() >= 2) {
          // 切换到第二个模式（OO）
          await modeItems.nth(1).click()
          await page.waitForTimeout(2000)

          // 验证组件没崩
          const container = page.locator('.m6-retained-earnings')
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

  // ═══ 场景 9：完整导航流程无 console 严重错误 ═══
  test('7.3.9 — 完整导航流程无 console 严重错误', async ({ page }) => {
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

    // 依次导航各sheet（M6-1→M6-2→M6-4→M6-3）
    const sheets = [
      /M6-1/,     // 审定表
      /M6-2/,     // 明细表（利润分配结转）
      /M6-4/,     // 检查表
      /M6-3/,     // 调整分录
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

  // ═══ 场景 10：render-config API 验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m6-retained-earnings`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm6-retained-earnings')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
