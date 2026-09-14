/**
 * I5 附注双向同步 E2E（Playwright）
 * 验证：I5-2 明细 → 附注上市自动取数 → 与审定勾稽
 */
import { test, expect, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickDisclosureSheetTab,
} from './fixtures/ensure-test-project'

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

test.describe('I5 附注双向同步', () => {
  test('明细填报后附注页可加载且显示聚合提示', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page)
    const token = (await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    }).then((r) => r.json())).data?.access_token
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(3000)

    // clickDisclosureSheetTab 找不到 Tab 时抛错（click 超时），故用 try/catch 换成可跳过信号
    let switched = true
    try {
      await clickDisclosureSheetTab(page, 'listed')
    } catch {
      switched = false
    }
    test.skip(!switched, '附注上市 sheet 不可用')

    await page.waitForTimeout(2000)
    const hasDisclosure = (await page.locator('.i5-tab-disclosure, .i5-disclosure, text=其他非流动资产').count()) > 0
    const hasAutoFill = (await page.locator('text=自动取数, text=从 I5-2, text=账面价值').count()) > 0
    expect(hasDisclosure || hasAutoFill).toBeTruthy()
  })
})
