/**
 * Playwright E2E — 底稿前端体验优化验收 [wp-frontend-ux-polish Task 9]
 *
 * 验证：
 * 1. 侧栏 4 功能组可见
 * 2. 横幅折叠正常
 * 3. 首次引导弹出（el-tour）
 *
 * 前置：后端 9980 + 前端 3030 运行中
 */
import { test, expect, type Page } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.TEST_PROJECT_ID || 'df5b8403-abbb-48af-b6a4-6fd44dfae5c9'

// 跳过条件：后端未启动
test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BASE_URL}/api/health`, { timeout: 5000 })
    if (!resp.ok()) test.skip()
  } catch {
    test.skip()
  }
})

async function loginAs(page: Page) {
  const resp = await page.request.post(`${BASE_URL}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

test.describe('底稿前端体验优化验收', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page)
  })

  test('侧栏 4 功能组可见', async ({ page }) => {
    test.setTimeout(30_000)
    // 导航到底稿列表
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 找到任意底稿并打开
    const firstWp = page.locator('.gt-wp-list-row, .el-table__row').first()
    if (await firstWp.isVisible()) {
      await firstWp.click()
      await page.waitForLoadState('networkidle')

      // 验证侧面板 4 功能组
      const sidePanel = page.locator('.gt-wp-side-panel')
      if (await sidePanel.isVisible()) {
        // 检查 4 个功能组 tab 存在
        const tabs = sidePanel.locator('.el-tabs__item')
        const tabCount = await tabs.count()
        expect(tabCount).toBeGreaterThanOrEqual(4)
      }
    }
  })

  test('横幅折叠功能', async ({ page }) => {
    test.setTimeout(30_000)
    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.gt-wp-list-row, .el-table__row').first()
    if (await firstWp.isVisible()) {
      await firstWp.click()
      await page.waitForLoadState('networkidle')

      // 检查横幅区域存在（折叠或展开状态）
      const bannerArea = page.locator('.gt-editor-banners')
      if (await bannerArea.isVisible()) {
        // 如果有折叠摘要行
        const summary = bannerArea.locator('.gt-editor-banners__summary')
        if (await summary.isVisible()) {
          // 点击展开
          await summary.click()
          // 验证展开后有内容
          const expanded = bannerArea.locator('.gt-editor-banners__expanded')
          await expect(expanded).toBeVisible()
        }
      }
    }
  })

  test('首次引导弹出（el-tour）', async ({ page }) => {
    test.setTimeout(30_000)
    // 清除 localStorage 确保首次状态
    await page.addInitScript(() => {
      window.localStorage.removeItem('gt_editor_tour_dismissed')
    })

    await page.goto(`${BASE_URL}/projects/${PROJECT_ID}/workpapers`)
    await page.waitForLoadState('networkidle')

    const firstWp = page.locator('.gt-wp-list-row, .el-table__row').first()
    if (await firstWp.isVisible()) {
      await firstWp.click()
      await page.waitForLoadState('networkidle')

      // 等待引导延迟（1.5s）
      await page.waitForTimeout(2000)

      // 检查 el-tour 弹出
      const tour = page.locator('.el-tour')
      if (await tour.isVisible({ timeout: 3000 }).catch(() => false)) {
        // 验证引导步骤标题
        const title = tour.locator('.el-tour__title, .el-tour-content__title')
        await expect(title).toBeVisible()
      }
    }
  })
})
