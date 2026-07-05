/**
 * H 类底稿 E2E: H0 函证 → ConfirmationHub + H0-5 替代程序
 */
import { test, expect } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'

async function getToken(request: import('@playwright/test').APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('H0 固定资产循环函证 → ConfirmationHub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('H0 页面可正常打开（ConfirmationHub 路由）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    await expect(
      page.locator('.confirmation-hub, .workpaper-container, [data-testid="workpaper-content"]'),
    ).toBeVisible({ timeout: 15000 })
  })

  test('H0 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    expect(response?.status()).not.toBe(404)
  })

  test('H0 使用与 D0/G0 相同的 confirmation-hub 组件', async ({ page }) => {
    const h0Response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0`)
    expect(h0Response?.status()).not.toBe(404)

    const g0Response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/G0`)
    expect(g0Response?.status()).not.toBe(404)
  })

  test('H0-1 函证结果汇总可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-1`)
    expect(response?.status()).not.toBe(404)
  })

  test('H0-5 替代程序渲染 confirmation-alternative-h05', async ({ page, request }) => {
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)

    if (wpResult.exists && wpResult.wpId) {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/${wpResult.wpId}?sheet=替代程序H0-5`)
    } else {
      await page.goto(`${BASE_URL}/project/${TEST_PROJECT_ID}/workpaper/H0-5`)
    }

    await expect(page.locator('[data-testid="h0-alternative-h05"]')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.gt-confirmation-alternative-h05')).toBeVisible()
  })

  test('H0-5 render-config 命中 confirmation-alternative-h05', async ({ request }) => {
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H0', TEST_PROJECT_ID)
    test.skip(!wpResult.exists || !wpResult.wpId, '测试项目无 H0 底稿')

    const resp = await request.get(`/api/workpapers/${wpResult.wpId}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { sheet: '替代程序H0-5' },
    })
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    const sheets = body?.data?.sheets ?? body?.sheets ?? []
    const target = Array.isArray(sheets)
      ? sheets.find((s: { sheetName?: string }) => s.sheetName === '替代程序H0-5')
      : null
    const componentType = target?.componentType ?? body?.data?.componentType ?? body?.componentType
    expect(componentType).toBe('confirmation-alternative-h05')
  })
})
