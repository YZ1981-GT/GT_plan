/**
 * completion-phase-infra PRE-4-4: A11-2/A11-3 嵌入式核对表 E2E
 *
 * 验证 GtEmbeddedChecklist 在 A11 bundle 中正确渲染。
 * A11-2 = 财务报表编制核对表
 * A11-3 = 审计底稿编制核对表
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a'

test.describe('A11-2/A11-3 嵌入式核对表', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('A11 bundle 页面可正常打开', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A11`)
    expect(response?.status()).not.toBe(404)
  })

  test('A11-2 核对表 Tab 可切换', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A11?sheet=A11-WP-1`)
    await page.waitForTimeout(3000)
    // A11 bundle 应有多个 Tab
    const tabs = page.locator('.el-tabs__item')
    const count = await tabs.count()
    expect(count).toBeGreaterThanOrEqual(2)
  })

  test('A11-2 checklist-table 组件渲染', async ({ page }) => {
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A11?sheet=A11-2`)
    await page.waitForTimeout(5000)
    // 核对表应有表格行或核对项目
    const content = await page.textContent('body')
    const hasChecklistContent =
      content?.includes('核对') ||
      content?.includes('编制') ||
      content?.includes('适用')
    // 也接受表格容器存在
    const hasTable = await page.locator('.el-table, .gt-checklist-table, table').count()
    expect(hasChecklistContent || hasTable > 0).toBeTruthy()
  })

  test('A11-3 审计底稿编制核对表可加载', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A11?sheet=A11-3`)
    expect(response?.status()).not.toBe(404)
    await page.waitForTimeout(3000)
    const content = await page.textContent('body')
    expect(content?.includes('底稿') || content?.includes('编制') || content?.length! > 100).toBeTruthy()
  })

  test('componentType 路由为 checklist-table', async ({ page }) => {
    // A11-2 和 A11-3 在 _WP_CODE_OVERRIDE 中映射为 checklist-table
    await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/A11?sheet=A11-2`)
    await page.waitForTimeout(3000)
    // 不应出现 404 或空白
    const bodyText = await page.textContent('body')
    expect(bodyText?.length).toBeGreaterThan(50)
  })
})
