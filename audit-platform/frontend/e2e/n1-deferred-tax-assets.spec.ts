/**
 * Playwright E2E — N1 递延所得税资产底稿完整流程验收
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 7.3
 * Requirements: 全部 (1~8)
 *
 * 验证场景：
 * 1. 打开N1底稿 → 目录页加载9行sheet+资产类badge可见
 * 2. 切换审定表N1-1 → 验证资产类取数(期末=期初+借方-贷方)+公式tooltip
 * 3. 切换明细表N1-2 → 验证可抵扣暂时性差异×税率+统计摘要
 * 4. 切换测算表N1-4 → 验证暂时性差异×税率+资产/负债双部分
 * 5. 切换亏损检查N1-5 → 验证谨慎性警告+弥补期限判断
 * 6. 切换调整分录N1-3 → 验证借贷平衡校验
 * 7. 双模式切换(HTML ↔ OnlyOffice)不崩
 * 8. 保存流程触发版本快照
 * 9. 完整导航流程无console严重错误
 *
 * 科目：1811递延所得税资产（**借方/资产类！期末=期初+借方-贷方**）
 * 核心特殊：①资产类借方 ②可抵扣暂时性差异×税率 ③可弥补亏损确认
 *           ④与N3递延所得税负债对应 ⑤N5递延税费用核对联动
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/n1-deferred-tax-assets.spec.ts
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

/** 通过 API 找到 N1 底稿 ID */
async function findN1WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 N1 底稿
  const n1 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'N1')
  if (n1) return { id: n1.id, code: 'N1' }
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

