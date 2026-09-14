/**
 * d-cycle-d1-1-audit-table.spec.ts — D1-1 应收票据审定表 E2E 验证
 *
 * 锚定 D2 Task 44 模式，验证 D1-1 审定表（d1-notes-receivable / D1TabAdjudication）
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

test.describe('D1-1 审定表加载与路由', () => {
  test('D1-1 审定表加载 d1-notes-receivable 组件', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, await getToken(request), 'D1-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'D1-1 底稿不存在，需先运行项目底稿生成')

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        consoleErrors.push(text)
      }
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForSelector(
      '.gt-wp-editor, .d1-notes-receivable, .d1-tab-adjudication, .gt-wp-editor-loading',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    const adjudication = page.locator('.d1-tab-adjudication, .d1-notes-receivable')
    await expect(adjudication.first()).toBeVisible({ timeout: 10_000 })

    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('D1-1 wp_code_overrides 路由到 d1-notes-receivable', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'D1-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'D1-1 底稿不存在')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const componentType =
      rcBody?.data?.component_type ?? rcBody?.component_type ?? rcBody?.data?.componentType
    expect(componentType).toBe('d1-notes-receivable')
  })
})
