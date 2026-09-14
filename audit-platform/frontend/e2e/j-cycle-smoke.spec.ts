/**
 * J 循环冒烟测试 — meta-wave-6 集成闸门
 *
 * 验证 J1/J2/J3 三个底稿核心面板可正确渲染：
 * 1. J3: BS定价面板 (Black-Scholes 参数可见)
 * 2. J2: 精算假设面板 (折现率/薪酬增长率输入可见)
 * 3. J1: 月度分析12列 (12个月份列头可见)
 *
 * Task: M.6.2 Playwright 冒烟
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

test.describe('J 循环冒烟测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('J3 股份支付 — BS定价面板渲染 (Black-Scholes 参数可见)', async ({ page }) => {
    // 导航到 J3 底稿
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J3-2`)
    await page.waitForTimeout(3000)

    // 验证 BS 定价相关参数输入可见
    const content = await page.textContent('body')
    const hasBlackScholesContent =
      content?.includes('Black-Scholes') ||
      content?.includes('无风险利率') ||
      content?.includes('波动率') ||
      content?.includes('行权价') ||
      content?.includes('标的价格') ||
      content?.includes('期权定价') ||
      content?.includes('BS模型')

    // 页面至少包含底稿容器
    const container = page.locator(
      '.workpaper-container, [data-testid="workpaper-content"], .j3-share-based-payment'
    )
    await expect(container.first()).toBeVisible({ timeout: 15000 })

    expect(hasBlackScholesContent).toBe(true)
  })

  test('J2 设定受益计划 — 精算假设面板渲染 (折现率/薪酬增长率输入可见)', async ({ page }) => {
    // 导航到 J2 底稿精算假设 sheet
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J2-3`)
    await page.waitForTimeout(3000)

    // 验证精算假设相关参数可见
    const content = await page.textContent('body')
    const hasActuarialContent =
      content?.includes('折现率') ||
      content?.includes('薪酬增长率') ||
      content?.includes('精算假设') ||
      content?.includes('设定受益') ||
      content?.includes('DBO') ||
      content?.includes('养老金')

    // 页面至少包含底稿容器
    const container = page.locator(
      '.workpaper-container, [data-testid="workpaper-content"], .j2-defined-benefit-plan'
    )
    await expect(container.first()).toBeVisible({ timeout: 15000 })

    expect(hasActuarialContent).toBe(true)
  })

  test('J1 应付职工薪酬 — 月度分析12列渲染 (12个月份列头可见)', async ({ page }) => {
    // 导航到 J1 月度分析 sheet
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/J1-5`)
    await page.waitForTimeout(3000)

    // 验证12个月份列头可见
    const content = await page.textContent('body')
    const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
    const visibleMonths = months.filter((m) => content?.includes(m))

    // 页面至少包含底稿容器
    const container = page.locator(
      '.workpaper-container, [data-testid="workpaper-content"], .j1-employee-compensation'
    )
    await expect(container.first()).toBeVisible({ timeout: 15000 })

    // 至少应有 12 个月份列头（月度分析表）
    expect(visibleMonths.length).toBe(12)
  })
})
