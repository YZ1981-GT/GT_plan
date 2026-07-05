/**
 * d-cycle-d1a-procedure.spec.ts — D1A 审计程序表 E2E 冒烟
 */
import { test, expect, type Page } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

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
}

test.describe('D1A 程序表冒烟', () => {
  test('D1A 程序表页面可加载', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'D1A', PROJECT_ID)
    test.skip(!wpResult.exists, 'D1A 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const content = await page.textContent('body')
    const hasProcedure =
      content?.includes('程序') ||
      content?.includes('D1A') ||
      content?.includes('应收票据') ||
      content?.includes('审计结论') ||
      content?.includes('进度')
    expect(hasProcedure).toBeTruthy()
  })
})
