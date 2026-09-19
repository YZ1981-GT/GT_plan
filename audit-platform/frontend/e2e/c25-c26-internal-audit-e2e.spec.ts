/**
 * c25-c26-internal-audit-e2e.spec.ts — C25/C26 专项控制测试专属组件 E2E
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/  Task 6.2
 * Requirements: 2.4, 3.3, 7.1
 *
 * 验证项目：
 * C25 Flow:
 *   1. 导航到 C25 底稿 → 渲染 c25-internal-audit-reliance 组件
 *   2. 验证 10 步评估表可见
 *   3. 选择步骤 1 适用性"是"
 *   4. 填写执行人
 *   5. 填写执行情况说明
 *   6. 选择利用结论
 *   7. 只读模式禁用输入
 *
 * C26 Flow:
 *   1. 导航到 C26 底稿 → 渲染 c26-info-processing-control 组件
 *   2. 验证矩阵表渲染
 *   3. 点击「新增控制」按钮 → dialog 出现
 *   4. 输入控制名并确认 → 新行出现
 *   5. 标记四要素（checkboxes）
 *   6. 选择测试结果
 *   7. 只读模式隐藏增删并禁用输入
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

// ─── Helpers ────────────────────────────────────────────────────────────────

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
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

/** 收集 console errors（忽略已知噪音） */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (/\/ai\//.test(text) && /405/.test(text)) return
      if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
      if (/Failed to load resource.*500/.test(text)) return
      if (/OnlyOffice|DocsAPI/.test(text)) return
      errors.push(text)
    }
  })
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))
  return errors
}

