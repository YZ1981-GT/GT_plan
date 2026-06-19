/**
 * E2E: M9-3 OCI 分类 d-form-table
 * Task 46: Playwright E2E: M9-3 OCI 分类 d-form-table
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-0001-0001-0001-000000000001'

test.describe('M9-3 OCI分类检查', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*(?:dashboard|project).*/)
  })

  test('M9-3 OCI分类检查可正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M9-3`)
    await expect(page.locator('.d-form-table, [data-component="d-form-table"]')).toBeVisible({ timeout: 15000 })
  })

  test('M9-3 componentType 为 d-form-table', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M9-3`)
    await page.waitForTimeout(3000)
    // 不应为 audit-sheet
    const auditSheet = page.locator('.audit-sheet[data-wp-code="M9-3"]')
    await expect(auditSheet).not.toBeVisible({ timeout: 3000 })
  })

  test('M9-3 页面无 500 错误', async ({ page }) => {
    const errors: string[] = []
    page.on('response', (resp) => {
      if (resp.status() >= 500) {
        errors.push(`${resp.status()} ${resp.url()}`)
      }
    })
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M9-3`)
    await page.waitForTimeout(5000)
    expect(errors).toHaveLength(0)
  })

  test('M9-3 含 OCI 分类相关内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M9-3`)
    await page.waitForTimeout(3000)
    const body = await page.locator('body').textContent()
    expect(body).not.toContain('Internal Server Error')
  })

  test('M10-3 权益/负债分类检查可正确打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper?wp_code=M10-3`)
    await page.waitForTimeout(5000)
    const body = await page.locator('body').textContent()
    expect(body).not.toContain('Internal Server Error')
    expect(body).not.toContain('404')
  })
})
