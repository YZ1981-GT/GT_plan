/**
 * H 类底稿 E2E: H9-3 租赁负债现值 audit-sheet 打开
 * Task 45: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('H9-3 租赁负债现值测算 audit-sheet', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('H9-3 audit-sheet 页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H9-3`)
    await expect(
      page.locator('.audit-sheet, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H9-3`)
    expect(response?.status()).not.toBe(404)
  })

  test('H9-4 租赁负债摊销表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H9-4`)
    expect(response?.status()).not.toBe(404)
  })

  test('H8-4 使用权资产租赁还原可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H8-4`)
    expect(response?.status()).not.toBe(404)
  })

  test('H9A 租赁负债程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H9A`)
    expect(response?.status()).not.toBe(404)
  })
})
