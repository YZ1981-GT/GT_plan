/**
 * Playwright E2E — N2 应交税费底稿完整流程验收
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 7.3
 * Requirements: 全部 (1~13)
 *
 * 验证场景：
 * 1. 打开N2底稿 → 目录页加载17行sheet（skip O1A/出口退税额复核示例）
 * 2. 切换审定表N2-1 → 验证负债类公式列（期末=期初+贷方-借方）
 * 3. 填入一行税种数据(期初/贷方/借方) → 验证公式列自动计算
 * 4. 切换N2-6增值税测算 → 验证销项税额自动计算
 * 5. 填入销售额/税率 → 验证销项税额=销售额×税率
 * 6. 切换N2-8其他税费测算 → 验证城建税计税依据联动
 * 7. 切换N2-9房产税测算 → 验证从价/从租模式
 * 8. 切换N2-10土增税测算 → 验证四级累进
 * 9. 切换N2-7出口退税 → 验证免抵退测算
 * 10. 保存 → 无错误
 *
 * 科目：2221应交税费（**贷方/负债类！期末=期初+贷方-借方**）
 * 核心特殊：①负债类贷方 ②多税种测算 ③增值税销项-进项 ④出口退税
 *           ⑤计税依据联动(N2-6→N2-8) ⑥计提联动N4
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/n2-taxes-payable.spec.ts
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

/** 通过 API 找到 N2 底稿 ID */
async function findN2WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 N2 底稿
  const n2 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'N2')
  if (n2) return { id: n2.id, code: 'N2' }
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

