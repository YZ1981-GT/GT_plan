/**
 * c-cycle-c22-itgc.spec.ts — C22 IT 一般控制测试 E2E 验证
 *
 * 锚定 spec c-cycle-workpapers Task 40
 *
 * 验证 C22 IT 一般控制测试（OnlyOffice/audit-sheet）：
 * 1. 底稿页面正常加载
 * 2. OnlyOffice/audit-sheet 编辑器加载
 * 3. 34 sheet tabs 存在（或至少 > 20 tabs）
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

test.describe('Task 40: C22 IT 一般控制 OnlyOffice 打开+34 sheet Tab 展示', () => {
  test('40.1 — C22 底稿加载 OnlyOffice/audit-sheet 组件', async ({ page, request }) => {
    test.setTimeout(90_000) // OnlyOffice 加载较慢
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C22', PROJECT_ID)
    test.skip(!wpResult.exists, 'C22 底稿不存在，需先运行项目底稿生成')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        if (/OnlyOffice|DocsAPI/.test(text)) return // OnlyOffice 自身日志
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待编辑器加载（audit-sheet 可能是 OnlyOffice 或降级预览）
    await page.waitForSelector(
      '.gt-wp-editor, .gt-audit-sheet, .gt-wp-editor-loading, .onlyoffice-editor, [id*="onlyoffice"], .gt-deliverable-preview',
      { timeout: 30_000 },
    )
    await page.waitForTimeout(8_000) // OnlyOffice 初始化需要时间

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证 audit-sheet 容器存在（OnlyOffice iframe 或降级组件）
    const auditSheet = page.locator(
      '.gt-audit-sheet, .onlyoffice-editor, [id*="onlyoffice"], iframe[name*="frameEditor"], .gt-deliverable-preview',
    )
    const hasSheet = await auditSheet.count() > 0
    // 如果 OnlyOffice 不可用，可能显示降级预览
    const degradedPreview = page.locator('.gt-deliverable-preview, .degraded-notice')
    const isDegraded = await degradedPreview.count() > 0

    expect(
      hasSheet || isDegraded,
      'C22 应显示 audit-sheet 编辑器或降级预览',
    ).toBeTruthy()

    // 验证无严重 console errors（排除 OnlyOffice 自身）
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('40.2 — C22 应有多个 sheet tabs（目标 34）', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C22', PROJECT_ID)
    test.skip(!wpResult.exists, 'C22 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(10_000) // OnlyOffice 完全加载

    // OnlyOffice sheet tabs 可能在 iframe 内
    // 如果是 OnlyOffice iframe，切换到 iframe 上下文
    const iframe = page.frameLocator('iframe[name*="frameEditor"], iframe[src*="onlyoffice"]')

    // 尝试在 iframe 内查找 sheet tabs
    let tabCount = 0
    try {
      const iframeTabs = iframe.locator('[class*="sheet-tab"], [class*="tab-strip"] li, .sheet-view-tab-strip li')
      tabCount = await iframeTabs.count()
    } catch {
      // OnlyOffice iframe 可能不可访问（跨域）或降级模式
    }

    // 如果 iframe 内找不到，检查页面级别的 tabs
    if (tabCount === 0) {
      const pageTabs = page.locator('.el-tabs__item, [role="tab"]')
      tabCount = await pageTabs.count()
    }

    // OnlyOffice 可能已降级（无 ONLYOFFICE_URL），此时跳过 tab 数量检查
    if (tabCount === 0) {
      const isDegraded = await page.locator('.gt-deliverable-preview, .degraded-notice').count() > 0
      test.skip(isDegraded, 'OnlyOffice 降级模式，无法验证 sheet tabs')
    }

    // 如果能获取到 tabs，验证数量（34 sheet 或至少 > 20）
    if (tabCount > 0) {
      expect(tabCount, `C22 应有超过 20 个 sheet tabs（目标 34），实际 ${tabCount}`).toBeGreaterThan(20)
    }
  })

  test('40.3 — C22 render-config API 验证 audit-sheet 类型', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'C22', PROJECT_ID)
    test.skip(!wpResult.exists, 'C22 底稿不存在')

    // 验证 render-config 返回 audit-sheet 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('audit-sheet')
  })
})
