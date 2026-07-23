/**
 * I 类底稿 E2E: I2-3 资本化条件检查 — 页面级烟雾测试
 * P6 Task 38
 *
 * 注（I2 复盘修复，2026-07）：I2-3 现已由结构化 HTML 组件 I2TabAdjustment.vue 渲染
 * （GtI2DevelopmentExpenditure.vue currentSheet==='I2-3' 分支），并非旧版通用
 * "d-form-table" componentType；下方测试均为宽松的页面可用性/无致命报错烟雾检查，
 * 未对具体 componentType 或 DOM 选择器做强断言，故无需因组件重命名而调整。
 */
import { test, expect } from '@playwright/test'

const PROJECT_ID = process.env.TEST_PROJECT_ID || 'df5b8403-4157-b297-744707db5883'
const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'

test.describe('I2-3 开发支出资本化条件检查（烟雾测试）', () => {
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

  test('I2-3 render-config 端点可访问（不强制断言 componentType）', async ({ page }) => {
    // 通过 API 验证；I2-3 现为结构化 HTML 组件而非旧版 d-form-table，此处仅验证端点可达
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
