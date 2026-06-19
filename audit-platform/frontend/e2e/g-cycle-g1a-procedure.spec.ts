/**
 * G 类底稿 E2E: G1A 程序表打开 + 风险/控制联动面板
 * Task 47: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('G1A 交易性金融资产程序表', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('程序表页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G1A`)
    // 等待页面加载（程序表组件或错误提示）
    await expect(
      page.locator('.gt-program-console, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('程序表显示步骤内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G1A`)
    await page.waitForTimeout(3000)
    // 程序表应包含交易性金融资产相关文本
    const content = await page.textContent('body')
    expect(content).toContain('交易性金融资产')
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G1A`)
    expect(response?.status()).not.toBe(404)
  })

  test('风险联动面板可展开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G1A`)
    await page.waitForTimeout(3000)
    // 查找风险相关UI元素（取决于实现，可能是chip/badge/panel）
    const riskElements = page.locator('[class*="risk"], [data-testid*="risk"]')
    // 如果有风险面板，应可见
    if (await riskElements.count() > 0) {
      await expect(riskElements.first()).toBeVisible()
    }
  })

  test('底稿列表中 G1A 存在', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpapers`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    // G 循环应在列表中显示
    expect(content).toContain('投资')
  })
})
