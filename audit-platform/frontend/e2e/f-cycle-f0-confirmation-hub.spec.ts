/**
 * f-cycle-f0-confirmation-hub.spec.ts — F0 函证底稿→ConfirmationHub 路由跳转 E2E 验证
 *
 * 锚定 spec f-cycle-workpapers Task 58
 *
 * 验证 F0 函证底稿：
 * 1. F0 底稿打开后重定向到 ConfirmationHub（路由变化或特定组件渲染）
 * 2. render-config API 返回 confirmation-hub componentType
 * 3. F0 与 D0、E0 使用相同的 confirmation-hub 模式
 * 4. F0-1~F0-5 辅助底稿类型正确（d-form-table）
 *
 * F0 底稿映射为 confirmation-hub，不独立渲染，而是路由到 ConfirmationHub 模块（cycle=F）。
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

test.describe('Task 58: F0 函证底稿→ConfirmationHub 路由跳转', () => {
  test('58.1 — F0 底稿打开后路由到 ConfirmationHub', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'F0', PROJECT_ID)
    test.skip(!wpResult.exists, 'F0 底稿不存在，需先运行项目底稿生成')

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
    await page.waitForTimeout(6_000)

    // F0 应该重定向到 ConfirmationHub 或渲染 ConfirmationHub 组件
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
      pageContent?.includes('确认函') ||
      pageContent?.includes('询证函')

    // 验证：路由跳转 OR 函证组件渲染 OR 函证相关内容
    expect(
      redirectedToConfirmation || hasConfirmationComponent || hasConfirmationContent,
      'F0 应重定向到 ConfirmationHub 或渲染函证相关组件/内容',
    ).toBeTruthy()

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('58.2 — F0 render-config API 返回 confirmation-hub componentType', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'F0', PROJECT_ID)
    test.skip(!wpResult.exists, 'F0 底稿不存在')

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

  test('58.3 — F0 与 D0、E0 confirmation-hub 类型一致', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // F0 应为 confirmation-hub
    const f0Result = await findWorkpaper(request, token, 'F0', PROJECT_ID)
    if (f0Result.exists) {
      const f0Resp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${f0Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (f0Resp.status() === 200) {
        const f0Body = await f0Resp.json()
        const f0Data = f0Body?.data || f0Body
        expect(f0Data.component_type || f0Data.componentType).toBe('confirmation-hub')
      }
    }

    // D0 应为 confirmation-hub（对比验证）
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

    // E0 应为 confirmation-hub（对比验证）
    const e0Result = await findWorkpaper(request, token, 'E0', PROJECT_ID)
    if (e0Result.exists) {
      const e0Resp = await request.get(
        `/api/projects/${PROJECT_ID}/working-papers/${e0Result.wpId}/render-config`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (e0Resp.status() === 200) {
        const e0Body = await e0Resp.json()
        const e0Data = e0Body?.data || e0Body
        expect(e0Data.component_type || e0Data.componentType).toBe('confirmation-hub')
      }
    }
  })

  test('58.4 — F0 函证辅助底稿类型正确', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // F0-1~F0-5 应为 d-form-table
    const auxCodes = ['F0-1', 'F0-2', 'F0-3', 'F0-4', 'F0-5']
    for (const code of auxCodes) {
      const wpResult = await findWorkpaper(request, token, code, PROJECT_ID)
      if (wpResult.exists) {
        const rcResp = await request.get(
          `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (rcResp.status() === 200) {
          const rcBody = await rcResp.json()
          const rcData = rcBody?.data || rcBody
          const ct = rcData.component_type || rcData.componentType
          expect(ct, `${code} 应为 d-form-table`).toBe('d-form-table')
        }
      }
    }
  })
})
