/**
 * Playwright E2E — A18-1 向监管部门报送审计小结
 *
 * Spec: .kiro/specs/a18-1-regulatory-submission/
 * Task: 5.2
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const SHOULD_RUN = process.env.RUN_A181_E2E === '1'

test.describe('A18-1 向监管部门报送审计小结', () => {
  test.skip(!SHOULD_RUN, '跳过 E2E（需设置 RUN_A181_E2E=1）')

  test('加载 → 验证前缀 → 填写 → 保存 → 刷新验证', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // Navigate to A18-1
    await page.getByText('A18-1').first().click()
    await page.waitForTimeout(1000)

    // Verify structured view
    const content = page.locator('.gt-a181__content')
    await expect(content).toBeVisible({ timeout: 10000 })

    // Verify prefix "致：" is present
    await expect(page.locator('.gt-a181__prefix')).toContainText('致：')

    // Fill bureau
    const bureauInput = page.locator('.gt-a181__recipient input').first()
    await bureauInput.fill('深圳市')

    // Fill contact
    await page.locator('.gt-a181__body-fields input').first().fill('张合伙人')

    // Wait for save
    await page.waitForTimeout(3000)
    await expect(page.locator('.gt-a181__save-status')).toContainText('已保存')

    // Reload and verify
    await page.reload()
    await page.waitForLoadState('networkidle')
    await page.getByText('A18-1').first().click()
    await page.waitForTimeout(1000)

    await expect(page.locator('.gt-a181__recipient input').first()).toHaveValue('深圳市')
  })
})
