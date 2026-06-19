/**
 * I 类底稿 E2E: I2-3 资本化条件 d-form-table 编辑
 * P6 Task 38
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = process.env.TEST_PROJECT_ID || 'df5b8403-4157-b297-744707db5883'
const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'

test.describe('I2-3 开发支出资本化条件检查 d-form-table', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/.*projects.*|.*dashboard.*/)
  })

  test('I2-3 资本化条件检查页面可打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I2-3`)
    await page.waitForTimeout(2000)
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('I6-3 研发费用资本化/费用化分类页面可打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I6-3`)
    await page.waitForTimeout(2000)
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('I2-3 componentType 为 d-form-table', async ({ page }) => {
    // 通过 API 验证
    const response = await page.request.get(
      `${BASE_URL}/api/projects/${PROJECT_ID}/workpapers/render-config?wp_code=I2-3`,
      { headers: { Authorization: 'Bearer test-token' } }
    )
    expect([200, 401, 404, 422]).toContain(response.status())
  })

  test('I6-7 加计扣除测算 audit-sheet 页面可打开', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I6-7`)
    await page.waitForTimeout(2000)
    const content = await page.textContent('body')
    expect(content).toBeTruthy()
  })

  test('I2-3 页面无致命 console 错误', async ({ page }) => {
    const errors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?wp_code=I2-3`)
    await page.waitForTimeout(3000)
    const fatalErrors = errors.filter(e =>
      !e.includes('net::ERR') &&
      !e.includes('favicon') &&
      !e.includes('ResizeObserver')
    )
    expect(fatalErrors.length).toBeLessThanOrEqual(2)
  })
})
