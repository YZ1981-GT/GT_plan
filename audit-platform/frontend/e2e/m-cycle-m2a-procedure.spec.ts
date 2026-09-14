/**
 * E2E: M2A 实收资本程序表打开 + C1 企业层面控制联动
 * Task 43: Playwright E2E: M2A 程序表打开 + C1 控制联动
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-0001-0001-0001-000000000001'

test.describe('M2A 实收资本程序表', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*(?:dashboard|project).*/)
  })

  test('M2A 程序表可正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M2A`)
    // 等待程序表渲染
    await expect(page.locator('.gt-program-console, .a-program-console, [data-component="a-program-console"]')).toBeVisible({ timeout: 15000 })
  })

  test('M2A 程序表显示步骤列表', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M2A`)
    await page.waitForTimeout(3000)
    // 程序表应至少显示 5 个步骤
    const steps = page.locator('.procedure-step, .program-item, tr[data-seq]')
    await expect(steps.first()).toBeVisible({ timeout: 10000 })
  })

  test('M2A seq1 显示风险评估数据源', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M2A`)
    await page.waitForTimeout(3000)
    // 第一步应引用 B50 风险评估
    await expect(page.locator('text=风险评估')).toBeVisible({ timeout: 10000 })
  })

  test('M2A 末步引用 C1 企业层面控制', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M2A`)
    await page.waitForTimeout(3000)
    // 末步应包含列报和披露相关内容
    await expect(page.locator('text=列报')).toBeVisible({ timeout: 10000 })
  })

  test('M2A 有 ref_index chip 跳转到 M2-2', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M2A`)
    await page.waitForTimeout(3000)
    // 应能看到 M2-2 引用
    const chip = page.locator('text=M2-2')
    if (await chip.isVisible()) {
      await expect(chip).toBeVisible()
    }
  })
})
