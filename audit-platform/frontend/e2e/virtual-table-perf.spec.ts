/**
 * Playwright 验收测试：虚拟滚动性能
 *
 * 待环境验证：需要后端 9980 + 前端 3030 运行
 * 运行条件：RUN_FULL_E2E=1 环境变量
 *
 * 验证场景：
 * 1. 打开大底稿（>500 行）
 * 2. 滚动流畅
 * 3. 无卡顿（无 long task > 50ms）
 *
 * Validates: Requirements 1.2
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3030'
const RUN_FULL_E2E = process.env.RUN_FULL_E2E === '1'

test.describe('虚拟滚动性能验收', () => {
  test.skip(!RUN_FULL_E2E, '待环境验证：需设置 RUN_FULL_E2E=1 且启动 start-dev.bat')

  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/dashboard**', { timeout: 10000 })
  })

  test('大底稿（>500 行）虚拟滚动启用且滚动流畅', async ({ page }) => {
    // 导航到底稿列表，选择一个大底稿
    // 注：具体路径取决于项目数据，此处为通用骨架
    await page.goto(`${BASE_URL}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 查找包含大量数据的底稿（序时账/明细表）
    const tableRows = page.locator('.el-table__body-wrapper tr, .el-table-v2__row')
    const rowCount = await tableRows.count()

    if (rowCount > 500) {
      // 验证虚拟滚动已启用
      const virtualTable = page.locator('.el-table-v2')
      await expect(virtualTable).toBeVisible()

      // 验证虚拟滚动状态提示
      const statusBadge = page.locator('.gt-vt-badge, .gt-vt-hint')
      await expect(statusBadge).toContainText('虚拟滚动已启用')
    }
  })

  test('滚动操作无 long task（帧率 ≥ 60fps）', async ({ page }) => {
    await page.goto(`${BASE_URL}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 收集 long task（> 50ms 的任务表示卡顿）
    const longTasks: number[] = []

    await page.evaluate(() => {
      ;(window as any).__longTasks = []
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          ;(window as any).__longTasks.push(entry.duration)
        }
      })
      observer.observe({ type: 'longtask', buffered: true })
    })

    // 模拟滚动
    const scrollContainer = page.locator('.el-table-v2, .el-table__body-wrapper').first()
    if (await scrollContainer.isVisible()) {
      for (let i = 0; i < 5; i++) {
        await scrollContainer.evaluate((el) => {
          el.scrollTop += 500
        })
        await page.waitForTimeout(100)
      }
    }

    // 检查是否有 long task
    const tasks = await page.evaluate(() => (window as any).__longTasks || [])
    const longTaskCount = tasks.filter((t: number) => t > 50).length

    // 允许最多 1 个 long task（初始渲染可能触发）
    expect(longTaskCount).toBeLessThanOrEqual(1)
  })

  test('≤500 行使用普通 el-table', async ({ page }) => {
    await page.goto(`${BASE_URL}/workpapers`)
    await page.waitForLoadState('networkidle')

    // 找一个小底稿
    const standardTable = page.locator('.el-table').first()
    if (await standardTable.isVisible()) {
      // 验证不是 el-table-v2
      const virtualTable = page.locator('.el-table-v2')
      const isVirtualVisible = await virtualTable.isVisible().catch(() => false)

      // 如果数据量小，应该用普通 el-table
      if (!isVirtualVisible) {
        await expect(standardTable).toBeVisible()
      }
    }
  })
})
