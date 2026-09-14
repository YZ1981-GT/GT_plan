/**
 * A21 core+plus E2E — E21 签字 / E22 导出
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { resolveFixtureProjectId } from './fixtures/ensure-test-project'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = resolveFixtureProjectId('FIX-A') || _env.TEST_PROJECT_ID || ''

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

async function findWpByCode(
  request: APIRequestContext,
  token: string,
  wpCode: string,
): Promise<{ id: string } | null> {
  const resp = await request.get(`/api/projects/${TEST_PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const wp = list.find((w: any) => (w.wp_code || '').toUpperCase() === wpCode.toUpperCase())
  return wp?.id ? { id: wp.id } : null
}

test.describe('A21 core+plus E2E', () => {
  test.skip(!RUN_FULL_E2E || !TEST_PROJECT_ID, '【待环境】需 RUN_FULL_E2E=1 + FIX-A 项目')

  test('E21 — 全部勾选 + 通过 → sign status pass', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await loginAs(page)
    const wp = await findWpByCode(request, token, 'A21-1')
    test.skip(!wp, '项目内无 A21-1 底稿')

    await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wp!.id}/edit`)
    await page.waitForSelector('.gt-review-checklist', { timeout: 25_000 })

    const yesButtons = page.locator('.gt-review-checklist .check-item:not(.is-auto-na) .el-radio-button', { hasText: '是' })
    const count = await yesButtons.count()
    for (let i = 0; i < count; i++) {
      await yesButtons.nth(i).click()
    }

    await page.locator('.gt-review-checklist button', { hasText: '通过' }).click()
    await expect(page.locator('.gt-review-checklist .el-tag', { hasText: '已通过' })).toBeVisible({ timeout: 8_000 })

    const signResp = await request.get(
      `/api/projects/${TEST_PROJECT_ID}/a21/review-sign-status`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(signResp.ok()).toBeTruthy()
    const status = await signResp.json()
    const data = status?.data ?? status
    expect(data['A21-1']).toBe('pass')
  })

  test('E22 — 导出 xlsx 返回 200', async ({ request, page }) => {
    test.setTimeout(45_000)
    const token = await loginAs(page)
    const wp = await findWpByCode(request, token, 'A21-1')
    test.skip(!wp, '项目内无 A21-1 底稿')

    const resp = await request.get(
      `/api/workpapers/${wp!.id}/export-review-xlsx?project_id=${TEST_PROJECT_ID}&wp_code=A21-1`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(resp.status()).toBe(200)
    expect(resp.headers()['content-type']).toContain('spreadsheetml')
  })
})
