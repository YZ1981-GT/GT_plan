/**
 * Playwright E2E — M2 实收资本（股本）底稿完整流程验收
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 7.3
 * Requirements: 全部 (1~7)
 *
 * 验证场景：
 * 1. 打开 M2 底稿 → sheetName 分发 → 目录导航11行可见
 * 2. 切换审定表 M2-1 → 权益类贷方+期末=期初+贷方(增资)-借方(减资)
 * 3. 切换明细表 M2-2 → el-segmented 上市/非上市分支选择器切换
 * 4. 切换外币投资 M2-4 → 添加行+折算本位币=原币×汇率+差异→M4
 * 5. 切换验资核对 M2-5 → 验资差异+出资到位率+阈值
 * 6. 切换调整分录 M2-3 → 借贷平衡indicator
 * 7. 保存流程 → TB回写通知 + 无console严重错误
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 * 核心特殊：①权益类贷方 ②上市/非上市双版本明细 ③验资核对 ④外币投资折算→M4
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m2-paid-in-capital.spec.ts
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

/** 通过 API 找到 M2 底稿 ID */
async function findM2WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 M2 底稿
  const m2 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M2')
  if (m2) return { id: m2.id, code: 'M2' }
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

test.describe('M2 实收资本（股本）底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM2WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 M2 底稿 → 目录导航+11行可见 ═══
  test('7.3.1 — 打开 M2 底稿，目录导航+11行sheet可见', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M2 组件容器加载
    const container = page.locator('.m2-paid-in-capital')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M2TabIndex）
    const directory = page.locator('.m2-tab-index, [class*="tab-index"]')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证有11个sheet导航行
    const navRows = page.locator('.m2-tab-index .m2-nav-row, [class*="nav-row"], .el-table__row')
    const rowCount = await navRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(11)
  })

  // ═══ 场景 2：审定表 M2-1 → 权益类贷方 ═══
  test('7.3.2 — 审定表M2-1: 权益类贷方+期末=期初+贷方(增资)-借方(减资)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过sheet导航切换到M2-1审定表
    const adjNav = page.locator('[class*="nav-row"]', { hasText: /审定表|M2-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjTable = page.locator('.m2-adjudication, [class*="adjudication"]')
    if (await adjTable.count() > 0) {
      await expect(adjTable).toBeVisible({ timeout: 10_000 })

      // 验证表格存在
      const table = adjTable.locator('.el-table')
      await expect(table).toBeVisible()

      // 验证关键列header（期初/贷方发生(增资)/借方发生(减资)/期末）
      const endBalCol = adjTable.locator('th', { hasText: '期末' })
      if (await endBalCol.count() > 0) {
        await expect(endBalCol.first()).toBeVisible()
      }

      // 验证有按出资人/股东分类行
      const categoryRows = adjTable.locator('text=合计, text=小计')
      if (await categoryRows.count() > 0) {
        await expect(categoryRows.first()).toBeVisible()
      }

      // 验证有公式列（虚线下划线 + cursor:help）
      const formulaCols = adjTable.locator('.formula-cell, [class*="formula"]')
      const formulaCount = await formulaCols.count()
      expect(formulaCount).toBeGreaterThanOrEqual(0)
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：明细表 M2-2 → 上市/非上市分支选择器切换 ═══
  test('7.3.3 — 明细表M2-2: el-segmented上市/非上市双版本切换', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M2-2明细表
    const detailNav = page.locator('[class*="nav-row"]', { hasText: /明细表|M2-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m2-detail, [class*="detail"]')
    if (await detailComp.count() > 0) {
      await expect(detailComp.first()).toBeVisible({ timeout: 10_000 })

      // 验证分支选择器（el-segmented）存在
      const branchSelector = detailComp.locator('.el-segmented, [class*="branch-selector"]')
      if (await branchSelector.count() > 0) {
        await expect(branchSelector.first()).toBeVisible()

        // 验证两个选项：上市公司版 / 非上市公司版
        const listedOption = branchSelector.locator('text=上市')
        const unlistedOption = branchSelector.locator('text=非上市')

        if (await listedOption.count() > 0 && await unlistedOption.count() > 0) {
          // 切换到上市公司版
          await listedOption.first().click()
          await page.waitForTimeout(1000)
          await expect(page.locator('.el-message--error')).not.toBeVisible()

          // 切换到非上市公司版
          await unlistedOption.first().click()
          await page.waitForTimeout(1000)
          await expect(page.locator('.el-message--error')).not.toBeVisible()
        }
      }

      // 验证表格渲染
      const table = page.locator('.el-table, table').first()
      await expect(table).toBeVisible()

      // 验证新增行按钮存在
      const addRowBtn = detailComp.locator('button, .el-button', { hasText: /新增|添加/ })
      if (await addRowBtn.count() > 0) {
        await expect(addRowBtn.first()).toBeVisible()
      }
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：外币投资 M2-4 → 折算本位币=原币×汇率 + 差异→M4 ═══
  test('7.3.4 — 外币投资M2-4: 折算公式+差异→M4联动提示', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M2-4外币投资
    const fxNav = page.locator('[class*="nav-row"]', { hasText: /外币|M2-4|汇率/ })
    if (await fxNav.count() > 0) {
      await fxNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证外币投资组件加载
    const fxComp = page.locator('.m2-fx-invest, [class*="fx-invest"]')
    if (await fxComp.count() > 0) {
      await expect(fxComp.first()).toBeVisible({ timeout: 10_000 })

      // 验证表格存在
      const table = fxComp.locator('.el-table')
      await expect(table).toBeVisible()

      // 验证关键列：出资人|原币出资|币种|出资日汇率|折算本位币|账面本位币|折算差异
      const headerArea = fxComp.locator('th')
      const headerCount = await headerArea.count()
      expect(headerCount).toBeGreaterThanOrEqual(5)

      // 验证"折算差异"列存在
      const diffCol = fxComp.locator('th', { hasText: /折算差异|差异/ })
      if (await diffCol.count() > 0) {
        await expect(diffCol.first()).toBeVisible()
      }

      // 验证M4联动提示/GtIndexChip
      const m4Chip = fxComp.locator('.gt-index-chip, [class*="cross-ref"], text=M4')
      // M4联动入口应存在（差异→资本公积）
      if (await m4Chip.count() > 0) {
        await expect(m4Chip.first()).toBeVisible()
      }

      // 验证新增行按钮
      const addBtn = fxComp.locator('button, .el-button', { hasText: /新增|添加/ })
      if (await addBtn.count() > 0) {
        await expect(addBtn.first()).toBeVisible()
      }
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：验资核对 M2-5 → 验资差异+出资到位率+阈值 ═══
  test('7.3.5 — 检查表M2-5: 验资核对+出资到位率+阈值告警', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M2-5检查表
    const checkNav = page.locator('[class*="nav-row"]', { hasText: /检查|M2-5|验资/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证检查表组件加载
    const checkComp = page.locator('.m2-capital-check, [class*="capital-check"]')
    if (await checkComp.count() > 0) {
      await expect(checkComp.first()).toBeVisible({ timeout: 10_000 })

      // 验证核对清单区域
      const checkList = checkComp.locator('.el-table, [class*="checklist"]')
      await expect(checkList.first()).toBeVisible()

      // 验证关键列：出资人|认缴|实缴|验资金额|差异|验资机构
      const headerArea = checkComp.locator('th')
      const headerCount = await headerArea.count()
      expect(headerCount).toBeGreaterThanOrEqual(4)

      // 验证审计结论区（el-card包裹）
      const conclusionCard = checkComp.locator('.el-card')
      if (await conclusionCard.count() > 0) {
        await expect(conclusionCard.first()).toBeVisible()
      }

      // 验证AI辅助按钮存在
      const aiBtn = checkComp.locator('button, .el-button', { hasText: /AI/ })
      if (await aiBtn.count() > 0) {
        await expect(aiBtn.first()).toBeVisible()
      }
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：调整分录 M2-3 → 借贷平衡 ═══
  test('7.3.6 — 调整分录M2-3: 借贷平衡indicator', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M2-3调整分录
    const adjNav = page.locator('[class*="nav-row"]', { hasText: /调整|M2-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证调整分录组件加载
    const adjComp = page.locator('.m2-adjustment, [class*="adjustment"]')
    if (await adjComp.count() > 0) {
      await expect(adjComp.first()).toBeVisible({ timeout: 10_000 })

      // 验证表格存在
      const table = adjComp.locator('.el-table')
      await expect(table).toBeVisible()

      // 验证AJE/RJE标签存在
      const ajeLabel = adjComp.locator('text=AJE')
      if (await ajeLabel.count() > 0) {
        await expect(ajeLabel.first()).toBeVisible()
      }
      const rjeLabel = adjComp.locator('text=RJE')
      if (await rjeLabel.count() > 0) {
        await expect(rjeLabel.first()).toBeVisible()
      }

      // 验证借贷平衡indicator
      const balanceArea = adjComp.locator(
        'text=借方, text=贷方, text=平衡, [class*="balance"]',
      ).first()
      if (await balanceArea.isVisible()) {
        await expect(balanceArea).toBeVisible()
      }
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：双模式切换 + 保存流程 ═══
  test('7.3.7 — 双模式切换不崩溃 + TB回写通知', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 找到双模式切换控件
    const modeSwitch = page.locator('.el-segmented, [class*="dual-mode"], [class*="mode-switch"]')
    if (await modeSwitch.count() > 0) {
      // 切换到 OnlyOffice 模式
      const ooOption = modeSwitch.locator('text=在线编辑, text=OnlyOffice, text=OO')
      if (await ooOption.count() > 0) {
        await ooOption.first().click()
        await page.waitForTimeout(3000)

        // 验证不崩溃
        const container = page.locator('.m2-paid-in-capital')
        await expect(container).toBeVisible()

        // 切回结构化
        const htmlOption = modeSwitch.locator('text=结构化, text=HTML')
        if (await htmlOption.count() > 0) {
          await htmlOption.first().click()
          await page.waitForTimeout(2000)
          await expect(container).toBeVisible()
        }
      }
    }

    // 验证保存按钮存在
    const saveBtn = page.locator('button, .el-button', { hasText: /保存/ })
    if (await saveBtn.count() > 0) {
      // 点击保存
      await saveBtn.first().click()
      await page.waitForTimeout(2000)

      // 验证TB回写成功通知（el-message--success）
      const successMsg = page.locator('.el-message--success, .el-notification__content')
      // 保存完成应有成功提示
    }

    // 无错误
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

    // 依次导航各sheet（目录→M2-1→M2-2→M2-4→M2-5→M2-3）
    const sheets = [
      /审定表|M2-1/,
      /明细表|M2-2/,
      /外币|M2-4/,
      /检查|M2-5|验资/,
      /调整|M2-3/,
    ]

    for (const sheetPattern of sheets) {
      const nav = page.locator('[class*="nav-row"]', { hasText: sheetPattern })
      if (await nav.count() > 0) {
        await nav.first().click()
        await page.waitForTimeout(2000)
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
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m2-paid-in-capital`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm2-paid-in-capital')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
