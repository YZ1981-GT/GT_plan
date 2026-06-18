/**
 * A21-lite E2E — E20: A21-1 勾选持久化
 *
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID_FIX_A=<A类项目ID>
 *   npx playwright test e2e/a21-lite.spec.ts
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

test.describe('A21-lite E2E', () => {
  test.skip(!RUN_FULL_E2E || !TEST_PROJECT_ID, '【待环境】需 RUN_FULL_E2E=1 + FIX-A 项目')

  test('E20 — A21-1 勾选 1 项 → 刷新不丢', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page)
    const wp = await findWpByCode(request, token, 'A21-1')
    test.skip(!wp, '项目内无 A21-1 底稿')

    await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wp!.id}/edit`)
    await page.waitForSelector('.gt-review-checklist', { timeout: 25_000 })

    const firstYes = page.locator('.gt-review-checklist .el-radio-button', { hasText: '是' }).first()
    await firstYes.click()

    await page.waitForTimeout(2500)

    await page.reload()
    await page.waitForSelector('.gt-review-checklist', { timeout: 25_000 })

    const checked = page.locator('.gt-review-checklist .el-radio-button.is-active', { hasText: '是' }).first()
    await expect(checked).toBeVisible({ timeout: 8_000 })
  })
})
