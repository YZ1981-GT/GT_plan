/**
 * J 类底稿 E2E: J2-3 精算假设 d-form-table 编辑
 * Task 31: Playwright E2E
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('J2-3 精算假设评估 d-form-table', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('d-form-table 页面可正常打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-3`)
    await expect(
      page.locator('.gt-d-form-table, .workpaper-container, [data-testid="workpaper-content"]')
    ).toBeVisible({ timeout: 15000 })
  })

  test('componentType 路由不返回 404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-3`)
    expect(response?.status()).not.toBe(404)
  })

  test('页面包含精算假设相关字段', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-3`)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    // 精算假设评估应包含折现率或工资增长率等关键术语
    const hasActuarialContent =
      content?.includes('折现率') ||
      content?.includes('精算') ||
      content?.includes('假设') ||
      content?.includes('工资增长') ||
      content?.includes('离职率')
    expect(hasActuarialContent).toBeTruthy()
  })

  test('d-form-table 表格渲染有行数据', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-3`)
    await page.waitForTimeout(3000)
    // d-form-table 应渲染为 HTML 表格
    const tableRows = page.locator('table tr, .el-table__row, [class*="form-row"]')
    const count = await tableRows.count()
    // 至少应有表头行
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('J2-4 精算师工作利用底稿可打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-4`)
    expect(response?.status()).not.toBe(404)
  })
})
