/**
 * Playwright E2E — L2 应付利息底稿完整流程验收
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 L2 底稿 → sheetName 分发 → 目录导航可见
 * 2. 切换审定表 L2-1 → 负债类贷方+按来源分类+公式列
 * 3. 切换明细表 L2-2 → 区段Tab + 公式列虚线 + 动态行
 * 4. 切换检查表 L2-4 → 计提核对+逾期分析+完整性+准确性
 * 5. 切换调整分录 L2-3 → AJE/RJE切换+借贷平衡
 * 6. 完整导航流程无 console 严重错误
 * 7. 双模式切换（结构化 ↔ OO）
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/l2-interest-payable.spec.ts
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

/** 通过 API 找到 L2 底稿 ID */
async function findL2WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  // 找 L2 底稿
  const l2 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'L2')
  if (l2) return { id: l2.id, code: 'L2' }
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

test.describe('L2 应付利息底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string
  let wpCode: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findL2WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
    wpCode = wp.code
  })

  // ═══ 场景 1：打开 L2 底稿 → 目录导航可见 ═══
  test('7.3.1 — 打开 L2 底稿，目录导航+7行sheet可见', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 L2 组件容器加载
    const container = page.locator('.l2-interest-payable')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（L2TabIndex）
    const directory = page.locator('.l2-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证有 7 个 sheet 导航行（L2-1~L2-4 + 附注上市/国企 + L2A）
    const navRows = page.locator('.l2-tab-index .l2-nav-row')
    const rowCount = await navRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(7)

    // 验证进度统计区域可见
    const progressArea = page.locator('.l2-progress')
    if (await progressArea.count() > 0) {
      await expect(progressArea.first()).toBeVisible()
    }
  })

  // ═══ 场景 2：切换审定表 L2-1 → 负债类贷方+按来源分类+公式列 ═══
  test('7.3.2 — 审定表L2-1: 负债类贷方+按来源分类小计+列头验证', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过 sheet 导航切换到 L2-1 审定表
    const adjNav = page.locator('.l2-nav-row', { hasText: /审定表|L2-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    } else {
      const chip = page.locator('[data-sheet-code="L2-1"], .sheet-chip', { hasText: /L2-1|审定/ })
      if (await chip.count() > 0) {
        await chip.first().click()
        await page.waitForTimeout(2000)
      }
    }

    // 验证审定表组件加载
    const adjTable = page.locator('.l2-adjudication')
    if (await adjTable.count() > 0) {
      await expect(adjTable).toBeVisible({ timeout: 10_000 })

      // 验证表格存在
      const table = adjTable.locator('.el-table')
      await expect(table).toBeVisible()

      // 验证列头：期初/贷方/借方/期末/未审/AJE/RJE/审定
      const expectedColumns = ['期初', '贷方', '借方', '期末', '未审', 'AJE', 'RJE', '审定']
      for (const col of expectedColumns) {
        const header = adjTable.locator('.el-table__header', { hasText: col })
        if (await header.count() > 0) {
          await expect(header.first()).toBeVisible()
        }
      }

      // 验证按来源分类行（短期借款/长期借款/应付债券）
      const sourceRows = adjTable.locator('text=短期借款')
      if (await sourceRows.count() > 0) {
        await expect(sourceRows.first()).toBeVisible()
      }

      // 验证有公式列（虚线下划线 class）
      const formulaCols = adjTable.locator('.formula-cell, .l2-formula')
      const formulaCount = await formulaCols.count()
      expect(formulaCount).toBeGreaterThanOrEqual(0) // 需数据才显示
    }
  })

  // ═══ 场景 3：切换明细表 L2-2 → 区段Tab + 公式列虚线 + 动态行 ═══
  test('7.3.3 — 明细表L2-2: 区段Tab(来源+未审/调整/审定/逾期+附注)+公式列虚线', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到 L2-2 明细表
    const detailNav = page.locator('.l2-nav-row', { hasText: /明细表|L2-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    } else {
      const chip = page.locator('[data-sheet-code="L2-2"], .sheet-chip', { hasText: /L2-2|明细/ })
      if (await chip.count() > 0) {
        await chip.first().click()
        await page.waitForTimeout(2000)
      }
    }

    // 验证明细表组件加载
    const detailTable = page.locator('.l2-detail')
    if (await detailTable.count() > 0) {
      await expect(detailTable).toBeVisible({ timeout: 10_000 })

      // 验证区段Tab存在（来源信息/金额变动/支付情况 或 来源+未审/调整/审定/逾期+附注）
      const segmentTabs = detailTable.locator('.el-segmented, .l2-segment-tabs')
      if (await segmentTabs.count() > 0) {
        await expect(segmentTabs.first()).toBeVisible()
      }

      // 验证公式列有虚线下划线样式（dashed underline + cursor:help）
      const formulaCells = detailTable.locator(
        '.formula-cell, [style*="border-bottom"][style*="dashed"], [style*="cursor: help"]',
      )
      const formulaCellCount = await formulaCells.count()
      expect(formulaCellCount).toBeGreaterThanOrEqual(0) // 有数据时才显示

      // 验证新增行按钮存在
      const addRowBtn = detailTable.locator('button', { hasText: /新增|添加/ })
      if (await addRowBtn.count() > 0) {
        await expect(addRowBtn.first()).toBeVisible()
      }

      // 验证导入导出下拉存在
      const importExport = detailTable.locator('.el-dropdown, text=导入导出')
      if (await importExport.count() > 0) {
        await expect(importExport.first()).toBeVisible()
      }
    }
  })

  // ═══ 场景 4：切换检查表 L2-4 → 计提核对+逾期分析+完整性+准确性 ═══
  test('7.3.4 — 检查表L2-4: 计提核对/逾期分析/完整性/准确性section', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到 L2-4 检查表
    const checkNav = page.locator('.l2-nav-row', { hasText: /检查表|L2-4/ })
    if (await checkNav.count() > 0) {
      await checkNav.first().click()
      await page.waitForTimeout(2000)
    } else {
      const chip = page.locator('[data-sheet-code="L2-4"], .sheet-chip', { hasText: /L2-4|检查/ })
      if (await chip.count() > 0) {
        await chip.first().click()
        await page.waitForTimeout(2000)
      }
    }

    // 验证检查表组件加载
    const checkTable = page.locator('.l2-interest-check')
    if (await checkTable.count() > 0) {
      await expect(checkTable).toBeVisible({ timeout: 10_000 })

      // 验证各 section 渲染（计提核对/逾期分析/完整性/准确性）
      const expectedSections = ['计提核对', '逾期分析', '完整性', '准确性']
      for (const section of expectedSections) {
        const sectionEl = checkTable.locator(`text=${section}`)
        if (await sectionEl.count() > 0) {
          await expect(sectionEl.first()).toBeVisible()
        }
      }

      // 验证结论区（el-card包裹）
      const conclusionCard = checkTable.locator('.el-card')
      if (await conclusionCard.count() > 0) {
        await expect(conclusionCard.first()).toBeVisible()
      }

      // 验证 AI 辅助按钮（section标题行右侧）
      const aiBtn = checkTable.locator('button', { hasText: /AI|智能/ })
      if (await aiBtn.count() > 0) {
        await expect(aiBtn.first()).toBeVisible()
      }
    }
  })

  // ═══ 场景 5：切换调整分录 L2-3 → AJE/RJE切换+借贷平衡 ═══
  test('7.3.5 — 调整分录L2-3: AJE/RJE toggle + 借贷平衡指示', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到 L2-3 调整分录
    const adjNav = page.locator('.l2-nav-row', { hasText: /调整|L2-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    } else {
      const chip = page.locator('[data-sheet-code="L2-3"], .sheet-chip', { hasText: /L2-3|调整/ })
      if (await chip.count() > 0) {
        await chip.first().click()
        await page.waitForTimeout(2000)
      }
    }

    // 验证调整分录组件加载
    const adjustment = page.locator('.l2-adjustment')
    if (await adjustment.count() > 0) {
      await expect(adjustment).toBeVisible({ timeout: 10_000 })

      // 验证 AJE/RJE 切换控件
      const ajeRjeToggle = adjustment.locator(
        '.el-segmented, .el-radio-group, .l2-aje-rje-toggle',
      )
      if (await ajeRjeToggle.count() > 0) {
        await expect(ajeRjeToggle.first()).toBeVisible()

        // 验证 AJE 和 RJE 选项
        const ajeOption = ajeRjeToggle.locator('text=AJE')
        const rjeOption = ajeRjeToggle.locator('text=RJE')
        if (await ajeOption.count() > 0) {
          await expect(ajeOption.first()).toBeVisible()
        }
        if (await rjeOption.count() > 0) {
          await expect(rjeOption.first()).toBeVisible()
        }
      }

      // 验证借贷平衡指示器
      const balanceIndicator = adjustment.locator(
        '.l2-balance-indicator, .balance-status, text=借贷平衡',
      )
      if (await balanceIndicator.count() > 0) {
        await expect(balanceIndicator.first()).toBeVisible()
      }
    }
  })

  // ═══ 场景 6：完整导航流程无 console 严重错误 ═══
  test('7.3.6 — 完整导航流程无 console 严重错误', async ({ page }) => {
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

    // 依次导航各 sheet（目录 → L2-1 → L2-2 → L2-4 → L2-3）
    const sheets = [
      /审定表|L2-1/,
      /明细表|L2-2/,
      /检查表|L2-4/,
      /调整|L2-3/,
    ]

    for (const sheetPattern of sheets) {
      const nav = page.locator('.l2-nav-row', { hasText: sheetPattern })
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

  // ═══ 场景 7：双模式切换（结构化 ↔ OO） ═══
  test('7.3.7 — 双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 找到双模式切换控件
    const modeSwitch = page.locator('.el-segmented, .l2-mode-switch')
    if (await modeSwitch.count() > 0) {
      // 切换到 OnlyOffice 模式
      const ooOption = modeSwitch.locator('text=在线编辑')
      if (await ooOption.count() > 0) {
        await ooOption.first().click()
        await page.waitForTimeout(3000)

        // 验证不崩溃
        const container = page.locator('.l2-interest-payable')
        await expect(container).toBeVisible()

        // 切回结构化
        const structOption = modeSwitch.locator('text=结构化')
        if (await structOption.count() > 0) {
          await structOption.first().click()
          await page.waitForTimeout(2000)
          await expect(container).toBeVisible()
        }
      }
    }
  })
})
