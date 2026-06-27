/**
 * Playwright E2E — A17-6 总结会会议纪要
 *
 * Spec: .kiro/specs/a17-6-closing-meeting/
 * Task: 5.2
 *
 * 前置: RUN_A176_E2E=1 + 后端 9980 + 前端 3030 运行中
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const SHOULD_RUN = process.env.RUN_A176_E2E === '1'

test.describe('A17-6 总结会会议纪要', () => {
  test.skip(!SHOULD_RUN, '跳过 E2E（需设置 RUN_A176_E2E=1）')

  test.beforeEach(async ({ page }) => {
    // Navigate to A17 bundle which contains A17-6 tab
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')
  })

  test('加载 A17-6 → 验证元信息自动填充 → 填写 → 保存 → 刷新验证', async ({ page }) => {
    // 1. Navigate to A17-6 (inside A17 bundle as a tab)
    // Look for A17 in workpaper list
    await page.getByText('A17').first().click()
    await page.waitForTimeout(1000)

    // Find A17-6 tab
    const a176Tab = page.getByRole('tab', { name: /A17-6|总结会/ })
    if (await a176Tab.isVisible()) {
      await a176Tab.click()
      await page.waitForTimeout(500)
    }

    // 2. Verify structured view renders
    const content = page.locator('.gt-a176__content')
    await expect(content).toBeVisible({ timeout: 10000 })

    // 3. Verify meta info card renders
    const metaItems = page.locator('.gt-a176__meta-item')
    await expect(metaItems).toHaveCount(6)

    // 4. Verify index_no is A17-6 and disabled
    const indexInput = metaItems.nth(5).locator('input')
    await expect(indexInput).toHaveValue('A17-6')
    await expect(indexInput).toBeDisabled()

    // 5. Fill in meeting minutes
    const minutesTextarea = page.locator('.gt-a176__field').nth(2).locator('textarea')
    await minutesTextarea.fill('本次总结会讨论了本年度审计工作的主要发现和结论')

    // 6. Fill conclusion
    const conclusionTextarea = page.locator('.gt-a176__field').nth(3).locator('textarea')
    await conclusionTextarea.fill('同意出具标准无保留意见')

    // 7. Wait for debounce save (2s + buffer)
    await page.waitForTimeout(3000)

    // 8. Verify save status shows "已保存"
    const saveStatus = page.locator('.gt-a176__save-status')
    await expect(saveStatus).toContainText('已保存')

    // 9. Reload page
    await page.reload()
    await page.waitForLoadState('networkidle')

    // Re-navigate to A17-6 tab
    await page.getByText('A17').first().click()
    await page.waitForTimeout(1000)
    const a176TabReload = page.getByRole('tab', { name: /A17-6|总结会/ })
    if (await a176TabReload.isVisible()) {
      await a176TabReload.click()
      await page.waitForTimeout(1000)
    }

    // 10. Verify data persisted
    const minutesAfterReload = page.locator('.gt-a176__field').nth(2).locator('textarea')
    await expect(minutesAfterReload).toHaveValue('本次总结会讨论了本年度审计工作的主要发现和结论')

    const conclusionAfterReload = page.locator('.gt-a176__field').nth(3).locator('textarea')
    await expect(conclusionAfterReload).toHaveValue('同意出具标准无保留意见')
  })

  test('双模式切换', async ({ page }) => {
    // Navigate to A17-6
    await page.getByText('A17').first().click()
    await page.waitForTimeout(1000)
    const a176Tab = page.getByRole('tab', { name: /A17-6|总结会/ })
    if (await a176Tab.isVisible()) {
      await a176Tab.click()
      await page.waitForTimeout(500)
    }

    // Verify structured view is default
    await expect(page.locator('.gt-a176__content')).toBeVisible()

    // Switch to online edit (if OO available)
    const onlineBtn = page.getByText('在线编辑')
    if (await onlineBtn.isVisible()) {
      await onlineBtn.click()
      await page.waitForTimeout(500)
      // Structured content should be hidden
      await expect(page.locator('.gt-a176__content')).not.toBeVisible()

      // Switch back
      await page.getByText('结构化视图').click()
      await page.waitForTimeout(500)
      await expect(page.locator('.gt-a176__content')).toBeVisible()
    }
  })
})
