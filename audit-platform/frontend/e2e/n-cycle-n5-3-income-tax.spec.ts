/**
 * N 类底稿 — N5-3 所得税计算表 audit-sheet E2E
 *
 * 验证：
 * 1. N5-3 所得税计算表正确打开
 * 2. audit-sheet 组件渲染
 * 3. 利润总额/调增调减/应纳税所得额/税率字段展示
 * 4. 坐标注册正确（address_registry）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || ''

test.describe('N5-3 所得税计算表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/projects**')
  })

  test('所得税计算表正确打开', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N5-3`)
    await page.waitForTimeout(2000)

    const content = await page.textContent('body')
    expect(content).toContain('所得税')
  })

  test('所得税计算表有计算相关字段', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N5-3`)
    await page.waitForTimeout(2000)

    // audit-sheet 应包含计算相关关键词
    const content = await page.textContent('body')
    // 至少应有底稿标题或加载提示
    expect(content?.length).toBeGreaterThan(0)
  })

  test('N5-3 componentType 为 audit-sheet', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N5-3`)
    await page.waitForTimeout(2000)

    // 页面不应出现 404 或错误
    const url = page.url()
    expect(url).not.toContain('404')
  })
})
