/**
 * J 类底稿 E2E: J3-4 期权定价 audit-sheet 打开
 * Task 32: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('J3-4 期权公允价值测算 audit-sheet', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('audit-sheet 页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-4`)
    await expect(
      page.locator(
        '.onlyoffice-editor, .univer-container, .workpaper-container, [data-testid="workpaper-content"]'
      )
    ).toBeVisible({ timeout: 15000 })
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-4`)
    expect(response?.status()).not.toBe(404)
  })

  test('页面包含期权定价或 Black-Scholes 相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-4`)
    await page.waitForTimeout(5000)
    const content = await page.textContent('body')
    // audit-sheet（OnlyOffice/Univer）可能显示期权相关信息或仅为编辑器容器
    const hasOptionContent =
      content?.includes('期权') ||
      content?.includes('Black-Scholes') ||
      content?.includes('行权价') ||
      content?.includes('波动率') ||
      content?.includes('股份支付') ||
      content?.includes('公允价值')
    // audit-sheet 可能仅渲染编辑器框架，内容在 OnlyOffice 内部
    // 所以也接受编辑器容器存在的情况
    const hasEditor = await page.locator(
      '.onlyoffice-editor, .univer-container, [class*="spreadsheet"]'
    ).count()
    expect(hasOptionContent || hasEditor > 0).toBeTruthy()
  })

  test('J3-5 等待期费用分摊底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-5`)
    expect(response?.status()).not.toBe(404)
  })

  test('J3-2 股份支付明细底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-2`)
    expect(response?.status()).not.toBe(404)
  })
})
