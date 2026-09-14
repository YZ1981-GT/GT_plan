/**
 * E2E Tests — H5 油气资产底稿 Playwright 端到端流程
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 7.3
 * Requirements: 全部
 *
 * 测试流程：
 * 1. 导航到 H5 底稿目录 → 验证 index 加载
 * 2. 切换到 H5-1 审定表 → 验证审定表双区块渲染
 * 3. 验证折耗分支选择器（H5-12）
 * 4. 验证行业守卫（非适用行业提示）
 */
import { test, expect } from '@playwright/test'

// 项目 fixture（需要已有测试项目数据）
const PROJECT_ID = process.env.E2E_PROJECT_ID || '1'
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'

test.describe('H5 油气资产底稿 — 端到端流程', () => {
  test.beforeEach(async ({ page }) => {
    // 登录（复用全局 setup 或手动登录）
    await page.goto(`${BASE_URL}/login`)
    await page.fill('[data-testid="username"]', 'admin')
    await page.fill('[data-testid="password"]', 'admin123')
    await page.click('[data-testid="login-btn"]')
    await page.waitForURL('**/projects**')
  })

  test('导航到H5底稿 → 目录Index加载', async ({ page }) => {
    // 进入项目 → 底稿列表
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 找到 H5 底稿并点击
    const h5Entry = page.locator('text=油气资产').first()
    await expect(h5Entry).toBeVisible({ timeout: 10000 })
    await h5Entry.click()

    // 验证底稿目录(H5 Index)加载
    await expect(page.locator('[data-testid="h5-tab-index"]')).toBeVisible({ timeout: 15000 })

    // 验证24行sheet列表存在
    const sheetRows = page.locator('[data-testid="h5-index-row"]')
    await expect(sheetRows.first()).toBeVisible()
  })

  test('切换到H5-1审定表 → 双区块渲染', async ({ page }) => {
    // 导航到 H5 底稿
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const h5Entry = page.locator('text=油气资产').first()
    await h5Entry.click()

    // 切换到 H5-1 审定表
    const adjTab = page.locator('text=H5-1').first()
    await expect(adjTab).toBeVisible({ timeout: 10000 })
    await adjTab.click()

    // 验证审定表加载 — 原值区块
    await expect(
      page.locator('[data-testid="h5-adjudication-cost-block"]'),
    ).toBeVisible({ timeout: 15000 })

    // 验证审定表加载 — 折耗区块
    await expect(
      page.locator('[data-testid="h5-adjudication-depletion-block"]'),
    ).toBeVisible()
  })

  test('H5-12 折耗分支选择器渲染', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const h5Entry = page.locator('text=油气资产').first()
    await h5Entry.click()

    // 切换到 H5-12
    const depletionTab = page.locator('text=H5-12').first()
    await expect(depletionTab).toBeVisible({ timeout: 10000 })
    await depletionTab.click()

    // 验证分支选择器存在
    const branchSelector = page.locator('[data-testid="depletion-branch-selector"]')
    await expect(branchSelector).toBeVisible({ timeout: 15000 })

    // 验证两个选项
    await expect(page.locator('text=不含减值')).toBeVisible()
    await expect(page.locator('text=含减值')).toBeVisible()
  })

  test('行业守卫 — 非适用行业显示提示', async ({ page }) => {
    // 此测试需要一个非oil_gas/mining行业的项目
    // 使用环境变量指定非石油项目ID
    const nonOilProjectId = process.env.E2E_NON_OIL_PROJECT_ID
    if (!nonOilProjectId) {
      test.skip()
      return
    }

    await page.goto(`${BASE_URL}/projects/${nonOilProjectId}/workpapers`)
    await page.waitForLoadState('networkidle')

    const h5Entry = page.locator('text=油气资产').first()
    if (await h5Entry.isVisible()) {
      await h5Entry.click()

      // 验证行业不适用提示
      await expect(
        page.locator('text=本底稿仅适用于石油天然气/采矿行业项目'),
      ).toBeVisible({ timeout: 10000 })
    }
  })
})
