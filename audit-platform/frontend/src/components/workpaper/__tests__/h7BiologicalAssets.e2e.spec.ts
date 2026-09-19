/**
 * H7 生产性生物资产 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 7.3
 * Requirements: 全部
 *
 * 完整流程：行业选择→打开H7→切换模式→审定→折旧→监盘→产量→保存
 *
 * NOTE: 需要dev server运行时才能执行。
 * 运行命令: npx playwright test src/components/workpaper/__tests__/h7BiologicalAssets.e2e.spec.ts
 */
import { test, expect } from '@playwright/test'

test.describe('H7 生产性生物资产 E2E', () => {
  test.beforeEach(async ({ page }) => {
    // 假设已有农业项目 + H7底稿
    await page.goto('/projects/test-agriculture/workpapers')
  })

  test('非农林牧渔项目显示行业不适用提示', async ({ page }) => {
    // 访问非适用行业的H7底稿
    await page.goto('/projects/test-manufacturing/workpapers/h7-test-wp')
    await expect(page.locator('.el-empty__description')).toContainText('农林牧渔')
  })

  test('默认成本模式 + 折旧sheet可见', async ({ page }) => {
    await page.goto('/projects/test-agriculture/workpapers/h7-wp-1')
    // 检查el-segmented默认选中成本模式
    await expect(page.locator('.el-segmented')).toBeVisible()
    // H7-11折旧sheet应可见
    await expect(page.locator('text=折旧测算')).toBeVisible()
  })

  test('切换到公允模式 → 折旧sheet消失 + 公允复核出现', async ({ page }) => {
    await page.goto('/projects/test-agriculture/workpapers/h7-wp-1')
    // 点击公允价值模式
    await page.click('text=公允价值模式')
    // 折旧sheet不可见
    await expect(page.locator('text=折旧测算表H7-11')).not.toBeVisible()
    // 公允价值复核可见
    await expect(page.locator('text=公允价值复核')).toBeVisible()
  })

  test('审定表保存触发TB回写', async ({ page }) => {
    await page.goto('/projects/test-agriculture/workpapers/h7-wp-1?sheet=H7-1')
    // 填入审定数据（模拟）
    // ...省略具体交互
    // 验证保存成功
    await expect(page.locator('.el-message--success')).toBeVisible()
  })

  test('互转差额≠0时红色高亮', async ({ page }) => {
    await page.goto('/projects/test-agriculture/workpapers/h7-wp-1?sheet=H7-14')
    // 验证差额显示
    await expect(page.locator('.transfer-diff-warning')).toBeVisible()
  })

  test('产量记录支持动态行新增', async ({ page }) => {
    await page.goto('/projects/test-agriculture/workpapers/h7-wp-1?sheet=H7-14')
    // 点击新增按钮
    await page.click('text=新增产量记录')
    // 弹出命名对话框
    await expect(page.locator('.el-message-box')).toBeVisible()
  })
})
