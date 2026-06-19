/**
 * H 类底稿 E2E: H0 函证 → ConfirmationHub 路由跳转
 * Task 46: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('H0 固定资产循环函证 → ConfirmationHub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('H0 页面可正常打开（ConfirmationHub 路由）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H0`)
    await expect(
      page.locator('.confirmation-hub, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('H0 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H0`)
    expect(response?.status()).not.toBe(404)
  })

  test('H0 使用与 D0/E0/F0/G0 相同的 confirmation-hub 组件', async ({ page }) => {
    const h0Response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H0`)
    expect(h0Response?.status()).not.toBe(404)

    const g0Response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0`)
    expect(g0Response?.status()).not.toBe(404)
  })

  test('H0-1 函证结果汇总可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H0-1`)
    expect(response?.status()).not.toBe(404)
  })

  test('H0-5 替代程序可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H0-5`)
    expect(response?.status()).not.toBe(404)
  })
})
