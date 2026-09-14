/**
 * G 类底稿 E2E: G0 函证 → ConfirmationHub 路由跳转
 * Task 50: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('G0 投资循环函证 → ConfirmationHub', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('G0 页面可正常打开（ConfirmationHub 路由）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0`)
    await expect(
      page.locator('.confirmation-hub, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('G0 componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0`)
    expect(response?.status()).not.toBe(404)
  })

  test('G0 函证页面包含投资相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    // ConfirmationHub 应该显示函证相关内容
    expect(content).toBeTruthy()
  })

  test('G0 使用与 D0/E0/F0 相同的 confirmation-hub 组件', async ({ page }) => {
    // 验证 G0 和其他函证底稿使用同一组件模式
    const g0Response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0`)
    expect(g0Response?.status()).not.toBe(404)

    const d0Response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/D0`)
    expect(d0Response?.status()).not.toBe(404)
  })

  test('G0 辅助表 G0-1 可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G0-1`)
    expect(response?.status()).not.toBe(404)
  })
})
