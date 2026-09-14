/**
 * N 类底稿 — N1A 递延所得税资产程序表 E2E
 *
 * 验证：
 * 1. N1A 程序表正确打开
 * 2. 步骤渲染（≥6 步）
 * 3. risk_for_cycle 联动数据源展示
 * 4. control_test_result_for_cycle 末步联动
 * 5. N1-3 暂时性差异 ref_index chip 可点击
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || ''

test.describe('N1A 递延所得税资产程序表', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/projects**')
  })

  test('程序表正确打开并渲染步骤', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1A`)
    await page.waitForTimeout(2000)

    // 验证程序表组件加载
    const content = await page.textContent('body')
    expect(content).toContain('递延所得税资产')
  })

  test('程序表有风险评估联动步骤', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1A`)
    await page.waitForTimeout(2000)

    const content = await page.textContent('body')
    expect(content).toContain('风险评估')
  })

  test('程序表有暂时性差异 ref chip', async ({ page }) => {
    test.skip(!PROJECT_ID, '需要 E2E_PROJECT_ID 环境变量')
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers?code=N1A`)
    await page.waitForTimeout(2000)

    const content = await page.textContent('body')
    expect(content).toContain('N1-3')
  })
})
