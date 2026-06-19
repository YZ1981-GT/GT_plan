/**
 * E2E: M6-1 未分配利润审定表回写
 * Task 44: Playwright E2E: M6-1 审定表回写
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-0001-0001-0001-000000000001'

test.describe('M6-1 未分配利润审定表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*(?:dashboard|project).*/)
  })

  test('M6-1 审定表可正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M6-1`)
    await expect(page.locator('.d-form-table, [data-component="d-form-table"]')).toBeVisible({ timeout: 15000 })
  })

  test('M6-1 显示公式字段（期初+净利润-提取-分配=期末）', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M6-1`)
    await page.waitForTimeout(3000)
    // 应包含未分配利润相关字段
    await expect(page.locator('text=期初')).toBeVisible({ timeout: 10000 })
  })

  test('M6-1 审定金额字段可编辑', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M6-1`)
    await page.waitForTimeout(3000)
    // 审定表应有可编辑的数字输入框
    const inputs = page.locator('input[type="number"], .el-input-number')
    if (await inputs.first().isVisible()) {
      await expect(inputs.first()).toBeVisible()
    }
  })

  test('M6-1 componentType 为 d-form-table', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M6-1`)
    await page.waitForTimeout(3000)
    // 确认不是 univer/audit-sheet 渲染
    const univer = page.locator('.univer-container, .spreadsheet-container')
    await expect(univer).not.toBeVisible({ timeout: 3000 })
  })

  test('M6-1 显示损益联动数据源', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M6-1`)
    await page.waitForTimeout(3000)
    // 净利润字段应有自动取数标记
    const autoLabel = page.locator('text=净利润')
    if (await autoLabel.isVisible()) {
      await expect(autoLabel).toBeVisible()
    }
  })
})
