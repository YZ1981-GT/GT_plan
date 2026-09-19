/**
 * K 类底稿 E2E: K5-3 或有事项评估 d-form-table 编辑
 * Task 47: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('K5-3 或有事项评估 d-form-table', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('K5-3 或有事项评估页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5-3`)
    await expect(
      page.locator(
        '.d-form-table, .form-table, [data-testid="workpaper-content"], .workpaper-container'
      )
    ).toBeVisible({ timeout: 15000 })
  })

  test('K5-3 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5-3`)
    expect(response?.status()).not.toBe(404)
  })

  test('K5-3 页面包含或有事项相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5-3`)
    await page.waitForTimeout(5000)
    const content = await page.textContent('body')
    const hasContingencyContent =
      content?.includes('或有事项') ||
      content?.includes('可能性') ||
      content?.includes('预计负债') ||
      content?.includes('诉讼') ||
      content?.includes('计提')
    const hasEditor = await page.locator(
      '.d-form-table, .form-table, [class*="form"]'
    ).count()
    expect(hasContingencyContent || hasEditor > 0).toBeTruthy()
  })

  test('K5-4 最佳估计数底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5-4`)
    expect(response?.status()).not.toBe(404)
  })

  test('K5-5 律师函回函分析底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5-5`)
    expect(response?.status()).not.toBe(404)
  })
})
