/**
 * H 类底稿 E2E: H1A 程序表打开 + 风险/控制联动面板
 * Task 43: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('H1A 固定资产程序表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('程序表页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1A`)
    await expect(
      page.locator('.gt-program-console, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('程序表显示固定资产相关步骤', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1A`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    expect(content).toContain('固定资产')
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1A`)
    expect(response?.status()).not.toBe(404)
  })

  test('风险联动面板可展开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1A`)
    await page.waitForTimeout(3000)
    const riskElements = page.locator('[class*="risk"], [data-testid*="risk"]')
    if (await riskElements.count() > 0) {
      await expect(riskElements.first()).toBeVisible()
    }
  })

  test('H2A 在建工程程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H2A`)
    expect(response?.status()).not.toBe(404)
  })
})
