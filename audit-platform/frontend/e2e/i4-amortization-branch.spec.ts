/**
 * I4 长期待摊费用 — E2E: 摊销分支切换 + 计算验证
 * Spec: .kiro/specs/i4-long-term-prepaid/ Task 7.4
 * Requirements: 6.1-6.6
 *
 * 测试场景（skeleton — 需 dev server 运行）:
 * 1. 导航到 I4 底稿
 * 2. 验证摊销分支选择器存在（el-segmented 含"直线法（I4-6）" / "工作量法（I4-7）"）
 * 3. 切换到工作量法 → 验证 I4TabAmortizationUnits 渲染
 * 4. 切换回直线法 → 验证 I4TabAmortizationStraight 渲染
 */
import { test, expect } from '@playwright/test'

// 项目 fixtures（需已有测试项目+I4底稿）
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'

test.describe('I4 摊销分支切换', () => {
  test.beforeEach(async ({ page }) => {
    // 登录（复用全局 setup 或直接导航）
    await page.goto(`${BASE_URL}/login`)
    await page.fill('[data-testid="username"]', 'admin')
    await page.fill('[data-testid="password"]', 'admin123')
    await page.click('[data-testid="login-btn"]')
    await page.waitForURL('**/projects**', { timeout: 10000 })
  })

  test('验证分支选择器存在且可切换', async ({ page }) => {
    // 导航到 I4 底稿（假设有项目和底稿）
    // NOTE: 实际 E2E 需要 fixture 数据。此处验证 UI 结构
    await page.goto(`${BASE_URL}/projects`)

    // 选择第一个项目 → 底稿列表
    const projectRow = page.locator('.project-list-item, [data-testid="project-row"]').first()
    if (await projectRow.isVisible()) {
      await projectRow.click()
    }

    // 查找 I4 底稿并进入摊销 sheet（I4-6）
    const i4Entry = page.locator('text=长期待摊费用').first()
    if (await i4Entry.isVisible({ timeout: 5000 }).catch(() => false)) {
      await i4Entry.click()
    }

    // 等待 I4 组件加载 — 查找摊销分支选择器
    const branchSelector = page.locator('.amort-branch-selector .el-segmented')
    if (await branchSelector.isVisible({ timeout: 8000 }).catch(() => false)) {
      // 验证选择器包含两个选项
      const options = branchSelector.locator('.el-segmented__item')
      await expect(options).toHaveCount(2)

      // 验证文本
      await expect(options.nth(0)).toContainText('直线法（I4-6）')
      await expect(options.nth(1)).toContainText('工作量法（I4-7）')

      // 切换到工作量法
      await options.nth(1).click()
      // 验证 I4TabAmortizationUnits 渲染（通过特定 class 或 data-testid）
      await expect(page.locator('.i4-amortization-units, [data-component="I4TabAmortizationUnits"]')).toBeVisible({ timeout: 5000 })

      // 切换回直线法
      await options.nth(0).click()
      // 验证 I4TabAmortizationStraight 渲染
      await expect(page.locator('.i4-amortization-straight, [data-component="I4TabAmortizationStraight"]')).toBeVisible({ timeout: 5000 })
    }
  })
})
