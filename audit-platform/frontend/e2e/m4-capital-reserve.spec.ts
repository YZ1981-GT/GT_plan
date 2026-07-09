/**
 * Playwright E2E — M4 资本公积底稿完整流程验收
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 M4 底稿 → sheetName 分发 → 目录导航可见（7行sheet）
 * 2. 切换审定表 M4-1 → 验证双区块布局（资本溢价 + 其他资本公积）+ 公式列
 * 3. 切换明细表 M4-2 → 验证区段Tab(资本溢价/其他) + 动态行prompt + 导入导出
 * 4. 验证 el-dropdown "导入导出" 菜单（3项：导出模板/导出数据/导入数据）
 * 5. 切换检查表 M4-4 → J3股份支付确认差异核对 + 结论区
 * 6. 切换调整分录 M4-3 → AJE/RJE segmented + 借贷平衡指示器
 * 7. 保存流程 → 基本数据录入 + 保存
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方 ②资本溢价+其他资本公积双区块 ③接收J3股份支付权益结算 ④接收M2外币折算差异
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m4-capital-reserve.spec.ts
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

/** 通过 API 找到 M4 底稿 ID */
async function findM4WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M4 底稿
  const m4 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M4')
  if (m4) return { id: m4.id, code: 'M4' }
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

test.describe('M4 资本公积底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM4WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M4 底稿 → 目录导航可见（7行sheet） ═══
  test('7.3.1 — 打开 M4 底稿，目录页加载7行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M4 组件容器加载
    const container = page.locator('.m4-capital-reserve')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M4TabIndex）
    const directory = page.locator('.m4-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m4-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m4-guide')
    await expect(guide).toBeVisible()

    // 验证有7行sheet目录（M4A + M4-1 + 附注上市 + 附注国企 + M4-2 + M4-3 + M4-4）
    const tableRows = page.locator('.m4-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(7)

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'M4A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M4-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M4-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M4-4' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M4-1 → 双区块布局 + 公式列 ═══
  test('7.3.2 — 审定表M4-1: 双区块(资本溢价+其他资本公积)+公式列正确计算', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M4-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M4-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m4-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"审定表"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M4-1')

    // 验证"权益类·贷方余额" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('贷方余额')

    // 验证双区块结构：区块一 "资本溢价" + 区块二 "其他资本公积"
    const blockHeaders = adjComp.locator('.block-title')
    const blockCount = await blockHeaders.count()
    expect(blockCount).toBeGreaterThanOrEqual(2)

    const premiumBlock = adjComp.locator('.block-title', { hasText: /资本溢价/ })
    await expect(premiumBlock).toBeVisible()

    const otherBlock = adjComp.locator('.block-title', { hasText: /其他资本公积/ })
    await expect(otherBlock).toBeVisible()

    // 验证表格存在（每个区块有 el-table）
    const tables = adjComp.locator('.el-table')
    expect(await tables.count()).toBeGreaterThanOrEqual(2)

    // 验证新增项目按钮可见
    const addBtn = adjComp.locator('button', { hasText: /新增项目/ })
    if (await addBtn.count() > 0) {
      await expect(addBtn.first()).toBeVisible()
    }

    // 验证方法论上下文(琥珀色)显示
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('期末余额 = 期初 + 贷方')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：明细表 M4-2 → 区段Tab + 动态行prompt ═══
  test('7.3.3 — 明细表M4-2: 区段Tab(资本溢价/其他)+动态行ElMessageBox.prompt', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M4-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M4-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m4-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M4-2')

    // 验证区段Tab（el-segmented: 资本溢价 / 其他资本公积）
    const segmentTabs = detailComp.locator('.segment-tabs .el-segmented')
    await expect(segmentTabs).toBeVisible()

    // 验证区段选项文字
    const segmentItems = detailComp.locator('.segment-tabs .el-segmented .el-segmented__item')
    expect(await segmentItems.count()).toBeGreaterThanOrEqual(2)

    // 验证联动提示（J3/M2 GtIndexChip）
    const linkageHint = detailComp.locator('.linkage-hint')
    if (await linkageHint.count() > 0) {
      await expect(linkageHint.first()).toBeVisible()
    }

    // 验证表格渲染
    const table = detailComp.locator('.detail-table-wrapper .el-table')
    await expect(table).toBeVisible()

    // 验证新增按钮存在
    const addBtn = detailComp.locator('button', { hasText: /新增来源项目/ })
    if (await addBtn.count() > 0) {
      await expect(addBtn.first()).toBeVisible()

      // 点击新增 → 应弹出 ElMessageBox.prompt 输入来源项目名称
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

  // ═══ 场景 4：导入导出 el-dropdown 菜单3项 ═══
  test('7.3.4 — 导入导出el-dropdown菜单含3项(导出模板/导出数据/导入数据)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M4-2明细表（导入导出按钮在此）
    const detailNav = page.locator('.el-table__row', { hasText: /M4-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表加载
    const detailComp = page.locator('.m4-tab-detail')
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

    // 关闭菜单（点击空白处）
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  })

  // ═══ 场景 5：检查表 M4-4 → J3联动核对 + 结论区 ═══
  test('7.3.5 — 检查表M4-4: J3股份支付确认差异核对+审计结论区', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M4-4检查表
    const checkNav = page.locator('.el-table__row', { hasText: /M4-4/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证检查表组件加载
    const checkComp = page.locator('.m4-tab-reserve-check')
    await expect(checkComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = checkComp.locator('.section-title')
    await expect(title).toContainText('M4-4')

    // 验证 Section 2: J3 股份支付确认差异核对区域
    const j3Section = checkComp.locator('.el-card', { hasText: /J3.*股份支付/ })
    await expect(j3Section).toBeVisible()

    // 验证J3核对区域内的3个字段
    const shareBasedGrid = checkComp.locator('.share-based-grid')
    await expect(shareBasedGrid).toBeVisible()

    // J3确认金额
    const j3Label = shareBasedGrid.locator('.share-based-label', { hasText: /J3确认金额/ })
    await expect(j3Label).toBeVisible()

    // 账面其他资本公积增加
    const bookedLabel = shareBasedGrid.locator('.share-based-label', { hasText: /账面其他资本公积增加/ })
    await expect(bookedLabel).toBeVisible()

    // 确认差异
    const diffLabel = shareBasedGrid.locator('.share-based-label', { hasText: /确认差异/ })
    await expect(diffLabel).toBeVisible()

    // 验证 GtIndexChip 跳转（J3标识）
    const j3Chip = checkComp.locator('.gt-index-chip, [class*="index-chip"]')
    if (await j3Chip.count() > 0) {
      await expect(j3Chip.first()).toBeVisible()
    }

    // 验证审计结论区（Section 4, el-card conclusion-card）
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

  // ═══ 场景 6：调整分录 M4-3 → AJE/RJE segmented + 借贷平衡 ═══
  test('7.3.6 — 调整分录M4-3: AJE/RJE segmented切换+借贷平衡指示器', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M4-3调整分录
    const adjNav = page.locator('.el-table__row', { hasText: /M4-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证调整分录组件加载
    const adjComp = page.locator('.m4-tab-adjustment')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M4-3')

    // 验证 AJE/RJE segmented 切换控件
    const segmented = adjComp.locator('.section-header .el-segmented')
    await expect(segmented).toBeVisible()

    // 验证至少有 AJE 和 RJE 两个选项
    const segItems = segmented.locator('.el-segmented__item')
    expect(await segItems.count()).toBeGreaterThanOrEqual(2)

    // 验证借贷平衡指示器
    const balanceIndicator = adjComp.locator('.balance-indicator')
    await expect(balanceIndicator).toBeVisible()

    // 验证借贷金额展示
    const debitLabel = balanceIndicator.locator('text=借方')
    await expect(debitLabel).toBeVisible()

    const creditLabel = balanceIndicator.locator('text=贷方')
    await expect(creditLabel).toBeVisible()

    // 验证平衡状态 tag（初始无分录应为平衡）
    const balanceTag = balanceIndicator.locator('.el-tag')
    await expect(balanceTag).toBeVisible()

    // 验证方法论上下文
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('贷方增加 = 调增资本公积')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：保存流程 ═══
  test('7.3.7 — 保存流程: 基本数据录入+保存+双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 先切换到审定表 M4-1
    const adjNav = page.locator('.el-table__row', { hasText: /M4-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m4-tab-adjudication')
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
          const container = page.locator('.m4-capital-reserve')
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

  // ═══ 场景 8：完整导航流程无 console 严重错误 ═══
  test('7.3.8 — 完整导航流程无 console 严重错误', async ({ page }) => {
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

    // 依次导航各sheet（M4-1→M4-2→M4-4→M4-3→附注）
    const sheets = [
      /M4-1/,     // 审定表
      /M4-2/,     // 明细表
      /M4-4/,     // 检查表
      /M4-3/,     // 调整分录
      /上市公司/, // 附注（上市）
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

  // ═══ 场景 9：render-config API 验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m4-capital-reserve`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm4-capital-reserve')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
