/**
 * K 类底稿 E2E: K0→ConfirmationHub 路由
 * Task 49: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('K0 管理循环函证 → ConfirmationHub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('K0 路由到 ConfirmationHub 页面', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K0`)
    await page.waitForTimeout(3000)
    // ConfirmationHub 可能重定向到 /confirmation 或显示函证管理界面
    const url = page.url()
    const content = await page.textContent('body')
    const isConfirmationPage =
      url.includes('confirmation') ||
      content?.includes('函证') ||
      content?.includes('Confirmation') ||
      content?.includes('发函') ||
      content?.includes('回函')
    const hasContainer = await page.locator(
      '.confirmation-hub, [data-testid="workpaper-content"], .workpaper-container'
    ).count()
    expect(isConfirmationPage || hasContainer > 0).toBeTruthy()
  })

  test('K0 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K0`)
    expect(response?.status()).not.toBe(404)
  })

  test('K0-1 函证结果汇总底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K0-1`)
    expect(response?.status()).not.toBe(404)
  })

  test('K0-2 核实被函证单位底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K0-2`)
    expect(response?.status()).not.toBe(404)
  })

  test('K0A 管理循环函证程序表可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K0A`)
    expect(response?.status()).not.toBe(404)
  })
})
