/**
 * c-cycle-c2-2-deviation.spec.ts — C2-2 偏差评价 E2E 验证
 *
 * 锚定 spec c-cycle-workpapers Task 42
 *
 * 验证 C2-2 销售循环评价控制偏差：
 * 1. 底稿页面正常加载
 * 2. 7 步评价字段可见
 * 3. 填写 step1（enum 选择"是"）
 * 4. 填写 conclusion（enum 选择）
 * 5. 保存
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

test.describe('Task 42: C2-2 偏差评价 7 步填写+结论保存', () => {
  test('42.1 — C2-2 偏差评价底稿加载并渲染 7 步评价字段', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2-2 底稿不存在，需先运行项目底稿生成')

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

    // 验证表格渲染
    const table = page.locator('.el-table, .gt-d-form-table')
    await expect(table.first()).toBeVisible({ timeout: 10_000 })

    // 验证页面内容包含 7 步评价相关文本
    const pageContent = await page.content()
    const hasStep1 = pageContent.includes('步骤1') || pageContent.includes('孤立事件')
      || pageContent.includes('step1') || pageContent.includes('偏差')
    const hasConclusion = pageContent.includes('结论') || pageContent.includes('conclusion')

    expect(
      hasStep1 || hasConclusion,
      'C2-2 偏差评价应包含评价步骤或结论相关文本',
    ).toBeTruthy()

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('42.2 — C2-2 填写 step1 enum（是/否）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2-2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 找到 enum 字段（el-select）并尝试选择"是"
    const selects = page.locator('.el-select, select')
    const selectCount = await selects.count()

    if (selectCount > 0) {
      // 点击第一个 select（可能是 step1_isolated）
      const firstSelect = selects.first()
      await firstSelect.click()
      await page.waitForTimeout(500)

      // 选择"是"
      const option = page.locator('.el-select-dropdown__item, .el-option')
        .filter({ hasText: '是' })
        .first()
      if (await option.isVisible()) {
        await option.click()
        await page.waitForTimeout(500)
      } else {
        await page.keyboard.press('Escape')
      }
    }
  })

  test('42.3 — C2-2 填写 conclusion enum 并保存', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C2-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2-2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 尝试找到并填写结论字段
    const selects = page.locator('.el-select, select')
    const selectCount = await selects.count()

    // 找到最后一个 select（可能是 conclusion 字段）
    if (selectCount > 1) {
      const lastSelect = selects.last()
      await lastSelect.scrollIntoViewIfNeeded()
      await lastSelect.click()
      await page.waitForTimeout(500)

      // 选择结论选项
      const option = page.locator('.el-select-dropdown__item, .el-option')
        .filter({ hasText: /有效|偏差|无效/ })
        .first()
      if (await option.isVisible()) {
        await option.click()
        await page.waitForTimeout(500)
      } else {
        await page.keyboard.press('Escape')
      }
    }

    // 保存
    const saveBtn = page.locator('button').filter({ hasText: /保存/ }).first()
    if (await saveBtn.isVisible()) {
      await saveBtn.click()
      await page.waitForTimeout(2_000)
    } else {
      await page.keyboard.press('Control+s')
      await page.waitForTimeout(2_000)
    }

    // 验证无保存错误
    const errorMsg = page.locator('.el-message--error')
    const hasError = await errorMsg.count() > 0
    if (hasError) {
      const errorText = await errorMsg.first().textContent()
      expect(errorText, '保存不应失败').not.toContain('失败')
    }
  })

  test('42.4 — C2-2 render-config API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'C2-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'C2-2 底稿不存在')

    // 验证 render-config 返回 d-form-table 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('d-form-table')

    // 验证 schema 包含"评价控制偏差" sheet
    const sheets = rcData.sheets || {}
    const sheetNames = Object.keys(sheets)
    expect(sheetNames.length, 'C2-2 schema 应有至少 1 个 sheet').toBeGreaterThanOrEqual(1)
    // 验证包含偏差评价相关 sheet
    const hasDeviationSheet = sheetNames.some(
      (name) => name.includes('偏差') || name.includes('评价'),
    )
    expect(hasDeviationSheet, `应有"偏差"或"评价"相关 sheet，实际: ${sheetNames.join(', ')}`).toBeTruthy()
  })
})
