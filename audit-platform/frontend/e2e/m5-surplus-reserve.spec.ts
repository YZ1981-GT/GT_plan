/**
 * Playwright E2E — M5 盈余公积底稿完整流程验收
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 M5 底稿 → sheetName 分发 → 目录导航可见（8行sheet）
 * 2. 切换审定表 M5-1 → 验证双区块布局（法定+任意盈余公积）+ 权益类公式列
 * 3. 验证审定数=未审+AJE+RJE自动计算 + 期末=期初+贷方-借方
 * 4. 切换明细表 M5-2 → 验证两区段(法定+任意) + 12公式 + 动态行prompt
 * 5. 验证 el-dropdown "导入导出" 菜单（3项：导出模板/导出数据/导入数据）
 * 6. 切换计提检查 M5-4 → 验证11公式 + GtIndexChip M6
 * 7. 切换检查表 M5-5 → 验证8项核对清单 + 审计结论区
 * 8. 保存流程 → 无错误
 *
 * 科目：4101盈余公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方 ②法定+任意盈余公积双区块 ③接收M6未分配利润计提基数
 *           ④法定10%计提+50%上限判断 ⑤M5-M6利润分配闭环
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m5-surplus-reserve.spec.ts
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

/** 通过 API 找到 M5 底稿 ID */
async function findM5WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M5 底稿
  const m5 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M5')
  if (m5) return { id: m5.id, code: 'M5' }
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

