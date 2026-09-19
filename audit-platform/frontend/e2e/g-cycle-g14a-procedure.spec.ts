/**
 * g-cycle-g14a-procedure.spec.ts — G14A 程序表 E2E 冒烟
 */
import { test, expect, type Page } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper, clickWorkpaperSheetTab } from './fixtures/ensure-test-project'

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

test.describe('G14A 程序表冒烟', () => {
  test('G14A 结构化程序表可加载', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'G14A', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14A 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)
    await clickWorkpaperSheetTab(page, 'G14A')

    const content = await page.textContent('body')
    expect(content).toMatch(/程序|信用减值|6702|审计/)
  })
})
