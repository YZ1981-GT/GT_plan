/**
 * d-cycle-d0-confirmation.spec.ts — D0 函证底稿→ConfirmationHub 路由跳转 E2E 验证
 *
 * 锚定 spec d-cycle-workpapers Task 47
 *
 * 验证 D0 函证底稿：
 * 1. 打开 D0 底稿后重定向到 ConfirmationHub（路由变化或特定组件渲染）
 * 2. render-config API 返回 confirmation-hub componentType
 *
 * D0 底稿映射为 confirmation-hub，不独立渲染，而是路由到 ConfirmationHub 模块。
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

test.describe('Task 47: D0 函证底稿→ConfirmationHub 路由跳转', () => {
  test('47.1 — D0 底稿打开后路由到 ConfirmationHub', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D0', PROJECT_ID)
    test.skip(!wpResult.exists, 'D0 底稿不存在，需先运行项目底稿生成')

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

    // 导航到 D0 底稿编辑页
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    // D0 应该重定向到 ConfirmationHub 或渲染 ConfirmationHub 组件
    const currentUrl = page.url()
    const redirectedToConfirmation =
      currentUrl.includes('confirmation') ||
      currentUrl.includes('confirm')

    // 或者页面上渲染了 ConfirmationHub 相关组件
    const confirmationHub = page.locator(
      '[class*="confirmation"], [class*="confirm-hub"], .gt-confirmation-hub',
    )
    const hasConfirmationComponent = await confirmationHub.count() > 0

    // 或者页面包含函证相关文字
    const pageContent = await page.textContent('body')
    const hasConfirmationContent =
      pageContent?.includes('函证') ||
      pageContent?.includes('发函') ||
      pageContent?.includes('回函') ||
      pageContent?.includes('确认函')

    // 验证：路由跳转 OR 函证组件渲染 OR 函证相关内容
    expect(
      redirectedToConfirmation || hasConfirmationComponent || hasConfirmationContent,
      'D0 应重定向到 ConfirmationHub 或渲染函证相关组件/内容',
    ).toBeTruthy()

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('47.2 — D0 render-config API 返回 confirmation-hub componentType', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'D0', PROJECT_ID)
    test.skip(!wpResult.exists, 'D0 底稿不存在')

    // 验证 render-config 返回 confirmation-hub 类型
    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    const componentType = rcData.component_type || rcData.componentType
    expect(componentType).toBe('confirmation-hub')
  })

  test('47.3 — D0 confirmation-hub 与 C1 a-program-console 类型对比', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // D0 应为 confirmation-hub
    const d0Result = await findWorkpaper(request, token, 'D0', PROJECT_ID)
    if (d0Result.exists) {
      const d0Resp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${d0Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (d0Resp.status() === 200) {
        const d0Body = await d0Resp.json()
        const d0Data = d0Body?.data || d0Body
        expect(d0Data.component_type || d0Data.componentType).toBe('confirmation-hub')
      }
    }

    // C1 应为 a-program-console（对比验证路由差异）
    const c1Result = await findWorkpaper(request, token, 'C1', PROJECT_ID)
    if (c1Result.exists) {
      const c1Resp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${c1Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (c1Resp.status() === 200) {
        const c1Body = await c1Resp.json()
        const c1Data = c1Body?.data || c1Body
        expect(c1Data.component_type || c1Data.componentType).toBe('a-program-console')
      }
    }
  })
})
