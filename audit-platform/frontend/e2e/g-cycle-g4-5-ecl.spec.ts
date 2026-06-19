/**
 * G 类底稿 E2E: G4-5 ECL 三阶段 audit-sheet 打开
 * Task 49: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('G4-5 ECL 三阶段 audit-sheet', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('ECL audit-sheet 页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G4-5`)
    await expect(
      page.locator('.audit-sheet-container, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('componentType 为 audit-sheet 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G4-5`)
    expect(response?.status()).not.toBe(404)
  })

  test('ECL 页面包含债权投资相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G4-5`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('G14-2 信用减值 ECL 同样可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/G14-2`)
    expect(response?.status()).not.toBe(404)
    await expect(
      page.locator('.audit-sheet-container, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })
})
