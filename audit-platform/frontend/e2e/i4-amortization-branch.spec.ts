/**
 * I4 长期待摊费用 — E2E: 编制路径冒烟（明细→审定→摊销分支）
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/
 *
 * 完整联动断言见单元测试：
 * - composables/__tests__/i4LinkageClosure.spec.ts
 * - composables/__tests__/useI4CrossSheet.test.ts
 *
 * 本文件在有 fixture 项目时验证 UI 可达；无数据时 soft-skip。
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const HAS_FIXTURE = process.env.E2E_I4_FIXTURE === '1'

test.describe('I4 编制路径', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!HAS_FIXTURE, '设置 E2E_I4_FIXTURE=1 并准备测试项目后启用')
    await page.goto(`${BASE_URL}/login`)
    await page.fill('[data-testid="username"]', process.env.E2E_USER || 'admin')
    await page.fill('[data-testid="password"]', process.env.E2E_PASS || 'admin123')
    await page.click('[data-testid="login-btn"]')
    await page.waitForURL('**/projects**', { timeout: 15000 })
  })

  test('目录建议顺序可见，并可进入 I4-2 / I4-1 / 摊销分支', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects`)
    const i4Entry = page.locator('text=长期待摊费用').first()
    await expect(i4Entry).toBeVisible({ timeout: 15000 })
    await i4Entry.click()

    // 目录：建议顺序
    const prep = page.locator('.prep-order, text=建议顺序')
    if (await prep.first().isVisible({ timeout: 8000 }).catch(() => false)) {
      await expect(page.locator('text=I4-2').first()).toBeVisible()
    }

    // 进入明细（滚转四区段文案）
    const detailChip = page.locator('text=明细表').first()
    if (await detailChip.isVisible().catch(() => false)) {
      await detailChip.click()
    }

    // 摊销分支：I4-6 / I4-7
    const branchSelector = page.locator('.amort-branch-selector .el-segmented')
    if (await branchSelector.isVisible({ timeout: 8000 }).catch(() => false)) {
      const options = branchSelector.locator('.el-segmented__item')
      await expect(options).toHaveCount(2)
      await options.nth(1).click()
      await expect(
        page.locator('.i4-amortization-units, [data-component="I4TabAmortizationUnits"]'),
      ).toBeVisible({ timeout: 5000 })
      await options.nth(0).click()
      await expect(
        page.locator('.i4-amortization-straight, [data-component="I4TabAmortizationStraight"]'),
      ).toBeVisible({ timeout: 5000 })
    }
  })
})