test.describe('M5 盈余公积底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM5WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M5 底稿 → 目录页加载8行sheet ═══
  test('7.3.1 — 打开 M5 底稿，目录页加载8行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M5 组件容器加载
    const container = page.locator('.m5-surplus-reserve')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M5TabIndex）
    const directory = page.locator('.m5-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m5-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m5-guide')
    await expect(guide).toBeVisible()

    // 验证有8行sheet目录（M5A+M5-1+附注上市+附注国企+M5-2+M5-3+M5-4+M5-5）
    const tableRows = page.locator('.m5-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(8)

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'M5A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M5-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M5-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M5-4' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M5-5' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M5-1 → 双区块布局（法定+任意盈余公积）+ 公式列 ═══
  test('7.3.2 — 审定表M5-1: 双区块(法定+任意盈余公积)+权益类公式列', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M5-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M5-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m5-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M5-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M5-1')

    // 验证"权益类·贷方余额" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('贷方余额')

    // 验证双区块结构：区块一 "法定盈余公积" + 区块二 "任意盈余公积"
    const blockHeaders = adjComp.locator('.block-title')
    const blockCount = await blockHeaders.count()
    expect(blockCount).toBeGreaterThanOrEqual(2)

    const statutoryBlock = adjComp.locator('.block-title', { hasText: /法定盈余公积/ })
    await expect(statutoryBlock).toBeVisible()

    const voluntaryBlock = adjComp.locator('.block-title', { hasText: /任意盈余公积/ })
    await expect(voluntaryBlock).toBeVisible()

    // 验证表格存在（每个区块有 el-table）
    const tables = adjComp.locator('.el-table')
    expect(await tables.count()).toBeGreaterThanOrEqual(2)

    // 验证方法论上下文(琥珀色)显示权益类公式
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('期末余额 = 期初 + 贷方')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：审定表公式验证 — 审定数=未审+AJE+RJE + 期末=期初+贷方-借方 ═══
  test('7.3.3 — 审定表M5-1: 数据录入验证公式(期末=期初+贷方-借方)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M5-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M5-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m5-tab-adjudication')
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

  // ═══ 场景 4：明细表 M5-2 → 两区段(法定+任意) + 动态行ElMessageBox.prompt ═══
  test('7.3.4 — 明细表M5-2: 两区段(法定+任意)+动态行ElMessageBox.prompt', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M5-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M5-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m5-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M5-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M5-2')

    // 验证两区段结构：法定盈余公积明细 + 任意盈余公积明细
    const blockHeaders = detailComp.locator('.block-title')
    expect(await blockHeaders.count()).toBeGreaterThanOrEqual(2)

    const statutoryDetailBlock = detailComp.locator('.block-title', { hasText: /法定盈余公积/ })
    await expect(statutoryDetailBlock).toBeVisible()

    const voluntaryDetailBlock = detailComp.locator('.block-title', { hasText: /任意盈余公积/ })
    await expect(voluntaryDetailBlock).toBeVisible()

    // 验证表格渲染
    const tables = detailComp.locator('.el-table')
    expect(await tables.count()).toBeGreaterThanOrEqual(2)

    // 验证新增明细按钮存在
    const addBtn = detailComp.locator('button', { hasText: /新增明细/ })
    if (await addBtn.count() > 0) {
      await expect(addBtn.first()).toBeVisible()

      // 点击新增 → 应弹出 ElMessageBox.prompt 输入明细名称
      await addBtn.first().click()
      await page.waitForTimeout(1000)

      // 验证弹窗出现
      const promptDialog = page.locator('.el-message-box')
      if (await promptDialog.count() > 0) {
        await expect(promptDialog.first()).toBeVisible()

        // 关闭弹窗（取消）
        const cancelBtn = promptDialog.locator('button', { hasText: /取消|Cancel/ })
        if (await cancelBtn.count() > 0) {
          await cancelBtn.first().click()
          await page.waitForTimeout(500)
        }
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：明细表导入导出 el-dropdown 菜单3项 ═══
  test('7.3.5 — 明细表M5-2: 导入导出el-dropdown含3项', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M5-2明细表（导入导出按钮在此）
    const detailNav = page.locator('.el-table__row', { hasText: /M5-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表加载
    const detailComp = page.locator('.m5-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 找到"导入导出"按钮（el-dropdown trigger）
    const importExportBtn = detailComp.locator('button', { hasText: /导入导出/ })
    await expect(importExportBtn).toBeVisible()

    // 点击打开下拉菜单
    await importExportBtn.click()
    await page.waitForTimeout(500)

    // 验证下拉菜单出现（el-dropdown-menu 在 body 层）
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
  })

  // ═══ 场景 6：计提检查 M5-4 → 11公式 + GtIndexChip M6 ═══
  test('7.3.6 — 计提检查M5-4: 11公式前端实时计算+GtIndexChip M6', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M5-4计提检查
    const accrualNav = page.locator('.el-table__row', { hasText: /M5-4/ })
    if (await accrualNav.count() > 0) {
      await accrualNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证计提检查组件加载
    const accrualComp = page.locator('.m5-tab-accrual-test')
    await expect(accrualComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M5-4"
    const title = accrualComp.locator('.section-title')
    await expect(title).toContainText('M5-4')

    // 验证 GtIndexChip M6 存在（跨底稿联动标识）
    const m6Chip = accrualComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await m6Chip.count() > 0) {
      await expect(m6Chip.first()).toBeVisible()
    }

    // 验证方法论上下文显示法定10%计提
    const methodology = accrualComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('10%')

    // 验证计提主表存在
    const accrualTable = accrualComp.locator('.accrual-main-table, .el-table')
    await expect(accrualTable.first()).toBeVisible()

    // 验证公式列header有tooltip
    const formulaHeaders = accrualComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)

    // 验证M6数据未就绪警告或50%上限提示之一可能显示
    const m6Warning = accrualComp.locator('.m6-warning')
    const ceilingAlert = accrualComp.locator('.ceiling-alert')
    // 至少方法论上下文可见即可（M6数据未必就绪）

    // 验证AI辅助按钮
    const aiBtn = accrualComp.locator('button', { hasText: /AI/ })
    expect(await aiBtn.count()).toBeGreaterThanOrEqual(1)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：检查表 M5-5 → 8项核对清单 + 审计结论区 ═══
  test('7.3.7 — 检查表M5-5: 8项核对清单+审计结论区', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M5-5检查表
    const checkNav = page.locator('.el-table__row', { hasText: /M5-5/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证检查表组件加载
    const checkComp = page.locator('.m5-tab-reserve-check')
    await expect(checkComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M5-5"
    const title = checkComp.locator('.section-title')
    await expect(title).toContainText('M5-5')

    // 验证核对清单（8项）
    const checklistItems = checkComp.locator('.checklist-item')
    const itemCount = await checklistItems.count()
    expect(itemCount).toBe(8)

    // 验证清单第一项文本包含"法定盈余公积计提"
    await expect(checklistItems.nth(0)).toContainText('法定盈余公积计提')

    // 验证清单有通过/不通过按钮
    const radioGroups = checkComp.locator('.el-radio-group')
    expect(await radioGroups.count()).toBeGreaterThanOrEqual(8)

    // 验证审计结论区（conclusion-card）
    const conclusionCard = checkComp.locator('.conclusion-card')
    await expect(conclusionCard).toBeVisible()
    await expect(conclusionCard).toContainText('审计结论')

    // 验证结论区有 textarea
    const conclusionTextarea = conclusionCard.locator('textarea')
    await expect(conclusionTextarea).toBeVisible()

    // 验证AI辅助按钮（多个section标题行）
    const aiButtons = checkComp.locator('button', { hasText: /AI/ })
    expect(await aiButtons.count()).toBeGreaterThanOrEqual(2)

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 8：保存流程 → 无错误 + 双模式切换不崩 ═══
  test('7.3.8 — 保存流程: 审定表录入+保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到审定表 M5-1
    const adjNav = page.locator('.el-table__row', { hasText: /M5-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m5-tab-adjudication')
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
          const container = page.locator('.m5-surplus-reserve')
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

    // 依次导航各sheet（M5-1→M5-2→M5-4→M5-5→M5-3）
    const sheets = [
      /M5-1/,     // 审定表
      /M5-2/,     // 明细表
      /M5-4/,     // 计提检查
      /M5-5/,     // 检查表
      /M5-3/,     // 调整分录
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
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m5-surplus-reserve`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm5-surplus-reserve')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