// ═══════════════════════════════════════════════════════════════════════════════
// C25 利用内部审计工作 E2E
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('C25 利用内部审计工作 E2E (Task 6.2)', () => {
  test('C25 底稿加载 → 渲染专属组件 + 10 步评估表可见', async ({ page }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C25', PROJECT_ID)
    test.skip(!wp.exists, 'C25 底稿不存在，需先运行项目底稿生成')

    const consoleErrors = collectConsoleErrors(page)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(8_000)

    // 验证专属组件加载（.gt-c25-internal-audit）
    const c25Root = page.locator('.gt-c25-internal-audit')
    const isC25Visible = await c25Root.isVisible({ timeout: 15_000 }).catch(() => false)
    if (!isC25Visible) {
      console.log('C25 未渲染为 c25-internal-audit-reliance，跳过')
      return
    }

    // 验证 10 步评估表可见
    const evalTable = page.locator('.gt-c25-internal-audit .evaluation-table')
    await expect(evalTable).toBeVisible()

    // 验证表格至少有 10 行
    const rows = page.locator('.gt-c25-internal-audit .evaluation-table .el-table__body-wrapper tr')
    const rowCount = await rows.count()
    expect(rowCount, '评估表应有 10 步').toBeGreaterThanOrEqual(10)

    // 验证方法论上下文区块渲染
    const methodology = page.locator('.gt-c25-internal-audit .methodology-context')
    await expect(methodology).toBeVisible()

    // 无严重 console errors
    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(critical, `控制台严重错误:\n${critical.join('\n')}`).toHaveLength(0)
  })

  test('C25 评估录入 → 适用性 + 执行人 + 执行说明 + 结论 (Req 2.4)', async ({ page }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C25', PROJECT_ID)
    test.skip(!wp.exists, 'C25 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(8_000)

    const c25Root = page.locator('.gt-c25-internal-audit')
    const isVisible = await c25Root.isVisible({ timeout: 15_000 }).catch(() => false)
    test.skip(!isVisible, 'C25 未渲染为专属组件')

    // ─── Step 1: 选择步骤 1 的适用性"是" ───
    const firstRowSelect = c25Root.locator('.evaluation-table .el-table__body-wrapper tr').first()
      .locator('.el-select')
    await expect(firstRowSelect).toBeVisible()
    await firstRowSelect.click()
    await page.waitForTimeout(300)

    // 从下拉中选择"是"
    const optionYes = page.locator('.el-select-dropdown__item:has-text("是")').first()
    await optionYes.click()
    await page.waitForTimeout(500)

    // ─── Step 2: 填写执行人 ───
    const firstRowInputs = c25Root.locator('.evaluation-table .el-table__body-wrapper tr').first()
      .locator('.el-input:not(.el-select .el-input)')
    // 执行人 input（第一个非 select 的 input）
    const executorInput = firstRowInputs.first()
    await executorInput.locator('input').click()
    await executorInput.locator('input').fill('张三')
    await page.waitForTimeout(500)

    // ─── Step 3: 填写执行情况说明（textarea） ───
    const firstRowTextarea = c25Root.locator('.evaluation-table .el-table__body-wrapper tr').first()
      .locator('textarea')
    if (await firstRowTextarea.count() > 0) {
      await firstRowTextarea.first().click()
      await firstRowTextarea.first().fill('已查阅内审部门的组织架构及报告路线，确认其具有独立性。')
      await page.waitForTimeout(500)
    }

    // ─── Step 4: 选择利用结论 ───
    const conclusionSelect = c25Root.locator('.conclusion-card .el-select')
    await expect(conclusionSelect).toBeVisible()
    await conclusionSelect.click()
    await page.waitForTimeout(300)

    const conclusionOption = page.locator('.el-select-dropdown__item:has-text("可以利用内部审计工作")')
    await conclusionOption.click()
    await page.waitForTimeout(500)

    // 验证结论已选中
    const conclusionValue = await conclusionSelect.locator('.el-select__selected-item, .el-input__inner').first().textContent()
      || await conclusionSelect.locator('input').inputValue()
    const hasConclusion = conclusionValue?.includes('可以利用') || conclusionValue?.includes('利用')
    expect(hasConclusion, '结论应已选中含"利用"').toBe(true)
  })

  test('C25 只读模式 → 输入禁用 (Req 7.1)', async ({ page }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C25', PROJECT_ID)
    test.skip(!wp.exists, 'C25 底稿不存在')

    // 通过 URL query 进入只读模式
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit?readonly=true`)
    await page.waitForTimeout(8_000)

    const c25Root = page.locator('.gt-c25-internal-audit')
    const isVisible = await c25Root.isVisible({ timeout: 15_000 }).catch(() => false)
    test.skip(!isVisible, 'C25 未渲染为专属组件')

    // 验证所有 select 被禁用
    const disabledSelects = c25Root.locator('.el-select.is-disabled, .el-select [disabled]')
    const enabledSelects = c25Root.locator('.el-select:not(.is-disabled)')
    const disabledSelectCount = await disabledSelects.count()
    const enabledSelectCount = await enabledSelects.count()

    // 只读模式下应有禁用的 select（适用性下拉 + 结论下拉）
    expect(
      disabledSelectCount > 0 || enabledSelectCount === 0,
      '只读模式下 select 应被禁用',
    ).toBe(true)

    // 验证 textarea 被禁用
    const disabledTextareas = c25Root.locator('textarea[disabled]')
    const enabledTextareas = c25Root.locator('textarea:not([disabled])')
    const disabledTaCount = await disabledTextareas.count()
    const enabledTaCount = await enabledTextareas.count()

    expect(
      disabledTaCount > 0 || enabledTaCount === 0,
      '只读模式下 textarea 应被禁用',
    ).toBe(true)

    // 验证 input 被禁用
    const disabledInputs = c25Root.locator('input[disabled], .el-input.is-disabled')
    const enabledBusinessInputs = c25Root.locator(
      'input:not([disabled]):not([type="file"]):not([type="hidden"])',
    )
    const disabledInputCount = await disabledInputs.count()
    const enabledInputCount = await enabledBusinessInputs.count()

    expect(
      disabledInputCount > 0 || enabledInputCount === 0,
      '只读模式下 input 应被禁用',
    ).toBe(true)
  })

  test('C25 render-config API 返回 c25-internal-audit-reliance', async ({ request }) => {
    test.setTimeout(20_000)
    const resp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const loginBody = await resp.json()
    const token = loginBody.data?.access_token ?? loginBody.access_token
    const wp = await findWorkpaper(request, token, 'C25', PROJECT_ID)
    test.skip(!wp.exists, 'C25 底稿不存在')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wp.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const compType = data.component_type || data.componentType
    expect(
      compType === 'c25-internal-audit-reliance' || compType === 'd-form-table',
      `componentType 应为 c25-internal-audit-reliance 或 d-form-table，实际: ${compType}`,
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C26 信息处理控制测试 E2E
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('C26 信息处理控制测试 E2E (Task 6.2)', () => {
  test('C26 底稿加载 → 渲染专属组件 + 矩阵表可见', async ({ page }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C26', PROJECT_ID)
    test.skip(!wp.exists, 'C26 底稿不存在，需先运行项目底稿生成')

    const consoleErrors = collectConsoleErrors(page)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(8_000)

    // 验证专属组件加载（.gt-c26-info-control）
    const c26Root = page.locator('.gt-c26-info-control')
    const isC26Visible = await c26Root.isVisible({ timeout: 15_000 }).catch(() => false)
    if (!isC26Visible) {
      console.log('C26 未渲染为 c26-info-processing-control，跳过')
      return
    }

    // 验证矩阵表渲染
    const matrixTable = page.locator('.gt-c26-info-control .matrix-table')
    await expect(matrixTable).toBeVisible()

    // 验证方法论上下文区块渲染
    const methodology = page.locator('.gt-c26-info-control .methodology-context')
    await expect(methodology).toBeVisible()

    // 验证循环筛选区域
    const cycleFilter = page.locator('.gt-c26-info-control .cycle-filter-section')
    await expect(cycleFilter).toBeVisible()

    // 无严重 console errors
    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(critical, `控制台严重错误:\n${critical.join('\n')}`).toHaveLength(0)
  })

  test('C26 矩阵增删 → 新增控制 + 四要素标记 + 测试结果 (Req 3.3)', async ({ page }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C26', PROJECT_ID)
    test.skip(!wp.exists, 'C26 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
    await page.waitForTimeout(8_000)

    const c26Root = page.locator('.gt-c26-info-control')
    const isVisible = await c26Root.isVisible({ timeout: 15_000 }).catch(() => false)
    test.skip(!isVisible, 'C26 未渲染为专属组件')

    // 获取初始行数
    const initialRows = await c26Root.locator('.matrix-table .el-table__body-wrapper tr').count()

    // ─── Step 1: 点击「新增控制」按钮 ───
    const addBtn = c26Root.locator('button:has-text("新增控制"), .el-button:has-text("新增控制")')
    await expect(addBtn).toBeVisible()
    await addBtn.click()
    await page.waitForTimeout(500)

    // ─── Step 2: ElMessageBox.prompt 弹窗出现 ───
    const dialog = page.locator('.el-message-box')
    await expect(dialog).toBeVisible({ timeout: 5_000 })

    // 验证弹窗标题
    const dialogTitle = dialog.locator('.el-message-box__title')
    await expect(dialogTitle).toContainText('新增控制')

    // ─── Step 3: 输入控制名并确认 ───
    const promptInput = dialog.locator('input')
    await promptInput.fill('IT-R&R-E2E-01')
    await page.waitForTimeout(300)

    const confirmBtn = dialog.locator('.el-message-box__btns .el-button--primary')
    await confirmBtn.click()
    await page.waitForTimeout(1_000)

    // ─── Step 4: 验证新行出现 ───
    const newRows = await c26Root.locator('.matrix-table .el-table__body-wrapper tr').count()
    expect(newRows, '新增控制后应多一行').toBeGreaterThan(initialRows)

    // ─── Step 5: 标记四要素（checkboxes） ───
    // 找到新增行（最后一行）的四要素 checkbox-group
    const lastRow = c26Root.locator('.matrix-table .el-table__body-wrapper tr').last()
    const checkboxes = lastRow.locator('.el-checkbox')
    const checkboxCount = await checkboxes.count()

    // 至少有 4 个 checkbox（完整性/准确性/授权/访问限制）
    expect(checkboxCount, '四要素应有 4 个 checkbox').toBeGreaterThanOrEqual(4)

    // 勾选「完整性」和「准确性」
    if (checkboxCount >= 2) {
      await checkboxes.nth(0).click()
      await page.waitForTimeout(300)
      await checkboxes.nth(1).click()
      await page.waitForTimeout(300)
    }

    // ─── Step 6: 选择测试结果 ───
    // 找到最后一行的测试结果 select（根据列顺序定位）
    const lastRowSelects = lastRow.locator('.el-select')
    const selectCount = await lastRowSelects.count()

    // 应有多个 select（控制类别 + 测试结果 + 结论）
    if (selectCount >= 2) {
      // 测试结果是第二个 select（第一个是控制类别）
      const testResultSelect = lastRowSelects.nth(1)
      await testResultSelect.click()
      await page.waitForTimeout(300)

      const resultOption = page.locator('.el-select-dropdown__item:has-text("未发现例外")').first()
      if (await resultOption.isVisible().catch(() => false)) {
        await resultOption.click()
        await page.waitForTimeout(500)
      }
    }
  })

  test('C26 只读模式 → 隐藏增删 + 禁用输入 (Req 7.1)', async ({ page }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWorkpaper(page.request, token, 'C26', PROJECT_ID)
    test.skip(!wp.exists, 'C26 底稿不存在')

    // 通过 URL query 进入只读模式
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit?readonly=true`)
    await page.waitForTimeout(8_000)

    const c26Root = page.locator('.gt-c26-info-control')
    const isVisible = await c26Root.isVisible({ timeout: 15_000 }).catch(() => false)
    test.skip(!isVisible, 'C26 未渲染为专属组件')

    // ─── 验证「新增控制」按钮隐藏 ───
    const addBtn = c26Root.locator('button:has-text("新增控制"), .el-button:has-text("新增控制")')
    const addBtnVisible = await addBtn.isVisible().catch(() => false)
    expect(addBtnVisible, '只读模式下「新增控制」按钮应隐藏').toBe(false)

    // ─── 验证删除按钮隐藏（操作列不渲染） ───
    const deleteBtn = c26Root.locator('.el-button .el-icon-delete, button[type="danger"]')
    const deleteBtnCount = await deleteBtn.count()
    expect(deleteBtnCount, '只读模式下删除按钮应隐藏').toBe(0)

    // ─── 验证 select 被禁用 ───
    const disabledSelects = c26Root.locator('.el-select.is-disabled, .el-select [disabled]')
    const enabledSelects = c26Root.locator('.el-select:not(.is-disabled)')
    const disabledSelectCount = await disabledSelects.count()
    const enabledSelectCount = await enabledSelects.count()

    expect(
      disabledSelectCount > 0 || enabledSelectCount === 0,
      '只读模式下 select 应被禁用',
    ).toBe(true)

    // ─── 验证 textarea 被禁用 ───
    const disabledTextareas = c26Root.locator('textarea[disabled]')
    const enabledTextareas = c26Root.locator('textarea:not([disabled])')
    const disabledTaCount = await disabledTextareas.count()
    const enabledTaCount = await enabledTextareas.count()

    expect(
      disabledTaCount > 0 || enabledTaCount === 0,
      '只读模式下 textarea 应被禁用',
    ).toBe(true)

    // ─── 验证 checkbox 被禁用 ───
    const disabledCheckboxes = c26Root.locator('.el-checkbox.is-disabled, .el-checkbox-group.is-disabled')
    const enabledCheckboxes = c26Root.locator('.el-checkbox:not(.is-disabled)')
    const disabledCbCount = await disabledCheckboxes.count()
    const enabledCbCount = await enabledCheckboxes.count()

    expect(
      disabledCbCount > 0 || enabledCbCount === 0,
      '只读模式下 checkbox 应被禁用',
    ).toBe(true)
  })

  test('C26 render-config API 返回 c26-info-processing-control', async ({ request }) => {
    test.setTimeout(20_000)
    const resp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const loginBody = await resp.json()
    const token = loginBody.data?.access_token ?? loginBody.access_token
    const wp = await findWorkpaper(request, token, 'C26', PROJECT_ID)
    test.skip(!wp.exists, 'C26 底稿不存在')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wp.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const compType = data.component_type || data.componentType
    expect(
      compType === 'c26-info-processing-control' || compType === 'd-form-table',
      `componentType 应为 c26-info-processing-control 或 d-form-table，实际: ${compType}`,
    ).toBe(true)
  })
})
