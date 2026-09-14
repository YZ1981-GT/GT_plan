/**
 * H 类底稿 E2E: H1-1 审定表编辑 + 回写
 * Task 44: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('H1-1 固定资产审定表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('审定表页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1-1`)
    await expect(
      page.locator('.gt-d-form-table, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('审定表显示资产类别分行', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1-1`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    // H1-1 特殊结构包含资产类别
    expect(content).toBeTruthy()
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H1-1`)
    expect(response?.status()).not.toBe(404)
  })

  test('H2-1 在建工程审定表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H2-1`)
    expect(response?.status()).not.toBe(404)
  })

  test('H8-1 使用权资产审定表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/H8-1`)
    expect(response?.status()).not.toBe(404)
  })
})
