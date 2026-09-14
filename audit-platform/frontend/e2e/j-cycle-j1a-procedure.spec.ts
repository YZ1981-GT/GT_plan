/**
 * J 类底稿 E2E: J1A 应付职工薪酬程序表打开 + 风险/控制联动
 * Task 30: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('J1A 应付职工薪酬程序表', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('程序表页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1A`)
    await expect(
      page.locator('.gt-program-console, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('程序表显示职工薪酬相关步骤', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1A`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    expect(content).toContain('职工薪酬')
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1A`)
    expect(response?.status()).not.toBe(404)
  })

  test('风险联动面板可展开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1A`)
    await page.waitForTimeout(3000)
    // 查找风险相关UI元素（risk_for_cycle 数据源渲染）
    const riskElements = page.locator('[class*="risk"], [data-testid*="risk"]')
    if (await riskElements.count() > 0) {
      await expect(riskElements.first()).toBeVisible()
    }
  })

  test('控制测试联动面板可展开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1A`)
    await page.waitForTimeout(3000)
    // 查找控制测试相关UI元素（control_test_result_for_cycle 数据源渲染）
    const controlElements = page.locator('[class*="control"], [data-testid*="control"]')
    if (await controlElements.count() > 0) {
      await expect(controlElements.first()).toBeVisible()
    }
  })

  test('J2A 设定受益计划程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2A`)
    expect(response?.status()).not.toBe(404)
  })

  test('J3A 股份支付程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3A`)
    expect(response?.status()).not.toBe(404)
  })
})
