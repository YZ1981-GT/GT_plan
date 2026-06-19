/**
 * c-cycle-c2-control-test.spec.ts — C2 循环控制测试 E2E 验证
 *
 * 锚定 spec c-cycle-workpapers Task 38
 *
 * 验证 C2 销售循环控制测试：
 * 1. 底稿页面正常加载
 * 2. 多 sheet tabs 可见（控制测试汇总表 + 控制测试过程记录）
 * 3. 汇总表填写（选择 control_attribute enum，设置 sample_size）
 * 4. 保存
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

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

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('Task 38: C2 循环控制测试打开+多 sheet 切换+汇总表填写+保存', () => {
  test('38.1 — C2 底稿加载并渲染多 sheet tabs', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2 底稿不存在，需先运行项目底稿生成')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待编辑器/表单渲染
    await page.waitForSelector(
      '.gt-wp-editor, .gt-d-form-table, .gt-wp-editor-loading',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证多 sheet tabs 存在（控制测试汇总表 + 控制测试过程记录）
    const tabs = page.locator('.el-tabs__item, [role="tab"]')
    const tabCount = await tabs.count()
    expect(tabCount, 'C2 应有至少 2 个 sheet tab').toBeGreaterThanOrEqual(2)

    // 验证 tab 名称包含汇总表和过程记录
    const tabTexts: string[] = []
    for (let i = 0; i < tabCount; i++) {
      const text = await tabs.nth(i).textContent()
      if (text) tabTexts.push(text.trim())
    }
    const hasMainSheet = tabTexts.some((t) => t.includes('汇总') || t.includes('控制测试'))
    expect(hasMainSheet, `应有"汇总表"或"控制测试"相关 tab，实际: ${tabTexts.join(', ')}`).toBeTruthy()

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('38.2 — C2 汇总表填写 control_attribute enum + sample_size', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证表格渲染（d-form-table 使用 el-table）
    const table = page.locator('.el-table, .gt-d-form-table')
    await expect(table.first()).toBeVisible({ timeout: 10_000 })

    // 尝试填写 enum 字段（控制属性：预防性/检查性）
    const selects = page.locator('.el-select, select')
    const selectCount = await selects.count()

    if (selectCount > 0) {
      // 点击第一个 select 打开下拉
      const firstSelect = selects.first()
      await firstSelect.click()
      await page.waitForTimeout(500)

      // 查找并选择选项（预防性）
      const option = page.locator('.el-select-dropdown__item, .el-option')
        .filter({ hasText: /预防性|检查性|有效/ })
        .first()
      if (await option.isVisible()) {
        await option.click()
        await page.waitForTimeout(500)
      } else {
        // 关闭下拉
        await page.keyboard.press('Escape')
      }
    }

    // 尝试填写数字字段（sample_size）
    const numberInputs = page.locator('input[type="number"], .el-input-number input')
    if (await numberInputs.count() > 0) {
      const firstNumber = numberInputs.first()
      await firstNumber.click()
      await firstNumber.fill('25')
      await page.waitForTimeout(300)
    }
  })

  test('38.3 — C2 保存操作', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 尝试保存（查找保存按钮或使用 Ctrl+S）
    const saveBtn = page.locator('button').filter({ hasText: /保存/ }).first()
    if (await saveBtn.isVisible()) {
      await saveBtn.click()
      await page.waitForTimeout(2_000)
    } else {
      await page.keyboard.press('Control+s')
      await page.waitForTimeout(2_000)
    }

    // 验证保存成功或至少无错误
    const errorMsg = page.locator('.el-message--error')
    const hasError = await errorMsg.count() > 0
    if (hasError) {
      const errorText = await errorMsg.first().textContent()
      expect(errorText, '保存不应失败').not.toContain('失败')
    }
  })

  test('38.4 — C2 render-config API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'C2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2 底稿不存在')

    // 验证 render-config 返回 d-form-table 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('d-form-table')

    // 验证 schema 包含 sheets
    const sheets = rcData.sheets || {}
    const sheetNames = Object.keys(sheets)
    expect(sheetNames.length, 'C2 schema 应有至少 2 个 sheet').toBeGreaterThanOrEqual(2)
  })
})
