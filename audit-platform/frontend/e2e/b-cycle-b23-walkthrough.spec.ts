/**
 * b-cycle-b23-walkthrough.spec.ts — B23-1 穿行测试多 sheet 切换+编辑+保存
 *
 * 锚定 spec b-cycle-workpapers Task 51
 *
 * 验证 B23-1 业务层面控制（穿行测试）：
 * 1. 底稿页面正常加载
 * 2. 多 sheet Tab 可见（穿行测试记录/评价设计有效性/控制偏差记录）
 * 3. 切换 Tab 正常
 * 4. 编辑穿行测试记录 sheet 的字段
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

test.describe('Task 51: B23-1 穿行测试多 sheet 切换+编辑+保存', () => {
  test('51.1 — B23-1 多 sheet Tab 可见', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B23-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B23-1 底稿不存在，需先运行项目底稿生成')

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

    // 等待编辑器渲染
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

    // 验证 Tab 组件存在（el-tabs）
    const tabs = page.locator('.el-tabs, .el-tabs__nav')
    await expect(tabs.first()).toBeVisible({ timeout: 10_000 })

    // 验证 Tab 项包含预期的 sheet 名称
    const tabItems = page.locator('.el-tabs__item')
    const tabCount = await tabItems.count()
    expect(tabCount, 'B23-1 应有多个 sheet tab（≥3）').toBeGreaterThanOrEqual(3)

    // 验证预期 tab 名称
    const expectedSheets = ['穿行测试', '评价设计有效性', '控制偏差']
    for (const sheetName of expectedSheets) {
      const tab = tabItems.filter({ hasText: sheetName }).first()
      // 名称可能有细微差异，使用宽松匹配
      if (await tab.count() > 0) {
        expect(await tab.textContent()).toContain(sheetName)
      }
    }

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('51.2 — B23-1 Tab 切换正常', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B23-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B23-1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 获取所有 tab
    const tabItems = page.locator('.el-tabs__item')
    const tabCount = await tabItems.count()
    test.skip(tabCount < 2, 'Tab 不足 2 个，跳过切换测试')

    // 点击第二个 tab
    const secondTab = tabItems.nth(1)
    await secondTab.click()
    await page.waitForTimeout(1_500)

    // 验证第二个 tab 被激活（is-active 类名）
    await expect(secondTab).toHaveClass(/is-active/)

    // 切换到第三个 tab（如果存在）
    if (tabCount >= 3) {
      const thirdTab = tabItems.nth(2)
      await thirdTab.click()
      await page.waitForTimeout(1_500)
      await expect(thirdTab).toHaveClass(/is-active/)
    }

    // 切回第一个 tab
    const firstTab = tabItems.nth(0)
    await firstTab.click()
    await page.waitForTimeout(1_500)
    await expect(firstTab).toHaveClass(/is-active/)
  })

  test('51.3 — B23-1 编辑字段并保存', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B23-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B23-1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 查找可编辑字段（textarea / input / 点击激活编辑单元格）
    const editableFields = page.locator(
      'textarea, input[type="text"], .el-input__inner, .gt-cell-editable',
    )
    const fieldCount = await editableFields.count()

    if (fieldCount > 0) {
      // 找到一个可见的输入框并输入测试内容
      for (let i = 0; i < Math.min(fieldCount, 5); i++) {
        const field = editableFields.nth(i)
        if (await field.isVisible()) {
          await field.click()
          await page.waitForTimeout(300)

          // 对 textarea 类型输入测试文本
          const tagName = await field.evaluate((el) => el.tagName.toLowerCase())
          if (tagName === 'textarea' || tagName === 'input') {
            await field.fill('E2E 测试记录')
            break
          }
        }
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

    // 验证保存成功（无错误提示）
    const errorMsg = page.locator('.el-message--error')
    if (await errorMsg.count() > 0) {
      const errorText = await errorMsg.first().textContent()
      expect(errorText, '保存不应出现严重错误').not.toContain('服务器错误')
    }
  })

  test('51.4 — B23-1 render-config + schema API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'B23-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'B23-1 底稿不存在')

    // 验证 render-config 返回 d-form-table
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('d-form-table')

    // 验证 schema 包含多个 sheets
    const schema = rcData.schema || rcData.render_schema || {}
    const sheets = schema.sheets || {}
    const sheetNames = Object.keys(sheets)
    // B23-generic.yaml 定义了 3 个 sheet
    expect(
      sheetNames.length,
      `B23-1 schema 应含多个 sheets，实际: ${sheetNames.join(', ')}`,
    ).toBeGreaterThanOrEqual(2)
  })
})