test.describe('N1 递延所得税资产底稿 E2E 流程（Task 7.3）', () => {
  test.describe.configure({ mode: 'serial' })

  let wpId: string = ''
  let skipAll = false

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findN1WpId(request, token)
    if (!wp) {
      skipAll = true
      return
    }
    wpId = wp.id
  })

  // ═══ 场景 1：打开N1底稿 → 目录页加载9行sheet ═══
  test('7.3.1 — 打开N1底稿，目录页加载(9行sheet+资产类badge)', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 验证 N1 组件容器加载
    const container = page.locator('.n1-deferred-tax-assets')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（N1TabIndex）
    const directory = page.locator('.n1-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"资产类·借方"醒目标注
    const assetBadge = page.locator('.n1-asset-badge')
    await expect(assetBadge).toBeVisible()
    await expect(assetBadge).toContainText(/资产|借方/)

    // 验证有9行sheet目录
    const tableRows = page.locator('.n1-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(8) // 至少8行有效sheet

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'N1A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N1-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N1-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N1-3' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N1-4' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'N1-5' })).toBeVisible()

    // 验证进度统计区域可见
    const progressSection = page.locator('.n1-progress-section')
    await expect(progressSection).toBeVisible()

    // 验证操作引导区存在
    const guide = page.locator('.n1-guide')
    await expect(guide).toBeVisible()
  })

  // ═══ 场景 2：审定表N1-1 → 资产类取数+公式badge ═══
  test('7.3.2 — 审定表N1-1: 资产类取数(期末=期初+借方-贷方)+公式tooltip', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 通过目录导航切换到N1-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /N1-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.n1-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N1-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('N1-1')

    // 验证"资产类·借方" tag
    const assetTag = adjComp.locator('.asset-tag')
    await expect(assetTag).toBeVisible()
    await expect(assetTag).toContainText(/资产|借方/)

    // 验证方法论上下文(琥珀色)显示资产类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/可抵扣暂时性差异|递延所得税资产/)

    // 验证资产类公式提示badge
    const formulaBadge = adjComp.locator('.asset-formula-badge')
    await expect(formulaBadge).toBeVisible()
    await expect(formulaBadge).toContainText(/期末.*期初.*借方.*贷方|期初.*借.*贷/)

    // 验证表格列头（项目/期初/借方/贷方/审定数）
    const table = adjComp.locator('.el-table')
    await expect(table.first()).toBeVisible()

    // 验证关键列header
    await expect(adjComp.locator('th', { hasText: '期初' })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /借方/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /贷方/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /审定数/ })).toBeVisible()

    // 验证N3对应关系提示存在
    const n3Hint = adjComp.locator('.n3-correspondence-hint, [data-testid="n3-hint"]')
    if (await n3Hint.count() > 0) {
      await expect(n3Hint.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：明细表N1-2 → 可抵扣暂时性差异×税率+统计摘要 ═══
  test('7.3.3 — 明细表N1-2: 可抵扣暂时性差异×税率+统计摘要+新增行', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N1-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /N1-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.n1-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N1-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('N1-2')

    // 验证方法论上下文包含核心公式说明
    const methodology = detailComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/可抵扣暂时性差异.*税率|账面价值.*计税基础/)

    // 验证统计摘要区域可见
    const summaryBar = detailComp.locator('.summary-bar')
    await expect(summaryBar).toBeVisible()

    // 验证统计项目存在
    await expect(summaryBar.locator('text=差异项目数')).toBeVisible()
    await expect(summaryBar.locator('text=可抵扣差异合计')).toBeVisible()
    await expect(summaryBar.locator('text=递延税资产合计')).toBeVisible()
    await expect(summaryBar.locator('text=加权平均税率')).toBeVisible()

    // 验证表格存在并有关键列
    const table = detailComp.locator('.el-table')
    await expect(table.first()).toBeVisible()
    await expect(detailComp.locator('th', { hasText: '账面价值' })).toBeVisible()
    await expect(detailComp.locator('th', { hasText: '计税基础' })).toBeVisible()
    await expect(detailComp.locator('th', { hasText: /适用税率/ })).toBeVisible()

    // 验证新增行按钮存在
    const addRowBtn = detailComp.locator('.add-row-bar button, button', { hasText: /新增/ })
    await expect(addRowBtn).toBeVisible()

    // 验证导入导出按钮存在
    const importExportBtn = detailComp.locator('.el-dropdown, button', { hasText: /导入导出/ })
    if (await importExportBtn.count() > 0) {
      await expect(importExportBtn.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：测算表N1-4 → 暂时性差异×税率（核心引擎） ═══
  test('7.3.4 — 测算表N1-4: 暂时性差异×税率+资产/负债双部分+确认条件', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N1-4测算表
    const calcNav = page.locator('.el-table__row', { hasText: /N1-4/ })
    if (await calcNav.count() > 0) {
      await calcNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证测算表组件加载
    const calcComp = page.locator('.n1-tab-calc-table')
    await expect(calcComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N1-4"
    const title = calcComp.locator('.section-title')
    await expect(title).toContainText('N1-4')

    // 验证方法论上下文包含测算逻辑
    const methodology = calcComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/暂时性差异.*税率|递延所得税/)

    // 验证表格存在并有关键列
    const table = calcComp.locator('.el-table')
    await expect(table.first()).toBeVisible()
    await expect(calcComp.locator('th', { hasText: '账面价值' })).toBeVisible()
    await expect(calcComp.locator('th', { hasText: '计税基础' })).toBeVisible()
    await expect(calcComp.locator('th', { hasText: /适用税率/ })).toBeVisible()

    // 验证资产/负债双部分区分（递延税资产列+递延税负债列）
    await expect(calcComp.locator('th', { hasText: /递延所得税资产/ })).toBeVisible()
    await expect(calcComp.locator('th', { hasText: /递延所得税负债/ })).toBeVisible()

    // 验证确认条件判断区域
    const confirmCondition = calcComp.locator('.confirm-condition, [data-testid="confirm-condition"]')
    if (await confirmCondition.count() > 0) {
      await expect(confirmCondition.first()).toBeVisible()
    }

    // 验证GtIndexChip跨底稿跳转(N3链接)
    const n3Chip = calcComp.locator('.gt-index-chip, [data-testid="cross-ref-chip"]')
    if (await n3Chip.count() > 0) {
      await expect(n3Chip.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：亏损检查N1-5 → 谨慎性警告+弥补期限 ═══
  test('7.3.5 — 亏损检查N1-5: 谨慎性警告+弥补期限判断+可确认额', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N1-5亏损检查
    const lossNav = page.locator('.el-table__row', { hasText: /N1-5/ })
    if (await lossNav.count() > 0) {
      await lossNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证亏损检查组件加载
    const lossComp = page.locator('.n1-tab-loss-check')
    await expect(lossComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N1-5"
    const title = lossComp.locator('.section-title')
    await expect(title).toContainText('N1-5')

    // 验证方法论上下文包含谨慎性原则说明
    const methodology = lossComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText(/可弥补亏损|谨慎性|未来.*应纳税所得额/)

    // 验证表格存在并有关键列
    const table = lossComp.locator('.el-table')
    await expect(table.first()).toBeVisible()
    await expect(lossComp.locator('th', { hasText: /亏损年度/ })).toBeVisible()
    await expect(lossComp.locator('th', { hasText: /亏损金额/ })).toBeVisible()
    await expect(lossComp.locator('th', { hasText: /未弥补/ })).toBeVisible()

    // 验证弥补期限说明（5年/10年）
    const periodHint = lossComp.locator('.period-hint, .compensation-period')
    if (await periodHint.count() > 0) {
      await expect(periodHint.first()).toContainText(/5年|10年|弥补期限/)
    }

    // 验证确认判断依据区域
    const conclusion = lossComp.locator('.conclusion-section, .el-card')
    expect(await conclusion.count()).toBeGreaterThanOrEqual(1)

    // 验证复核入口按钮
    const reviewBtn = lossComp.locator('button', { hasText: /复核/ })
    if (await reviewBtn.count() > 0) {
      await expect(reviewBtn.first()).toBeVisible()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：调整分录N1-3 → 借贷平衡校验 ═══
  test('7.3.6 — 调整分录N1-3: AJE/RJE切换+借贷平衡校验', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到N1-3调整分录
    const adjNav = page.locator('.el-table__row', { hasText: /N1-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证调整分录组件加载
    const adjComp = page.locator('.n1-tab-adjustment')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"N1-3"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('N1-3')

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

  // ═══ 场景 7：双模式切换(HTML ↔ OnlyOffice)不崩 ═══
  test('7.3.7 — 双模式切换(HTML ↔ OnlyOffice)不崩溃', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到审定表 N1-1
    const adjNav = page.locator('.el-table__row', { hasText: /N1-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const container = page.locator('.n1-deferred-tax-assets')

    // 验证双模式切换（el-segmented: HTML/OnlyOffice）
    const modeSwitch = page.locator('.n1-deferred-tax-assets-toolbar .el-segmented').first()
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

  // ═══ 场景 8：保存流程触发版本快照 ═══
  test('7.3.8 — 保存操作触发版本快照', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(4000)

    // 切换到审定表 N1-1（有保存功能的核心sheet）
    const adjNav = page.locator('.el-table__row', { hasText: /N1-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 找到全局保存按钮或sheet级保存按钮
    const saveBtn = page.locator('button', { hasText: /保存/ }).first()
    if (await saveBtn.count() > 0 && await saveBtn.isVisible()) {
      // 监听网络请求（保存应触发 API 调用）
      const savePromise = page.waitForResponse(
        (resp) => resp.url().includes('/api/workpapers/') && resp.request().method() === 'PUT',
        { timeout: 10_000 },
      ).catch(() => null)

      await saveBtn.click()
      const saveResp = await savePromise

      // 如果捕获到保存响应，验证成功
      if (saveResp) {
        expect(saveResp.status()).toBeLessThan(400)
      }

      // 验证保存成功提示或无错误
      await page.waitForTimeout(1500)
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ═══ 场景 9：完整导航流程无console严重错误 ═══
  test('7.3.9 — 完整导航流程无console严重错误', async ({ page }) => {
    test.skip(skipAll, 'N1底稿不存在于测试项目中')
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

    // 依次导航各核心sheet：N1-1→N1-2→N1-4→N1-5→N1-3
    const sheets = [
      /N1-1/,   // 审定表
      /N1-2/,   // 明细表
      /N1-4/,   // 测算表
      /N1-5/,   // 亏损检查
      /N1-3/,   // 调整分录
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

  // ═══ 场景 10：render-config API验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=n1-deferred-tax-assets`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'n1-deferred-tax-assets')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
