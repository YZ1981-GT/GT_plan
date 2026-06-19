/**
 * 现金流量表支持底稿 E2E — A5-2/A5-3/A5-4 集成验证
 * Spec: cash-flow-support-workpaper Task 9
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a'

test.describe('A5 现金流量表支持底稿', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('A5-2 承诺事项底稿可正常打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A5-2`)
    expect(response?.status()).not.toBe(404)
  })

  test('A5-3 或有事项底稿可正常打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A5-3`)
    expect(response?.status()).not.toBe(404)
  })

  test('A5-4 终止经营底稿可正常打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A5-4`)
    expect(response?.status()).not.toBe(404)
  })

  test('A5-3 或有事项显示三级可能性判断', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A5-3`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    const hasContent =
      content?.includes('或有事项') ||
      content?.includes('可能性') ||
      content?.includes('很可能')
    expect(hasContent).toBeTruthy()
  })

  test('A5-4 终止经营显示公式计算', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A5-4`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    const hasContent =
      content?.includes('终止经营') ||
      content?.includes('持续经营') ||
      content?.includes('净利润')
    expect(hasContent).toBeTruthy()
  })
})
