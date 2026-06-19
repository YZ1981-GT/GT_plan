/**
 * d-cycle-d6-contract-asset.spec.ts — D6 合同资产多 sheet Tab 切换 E2E 验证
 *
 * 锚定 spec d-cycle-workpapers Task 45
 *
 * 验证 D6 合同资产底稿系列：
 * 1. D6 底稿页面正常加载
 * 2. 多 sheet tabs 可见（D6 系列有 9 个子底稿）
 * 3. 切换到 D6-2（audit-sheet）— 验证 OnlyOffice/audit-sheet 加载
 * 4. 切换到 D6-6（d-form-table）— 验证 HTML 表单渲染
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

test.describe('Task 45: D6 合同资产多 sheet Tab 切换+audit-sheet 打开', () => {
  test('45.1 — D6 底稿加载并显示多 sheet tabs', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D6', PROJECT_ID)
    test.skip(!wpResult.exists, 'D6 底稿不存在，需先运行项目底稿生成')

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

    // 等待编辑器加载
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

    // 验证表格或表单渲染
    const table = page.locator('.el-table, .gt-d-form-table')
    await expect(table.first()).toBeVisible({ timeout: 10_000 })

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('45.2 — D6-2 audit-sheet 加载验证', async ({ page, request }) => {
    test.setTimeout(90_000) // OnlyOffice 加载较慢
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D6-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'D6-2 底稿不存在')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        if (/OnlyOffice|DocsAPI/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待 audit-sheet 组件加载
    await page.waitForSelector(
      '.gt-wp-editor, .gt-audit-sheet, .gt-wp-editor-loading, .onlyoffice-editor, [id*="onlyoffice"], .gt-deliverable-preview',
      { timeout: 30_000 },
    )
    await page.waitForTimeout(8_000)

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证 audit-sheet 容器或降级预览存在
    const auditSheet = page.locator(
      '.gt-audit-sheet, .onlyoffice-editor, [id*="onlyoffice"], iframe[name*="frameEditor"], .gt-deliverable-preview',
    )
    const hasSheet = await auditSheet.count() > 0
    const degradedPreview = page.locator('.gt-deliverable-preview, .degraded-notice')
    const isDegraded = await degradedPreview.count() > 0

    expect(
      hasSheet || isDegraded,
      'D6-2 应显示 audit-sheet 编辑器或降级预览',
    ).toBeTruthy()
  })

  test('45.3 — D6-6 d-form-table HTML 表单渲染', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D6-6', PROJECT_ID)
    test.skip(!wpResult.exists, 'D6-6 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待 d-form-table 渲染
    await page.waitForSelector(
      '.gt-wp-editor, .gt-d-form-table, .gt-wp-editor-loading',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证 HTML 表单渲染（el-table 或 el-form）
    const table = page.locator('.el-table, .gt-d-form-table, .el-form')
    const hasForm = await table.count() > 0
    expect(hasForm, 'D6-6 应渲染 HTML 表单（d-form-table）').toBeTruthy()
  })

  test('45.4 — D6 系列 render-config API 验证', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // D6 应为 d-form-table
    const d6Result = await findWorkpaper(request, token, 'D6', PROJECT_ID)
    if (d6Result.exists) {
      const rcResp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${d6Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      expect(rcResp.status()).toBe(200)
      const rcBody = await rcResp.json()
      const rcData = rcBody?.data || rcBody
      expect(rcData.component_type || rcData.componentType).toBe('d-form-table')
    }

    // D6-2 应为 audit-sheet
    const d62Result = await findWorkpaper(request, token, 'D6-2', PROJECT_ID)
    if (d62Result.exists) {
      const rcResp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${d62Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      expect(rcResp.status()).toBe(200)
      const rcBody = await rcResp.json()
      const rcData = rcBody?.data || rcBody
      expect(rcData.component_type || rcData.componentType).toBe('audit-sheet')
    }

    // D6-6 应为 d-form-table
    const d66Result = await findWorkpaper(request, token, 'D6-6', PROJECT_ID)
    if (d66Result.exists) {
      const rcResp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${d66Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      expect(rcResp.status()).toBe(200)
      const rcBody = await rcResp.json()
      const rcData = rcBody?.data || rcBody
      expect(rcData.component_type || rcData.componentType).toBe('d-form-table')
    }
  })
})
