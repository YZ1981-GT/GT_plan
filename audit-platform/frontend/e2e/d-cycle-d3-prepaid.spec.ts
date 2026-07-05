/**
 * d-cycle-d3-prepaid.spec.ts — D3 预收账款 E2E 冒烟
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

test.describe('D3 预收账款冒烟', () => {
  test('D3 目录/审定表页面可加载', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'D3', PROJECT_ID)
    test.skip(!wpResult.exists, 'D3 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/预收账款|D3-1|底稿目录|审定/)
  })
})
