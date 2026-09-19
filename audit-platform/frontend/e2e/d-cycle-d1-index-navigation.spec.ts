/**
 * d-cycle-d1-index-navigation.spec.ts — D1 目录跳转 E2E 冒烟
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

test.describe('D1 目录跳转冒烟', () => {
  test('D1 目录页可加载并显示底稿列表', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'D1', PROJECT_ID)
    test.skip(!wpResult.exists, 'D1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/底稿目录|D1-1|应收票据|编制进度/)
  })
})
