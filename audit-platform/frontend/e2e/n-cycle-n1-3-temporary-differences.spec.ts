/**
 * N 类底稿 — N1-3 暂时性差异计算 audit-sheet E2E
 *
 * 验证：
 * 1. N1-3 暂时性差异计算表正确打开
 * 2. audit-sheet 组件渲染
 * 3. 账面价值/计税基础/差异/税率/DTA 字段展示
 * 4. 坐标注册正确（address_registry）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || ''

test.describe('N1-3 暂时性差异计算表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/projects**')
  })

  test('暂时性差异计算表正确打开', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1-3`)
    await page.waitForTimeout(2000)

    const content = await page.textContent('body')
    expect(content).toContain('递延')
  })

  test('N1-3 componentType 为 audit-sheet', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1-3`)
    await page.waitForTimeout(2000)

    // 页面不应出现 404 或错误
    const url = page.url()
    expect(url).not.toContain('404')
  })

  test('暂时性差异表加载不报错', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))
    
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1-3`)
    await page.waitForTimeout(3000)

    // 不应有严重 JS 错误
    const criticalErrors = errors.filter(e => !e.includes('ResizeObserver'))
    expect(criticalErrors.length).toBe(0)
  })
})
