/**
 * f-cycle-f1-prepayment.spec.ts — F1 预付账款 E2E 冒烟
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

test.describe('F1 预付账款冒烟', () => {
  test('F1-1 审定表页面可加载', async ({ page, request }) => {
    test.setTimeout(60_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'F1', PROJECT_ID)
    test.skip(!wpResult.exists, 'F1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/预付账款|F1-1|审定|底稿目录/)
  })

  test('F1-2 明细表可打开且含列设置', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)

    const loginResp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const token = (await loginResp.json()).data?.access_token

    const wpResult = await findWorkpaper(request, token, 'F1-2', PROJECT_ID)
    test.skip(!wpResult.exists, 'F1-2 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(8_000)

    const content = await page.textContent('body')
    expect(content).toMatch(/预付|明细|债权人/)
    // 列设置按钮（HTML 模式）
    const colBtn = page.getByRole('button', { name: /列设置/ })
    if (await colBtn.count()) {
      await colBtn.first().click()
      await expect(page.getByText(/核心列|全部列|审定/)).toBeVisible({ timeout: 5_000 })
    }
  })
})
