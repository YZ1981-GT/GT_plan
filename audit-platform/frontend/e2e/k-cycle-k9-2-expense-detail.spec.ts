/**
 * K 类底稿 E2E: K9-2 管理费用明细 audit-sheet 打开
 * Task 48: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('K9-2 管理费用明细 audit-sheet', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('K9-2 管理费用明细页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K9-2`)
    await expect(
      page.locator(
        '.onlyoffice-editor, .univer-container, .workpaper-container, [data-testid="workpaper-content"]'
      )
    ).toBeVisible({ timeout: 15000 })
  })

  test('K9-2 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K9-2`)
    expect(response?.status()).not.toBe(404)
  })

  test('K9-2 页面包含费用明细相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K9-2`)
    await page.waitForTimeout(5000)
    const content = await page.textContent('body')
    const hasExpenseContent =
      content?.includes('管理费用') ||
      content?.includes('费用明细') ||
      content?.includes('发生额') ||
      content?.includes('工资') ||
      content?.includes('折旧')
    const hasEditor = await page.locator(
      '.onlyoffice-editor, .univer-container, [class*="spreadsheet"]'
    ).count()
    expect(hasExpenseContent || hasEditor > 0).toBeTruthy()
  })

  test('K8-2 销售费用明细底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-2`)
    expect(response?.status()).not.toBe(404)
  })

  test('K9-1 管理费用审定表底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K9-1`)
    expect(response?.status()).not.toBe(404)
  })
})
