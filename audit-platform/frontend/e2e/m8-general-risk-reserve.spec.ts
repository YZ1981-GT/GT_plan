/**
 * Playwright E2E — M8 一般风险准备底稿完整流程验收
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 7.3
 * Requirements: 全部 (1~6)
 *
 * 验证场景：
 * 1. 打开 M8 底稿 → sheetName 分发 → 底稿目录渲染7行sheet
 * 2. 切换审定表 M8-1 → 验证权益类badge "权益类·贷方余额·4104"
 * 3. 验证公式列虚线下划线(cursor:help) + 编辑AJE验证审定数重算
 * 4. 切换明细表 M8-2 → 验证分组列头 + 动态行新增(ElMessageBox.prompt)
 * 5. 切换风险测试 M8-4 → 验证比例1.5%默认 + 应计金额公式 + 差异颜色
 * 6. 切换调整分录 M8-3 → 新增分录 + 借贷平衡校验
 * 7. 保存流程 → 无错误
 *
 * 科目：4104一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心特殊：①权益类贷方 ②金融企业行业守卫 ③按风险资产1.5%计提测试
 *
 * 前置：后端 9980 + 前端 3030 需运行中（start-dev.bat）
 * 运行：rtk npx playwright test e2e/m8-general-risk-reserve.spec.ts
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

/** 通过 API 找到 M8 底稿 ID */
async function findM8WpId(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; code: string } | null> {
  const resp = await request.get(`${BASE_URL}/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
    params: { page_size: 500 },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])

  const m8 = list.find((w: any) => (w.wp_code || '').toUpperCase() === 'M8')
  if (m8) return { id: m8.id, code: 'M8' }
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

test.describe('M8 一般风险准备底稿 E2E 流程（Task 7.3）', () => {
  let wpId: string

  test.beforeAll(async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const wp = await findM8WpId(request, token)
    if (!wp) {
      test.skip()
      return
    }
    wpId = wp.id
  })

  // ═══ 场景 1：打开 M8 底稿 → 底稿目录渲染7行sheet ═══
  test('7.3.1 — 打开 M8 底稿，底稿目录渲染7行sheet', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 验证 M8 组件容器加载
    const container = page.locator('.m8-general-risk-reserve')
    await expect(container).toBeVisible({ timeout: 15_000 })

    // 验证目录视图（M8TabIndex）
    const directory = page.locator('.m8-tab-index')
    await expect(directory).toBeVisible({ timeout: 10_000 })

    // 验证"权益类贷方科目"醒目标注
    const equityBadge = page.locator('.m8-equity-badge')
    await expect(equityBadge).toBeVisible()
    await expect(equityBadge).toContainText('权益类贷方科目')

    // 验证操作引导区
    const guide = page.locator('.m8-guide')
    await expect(guide).toBeVisible()

    // 验证有7行sheet目录（M8A+M8-1+附注上市+附注国企+M8-2+M8-3+M8-4）
    const tableRows = page.locator('.m8-tab-index .el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount).toBe(7)

    // 验证关键底稿编码列存在
    await expect(page.locator('.el-table__row', { hasText: 'M8A' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M8-1' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M8-2' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M8-3' })).toBeVisible()
    await expect(page.locator('.el-table__row', { hasText: 'M8-4' })).toBeVisible()
  })

  // ═══ 场景 2：审定表 M8-1 → 权益类badge + 公式列虚线下划线 ═══
  test('7.3.2 — 审定表M8-1: 权益类badge可见 + 公式列cursor:help', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 通过目录导航切换到M8-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M8-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件加载
    const adjComp = page.locator('.m8-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M8-1"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M8-1')

    // 验证"权益类·贷方余额·4104" badge
    const badge = adjComp.locator('.equity-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toContainText('权益类·贷方余额·4104')

    // 验证公式列header有dashed underline (cursor:help)
    const formulaHeaders = adjComp.locator('.formula-col-header')
    expect(await formulaHeaders.count()).toBeGreaterThanOrEqual(1)
    // 验证cursor:help的CSS样式
    const firstFormulaHeader = formulaHeaders.first()
    const cursor = await firstFormulaHeader.evaluate(
      (el) => window.getComputedStyle(el).cursor,
    )
    expect(cursor).toBe('help')

    // 验证方法论上下文(琥珀色)
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('期末余额')

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 3：审定表M8-1 AJE编辑→审定数重算 ═══
  test('7.3.3 — 审定表M8-1: 编辑AJE值验证审定数自动重算', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M8-1审定表
    const adjNav = page.locator('.el-table__row', { hasText: /M8-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m8-tab-adjudication')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证表格列头包含审定相关列
    await expect(adjComp.locator('th', { hasText: /期末未审/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /期末AJE/ })).toBeVisible()
    await expect(adjComp.locator('th', { hasText: /期末审定/ })).toBeVisible()

    // 找到第一个数据行的期末AJE输入框并编辑
    const ajeInputs = adjComp.locator('.el-table__body .el-input-number input')
    if (await ajeInputs.count() > 0) {
      // 获取编辑前的审定数值（.formula-value）
      const formulaValues = adjComp.locator('.formula-value')
      const beforeText = await formulaValues.first().textContent()

      // 在第一个输入框中输入一个测试值
      const firstInput = ajeInputs.first()
      await firstInput.click()
      await firstInput.fill('1000')
      await firstInput.press('Tab')
      await page.waitForTimeout(500)

      // 验证审定数有变化（公式列自动重算）
      // 公式列(.formula-value)应该反映新的计算
      const afterText = await formulaValues.first().textContent()
      // 如果初始值为0，输入1000后审定数应该变化
      if (beforeText === '0' || beforeText === '—') {
        expect(afterText).not.toBe(beforeText)
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 4：明细表 M8-2 → 分组列头 + 动态行新增 ═══
  test('7.3.4 — 明细表M8-2: 分组列头可见 + 动态行新增(ElMessageBox.prompt)', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M8-2明细表
    const detailNav = page.locator('.el-table__row', { hasText: /M8-2/ })
    if (await detailNav.count() > 0) {
      await detailNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件加载
    const detailComp = page.locator('.m8-tab-detail')
    await expect(detailComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M8-2"
    const title = detailComp.locator('.section-title')
    await expect(title).toContainText('M8-2')

    // 验证分组列头（未审数/期初调整/账项调整/重分类调整/审定数）
    await expect(detailComp.locator('th', { hasText: /未审数/ })).toBeVisible()
    await expect(detailComp.locator('th', { hasText: /期初调整/ })).toBeVisible()

    // 验证导入导出按钮存在
    const importExportBtn = detailComp.locator('button', { hasText: /导入导出/ })
    await expect(importExportBtn).toBeVisible()

    // 验证"新增明细项目"按钮存在
    const addBtn = detailComp.locator('button', { hasText: /新增明细项目/ })
    await expect(addBtn).toBeVisible()

    // 点击新增按钮 → 应弹出 ElMessageBox.prompt 输入名称
    await addBtn.click()
    await page.waitForTimeout(1000)

    // 验证 MessageBox prompt 弹出
    const msgBox = page.locator('.el-message-box')
    await expect(msgBox).toBeVisible({ timeout: 5_000 })

    // 输入名称并确认
    const promptInput = msgBox.locator('input')
    if (await promptInput.count() > 0) {
      await promptInput.fill('测试明细项目E2E')
      const confirmBtn = msgBox.locator('.el-message-box__btns button', { hasText: /确定/ })
      await confirmBtn.click()
      await page.waitForTimeout(1000)
    } else {
      // 关闭弹窗（取消）
      const cancelBtn = msgBox.locator('.el-message-box__btns button', { hasText: /取消/ })
      if (await cancelBtn.count() > 0) await cancelBtn.click()
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 5：风险测试 M8-4 → 比例1.5%默认 + 应计金额公式 + 差异颜色 ═══
  test('7.3.5 — 风险测试M8-4: 比例1.5%默认 + 应计金额G=E×F + 差异颜色', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M8-4风险测试
    const riskNav = page.locator('.el-table__row', { hasText: /M8-4/ })
    if (await riskNav.count() > 0) {
      await riskNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证风险测试组件加载
    const riskComp = page.locator('.m8-tab-risk-test')
    await expect(riskComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M8-4"
    const title = riskComp.locator('.section-title')
    await expect(title).toContainText('M8-4')

    // 验证方法论上下文(琥珀色)显示1.5%计提标准
    const methodology = riskComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('1.5%')

    // 验证比例列头（含tooltip提示）
    await expect(riskComp.locator('.formula-col-header', { hasText: /比例/ })).toBeVisible()

    // 验证应计金额公式列头
    await expect(riskComp.locator('.formula-col-header', { hasText: /应计金额/ })).toBeVisible()

    // 验证差异列头
    await expect(riskComp.locator('.formula-col-header', { hasText: /差异/ })).toBeVisible()

    // 编辑一个风险资产期末余额值，验证应计金额公式重算
    const riskAssetInputs = riskComp.locator('.el-table__body .el-input-number input')
    if (await riskAssetInputs.count() >= 3) {
      // 找到风险资产期末余额输入（通常在第5列左右）
      // 先找到E列输入
      const eColInputs = riskComp.locator(
        '.el-table__body tr:first-child .el-input-number input',
      )
      if (await eColInputs.count() > 0) {
        // 输入测试值 10000
        const input = eColInputs.nth(2) // 第3个输入大约对应E列
        await input.click()
        await input.fill('10000')
        await input.press('Tab')
        await page.waitForTimeout(500)

        // 验证应计金额(.formula-value)出现非零值
        const formulaValues = riskComp.locator('.formula-value')
        const hasNonZero = await formulaValues.evaluateAll((els) =>
          els.some((el) => {
            const text = el.textContent || ''
            return text !== '—' && text !== '0' && text !== '0.00'
          }),
        )
        // 如果有输入，应该有计算结果
        expect(hasNonZero || (await eColInputs.count()) === 0).toBeTruthy()
      }
    }

    // 验证计提充足性结论区域
    const footer = riskComp.locator('.provision-footer')
    await expect(footer).toBeVisible()

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 6：调整分录 M8-3 → 新增分录 + 借贷平衡 ═══
  test('7.3.6 — 调整分录M8-3: 新增分录 + 借贷平衡状态', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到M8-3调整分录
    const adjNav = page.locator('.el-table__row', { hasText: /M8-3/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    // 验证调整分录组件加载
    const adjComp = page.locator('.m8-tab-adjustment')
    await expect(adjComp).toBeVisible({ timeout: 10_000 })

    // 验证标题含"M8-3"
    const title = adjComp.locator('.section-title')
    await expect(title).toContainText('M8-3')

    // 验证借贷平衡标签
    const balanceTag = adjComp.locator('.el-tag', { hasText: /借贷平衡/ })
    await expect(balanceTag).toBeVisible()

    // 验证方法论上下文
    const methodology = adjComp.locator('.methodology-context')
    await expect(methodology).toBeVisible()
    await expect(methodology).toContainText('借贷平衡')

    // 验证AJE/RJE切换存在
    const typeSwitch = adjComp.locator('.type-switch .el-segmented')
    await expect(typeSwitch).toBeVisible()

    // 验证"新增分录"按钮存在
    const addBtn = adjComp.locator('button', { hasText: /新增分录/ })
    await expect(addBtn).toBeVisible()

    // 点击新增分录
    await addBtn.click()
    await page.waitForTimeout(1000)

    // 验证没有错误消息
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ═══ 场景 7：保存流程 → 无错误 + 双模式切换不崩 ═══
  test('7.3.7 — 保存流程: 审定表保存 + 双模式切换不崩溃', async ({ page }) => {
    test.setTimeout(45_000)
    await loginAs(page)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)

    // 切换到审定表 M8-1
    const adjNav = page.locator('.el-table__row', { hasText: /M8-1/ })
    if (await adjNav.count() > 0) {
      await adjNav.first().click()
      await page.waitForTimeout(2000)
    }

    const adjComp = page.locator('.m8-tab-adjudication')
    if (await adjComp.count() > 0) {
      // 验证双模式切换（el-segmented: 结构化/OO）
      const modeSwitch = page.locator('.mode-toggle-bar .el-segmented').first()
      if (await modeSwitch.count() > 0) {
        const modeItems = modeSwitch.locator('.el-segmented__item')
        if (await modeItems.count() >= 2) {
          // 切换到第二个模式（OO）
          await modeItems.nth(1).click()
          await page.waitForTimeout(2000)

          // 验证组件没崩
          const container = page.locator('.m8-general-risk-reserve')
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

    // 依次导航各sheet（M8-1→M8-2→M8-4→M8-3）
    const sheets = [
      /M8-1/,     // 审定表
      /M8-2/,     // 明细表
      /M8-4/,     // 风险测试
      /M8-3/,     // 调整分录
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
    expect(
      criticalErrors,
      `控制台严重错误:\n${criticalErrors.join('\n')}`,
    ).toHaveLength(0)
  })

  // ═══ 场景 9：render-config API 验证 ═══
  test('render-config API 返回正确组件类型', async ({ request }) => {
    const tokenResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    })
    const tokenBody = await tokenResp.json()
    const token = tokenBody.data?.access_token ?? tokenBody.access_token

    const renderResponse = await request.get(
      `${BASE_URL}/api/workpapers/test-wp/render-config?force_component_type=m8-general-risk-reserve`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'm8-general-risk-reserve')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
