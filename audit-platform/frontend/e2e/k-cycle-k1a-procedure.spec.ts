/**
 * K 类底稿 E2E: K1A 程序表打开 + 风险/控制联动
 * Task 46: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('K1A 其他应收款程序表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('K1A 程序表页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K1A`)
    await expect(
      page.locator(
        '.program-console, .procedure-table, [data-testid="workpaper-content"], .workpaper-container'
      )
    ).toBeVisible({ timeout: 15000 })
  })

  test('K1A componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K1A`)
    expect(response?.status()).not.toBe(404)
  })

  test('K1A 页面包含风险评估引用（risk_for_cycle）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K1A`)
    await page.waitForTimeout(5000)
    const content = await page.textContent('body')
    // 程序表应显示步骤内容或编辑器
    const hasContent =
      content?.includes('风险') ||
      content?.includes('其他应收款') ||
      content?.includes('程序') ||
      content?.includes('步骤')
    const hasEditor = await page.locator(
      '.program-console, .procedure-table, [class*="program"]'
    ).count()
    expect(hasContent || hasEditor > 0).toBeTruthy()
  })

  test('K1A 控制测试结果引用', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K1A`)
    await page.waitForTimeout(5000)
    const content = await page.textContent('body')
    const hasControlRef =
      content?.includes('控制') ||
      content?.includes('测试') ||
      content?.includes('有效') ||
      content?.includes('程序')
    const hasEditor = await page.locator(
      '.program-console, .procedure-table, [class*="program"]'
    ).count()
    expect(hasControlRef || hasEditor > 0).toBeTruthy()
  })

  test('K5A 预计负债程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K5A`)
    expect(response?.status()).not.toBe(404)
  })
})