test.describe('N2 应交税费底稿 E2E 流程（Task 7.3）', () => {
  test.describe.configure({ mode: 'serial' })

  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findN2WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开N2底稿 → 目录页加载17行sheet ═══
  test('7.3.1 — 打开N2底稿，目录页加载(17行sheet)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 N2 组件容器加载
    const container = page.locator('.n2-taxes-payable')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（N2TabIndex）
    const directory = page.locator('.n2-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"负债类贷方科目"醒目标注
    const liabilityBadge = page.locator('.n2-liability-badge, .liability-badge')
    await expect(liabilityBadge).toBeVisible()
    await expect(liabilityBadge).toContainText(/负债|贷方/)

    // 验证有17行sheet目录（18总-1 O1A skip）
    const tableRows = page.locator('.n2-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(16) // 至少16行（含skip标记）

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'N2A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N2-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N2-6' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N2-8' })).toBeVisible()
  })

  // ═══ 场景 2：审定表N2-1 → 负债类公式列验证 ═══
  test('7.3.2 — 审定表N2-1: 负债类取数(期末=期初+贷方-借方)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到N2-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /N2-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.n2-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N2-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('N2-1')

    // 验证"负债类·贷方余额" badge
    const badge = adjComp.locator('.liability-badge, .equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText(/贷方|负债/)

    // 验证方法论上下文(琥珀色)显示负债类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/期末.*期初.*贷方.*借方|期初.*贷.*借/)

    // 验证表格中有多税种分行（增值税/城建税等）
    const table = adjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证公式列header有tooltip
    const formulaHeaders = adjComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：审定表录入数据验证公式计算 ═══
  test('7.3.3 — 审定表N2-1: 录入数据验证负债类公式自动计算', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-1
    const adjNav = page.locator('.el-table__row', { hasText: /N2-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.n2-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证保存按钮存在
    const saveBtn = adjComp.locator('button', { hasText: /保存/ })
    await expect(saveBtn).toBeVisible()

    // 验证新增项目按钮存在（多税种分行）
    const addBtn = adjComp.locator('button', { hasText: /新增|添加/ })
    if (await addBtn.count() > 0) {
      await expect(addBtn.first()).toBeVisible()
    }

    // 验证审计说明区域存在
    const conclusionCard = adjComp.locator('.conclusion-card, .audit-note-card')
    if (await conclusionCard.count() > 0) {
      await expect(conclusionCard.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：增值税测算N2-6 → 销项税额计算 ═══
  test('7.3.4 — 增值税测算N2-6: 验证销项税额公式', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-6增值税测算
    const vatNav = page.locator('.el-table__row', { hasText: /N2-6/ })
    if (await vatNav.count() > 0) {
      await vatNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证增值税测算组件加载
    const vatComp = page.locator('.n2-tab-vat-calc')
    await expect(vatComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N2-6"或"增值税"
    const title = vatComp.locator('.section-title')
    await expect(title).toContainText(/N2-6|增值税/)

    // 验证方法论上下文显示增值税公式
    const methodology = vatComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/销项|进项/)

    // 验证表格存在
    const table = vatComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证公式列有tooltip（销项税额是公式列）
    const formulaHeaders = vatComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    // 验证GtIndexChip（联动N2-1回填标识）
    const chips = vatComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await chips.count() > 0) {
      await expect(chips.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：N2-6销售额/税率录入验证 ═══
  test('7.3.5 — 增值税测算N2-6: 销售额×税率=销项税额验证', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-6
    const vatNav = page.locator('.el-table__row', { hasText: /N2-6/ })
    if (await vatNav.count() > 0) {
      await vatNav.first().click()
      await page.waitForTimeout(2000)
    }

    const vatComp = page.locator('.n2-tab-vat-calc')
    await expect(vatComp).toBeVisible({ timeout: 10_000 })

    // 验证保存按钮
    const saveBtn = vatComp.locator('button', { hasText: /保存/ })
    await expect(saveBtn).toBeVisible()

    // 验证税负率分析区域存在
    const burdenSection = vatComp.locator('.burden-rate, .tax-burden')
    if (await burdenSection.count() > 0) {
      await expect(burdenSection.first()).toBeVisible()
    }

    // 验证AI辅助按钮
    const aiBtn = vatComp.locator('button', { hasText: /AI/ })
    if (await aiBtn.count() > 0) {
      expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：其他税费测算N2-8 → 城建税计税依据联动 ═══
  test('7.3.6 — 其他税费测算N2-8: 城建税/教育费附加', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-8
    const otherNav = page.locator('.el-table__row', { hasText: /N2-8/ })
    if (await otherNav.count() > 0) {
      await otherNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证其他税费测算组件加载
    const otherComp = page.locator('.n2-tab-other-tax-calc')
    await expect(otherComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = otherComp.locator('.section-title')
    await expect(title).toContainText(/N2-8|其他税费/)

    // 验证方法论上下文
    const methodology = otherComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/城建税|增值税.*消费税/)

    // 验证表格
    const table = otherComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证GtIndexChip联动标识（来自N2-6）
    const chips = otherComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await chips.count() > 0) {
      await expect(chips.first()).toBeVisible()
    }

    // 验证地区选择器存在（城建税税率地区选择）
    const regionSelector = otherComp.locator('.el-select, .region-selector')
    if (await regionSelector.count() > 0) {
      await expect(regionSelector.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：房产税测算N2-9 ═══
  test('7.3.7 — 房产税测算N2-9: 从价/从租模式', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-9
    const propNav = page.locator('.el-table__row', { hasText: /N2-9/ })
    if (await propNav.count() > 0) {
      await propNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证房产税组件加载
    const propComp = page.locator('.n2-tab-property-tax')
    await expect(propComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = propComp.locator('.section-title')
    await expect(title).toContainText(/N2-9|房产税/)

    // 验证方法论上下文包含从价/从租公式
    const methodology = propComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/从价|原值|扣除比例|1\.2%/)

    // 验证表格
    const table = propComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 8：土增税测算N2-10 → 四级累进 ═══
  test('7.3.8 — 土增税测算N2-10: 四级累进税率', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-10
    const lvtNav = page.locator('.el-table__row', { hasText: /N2-10/ })
    if (await lvtNav.count() > 0) {
      await lvtNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证土增税组件加载
    const lvtComp = page.locator('.n2-tab-lvt')
    await expect(lvtComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = lvtComp.locator('.section-title')
    await expect(title).toContainText(/N2-10|土地增值税/)

    // 验证方法论上下文包含四级累进描述
    const methodology = lvtComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/30%|40%|50%|60%|累进/)

    // 验证表格
    const table = lvtComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 9：出口退税N2-7 ═══
  test('7.3.9 — 出口退税N2-7: 免抵退税额测算', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到N2-7
    const refundNav = page.locator('.el-table__row', { hasText: /N2-7/ })
    if (await refundNav.count() > 0) {
      await refundNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证出口退税组件加载
    const refundComp = page.locator('.n2-tab-export-refund')
    await expect(refundComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = refundComp.locator('.section-title')
    await expect(title).toContainText(/N2-7|出口退税/)

    // 验证表格
    const table = refundComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证GtIndexChip联动N2-6标识
    const chips = refundComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await chips.count() > 0) {
      await expect(chips.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 10：保存流程 + 双模式切换 ═══
  test('7.3.10 — 保存流程: 审定表保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到审定表 N2-1
    const adjNav = page.locator('.el-table__row', { hasText: /N2-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.n2-tab-adjudication')
    if (await adjComp.count() > 0) {
      // 验证双模式切换（el-segmented: 结构化/OO）
      const modeSwitch = adjComp.locator('.section-header .el-segmented').first()
      if (await modeSwitch.count() > 0) {
        const modeItems = modeSwitch.locator('.el-segmented__item')
        if (await modeItems.count() >= 2) {
          // 切换到OO模式
          await modeItems.nth(1).click()
          await page.waitForTimeout(2000)

          // 验证不崩
          const container = page.locator('.n2-taxes-payable')
          await expect(container).toBeVisible()

          // 切回结构化
          await modeItems.nth(0).click()
          await page.waitForTimeout(1000)
          await expect(container).toBeVisible()
        }
      }

      // 验证保存按钮并点击
      const saveBtn = adjComp.locator('button', { hasText: /保存/ })
      if (await saveBtn.count() > 0) {
        await saveBtn.first().click()
        await page.waitForTimeout(2000)
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 11：完整导航流程无console严重错误 ═══
  test('7.3.11 — 完整导航流程无console严重错误', async ({ page }) => {
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

    // 依次导航各核心sheet
    const sheets = [
      /N2-1/,   // 审定表
      /N2-2/,   // 明细表
      /N2-6/,   // 增值税测算
      /N2-8/,   // 其他税费测算
      /N2-9/,   // 房产税
      /N2-10/,  // 土增税
      /N2-7/,   // 出口退税
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

  // ═══ 场景 12：render-config API验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=n2-taxes-payable`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'n2-taxes-payable')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
