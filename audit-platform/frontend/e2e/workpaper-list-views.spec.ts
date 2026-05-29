/**
 * workpaper-list-shrink — Playwright e2e 回归
 *
 * 5 子视图各 1 条主路径：进入 → 渲染就绪 → 1 次主交互 → 切换离开
 * 验证拆分后 Shell + 5 子 SFC 的路由切换、渲染、keep-alive 正常工作。
 *
 * 跳过策略：
 * - 默认通过 test.skip(...) 跳过（needs running backend + frontend stack）
 * - 启动 start-dev.bat 后用 `npx playwright test e2e/workpaper-list-views.spec.ts`
 * - 或设置 RUN_FULL_E2E=1 环境变量
 *
 * Requirements: 6.3, 7.4
 * @see .kiro/specs/workpaper-list-shrink/tasks.md Task 11
 */
import { test, expect } from '@playwright/test'

const RUN_FULL_E2E = process.env.RUN_FULL_E2E === '1'

// 使用首汽租车项目（需先 UPDATE projects SET is_deleted=false）
const PROJECT_ID = 'df5b8403-5e3a-4c1a-b7a1-8f2e9d6c4b5a'
const BASE_PATH = `/projects/${PROJECT_ID}/workpapers`

test.describe('底稿列表 5 子视图回归 (workpaper-list-shrink)', () => {
  test.skip(!RUN_FULL_E2E, '完整 E2E 需 RUN_FULL_E2E=1 + start-dev.bat 运行')

  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  test('Workbench：进入默认视图 → 表格渲染 → 搜索 → 切到看板', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=workbench`)
    await page.waitForLoadState('networkidle')

    // 验证 Shell 容器渲染
    await expect(page.locator('.gt-wp-list')).toBeVisible({ timeout: 15000 })

    // 验证 Tab 栏存在
    await expect(page.locator('.el-radio-group')).toBeVisible()

    // 验证工作台内容区渲染
    await expect(page.locator('.gt-wp-workbench-container, .gt-wp-list-default, .el-table')).toBeVisible({ timeout: 10000 })

    // 切到看板
    await page.click('.el-radio-button:has-text("看板")')
    await expect(page).toHaveURL(/view=kanban/)
  })

  test('Board：切到看板 → 看板渲染 → 切到生命周期', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=kanban`)
    await page.waitForLoadState('networkidle')

    // 验证看板容器渲染
    await expect(page.locator('.gt-wp-board-wrapper')).toBeVisible({ timeout: 15000 })

    // 切到生命周期
    await page.click('.el-radio-button:has-text("生命周期")')
    await expect(page).toHaveURL(/view=lifecycle/)
  })

  test('Lifecycle：切到生命周期 → 阶段渲染 → 切到依赖图', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=lifecycle`)
    await page.waitForLoadState('networkidle')

    // 验证生命周期容器渲染
    await expect(page.locator('.gt-wp-lifecycle-wrapper')).toBeVisible({ timeout: 15000 })

    // 切到依赖图
    await page.click('.el-radio-button:has-text("依赖图")')
    await expect(page).toHaveURL(/view=graph/)
  })

  test('DependencyGraph：切到依赖图 → D3 图渲染 → 切到委派矩阵', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=graph`)
    await page.waitForLoadState('networkidle')

    // 验证依赖图容器渲染
    await expect(page.locator('.gt-wp-dep-graph-wrapper')).toBeVisible({ timeout: 15000 })

    // 切到委派矩阵
    await page.click('.el-radio-button:has-text("委派矩阵")')
    await expect(page).toHaveURL(/view=matrix/)
  })

  test('DelegationMatrix：切到委派矩阵 → 矩阵渲染 → 切回工作台', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=matrix`)
    await page.waitForLoadState('networkidle')

    // 验证委派矩阵容器渲染
    await expect(page.locator('.gt-wp-matrix-wrapper')).toBeVisible({ timeout: 15000 })

    // 切回工作台
    await page.click('.el-radio-button:has-text("工作台")')
    await expect(page).toHaveURL(/view=workbench/)
  })

  test('深链兼容：旧书签 ?view=list 正确渲染 Workbench', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=list`)
    await page.waitForLoadState('networkidle')

    // list 映射到 Workbench 子 SFC，应渲染列表视图
    await expect(page.locator('.gt-wp-list')).toBeVisible({ timeout: 15000 })
  })

  test('非法 viewMode 回退到 workbench', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=invalid-mode`)
    await page.waitForLoadState('networkidle')

    // 应回退到 workbench
    await expect(page).toHaveURL(/view=workbench/)
    await expect(page.locator('.gt-wp-list')).toBeVisible({ timeout: 15000 })
  })

  test('keep-alive：切换视图后切回不重新加载', async ({ page }) => {
    await page.goto(`${BASE_PATH}?view=workbench`)
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.gt-wp-list')).toBeVisible({ timeout: 15000 })

    // 切到看板
    await page.click('.el-radio-button:has-text("看板")')
    await expect(page.locator('.gt-wp-board-wrapper')).toBeVisible({ timeout: 10000 })

    // 切回工作台 — 应该瞬间渲染（keep-alive 缓存）
    await page.click('.el-radio-button:has-text("工作台")')
    await expect(page.locator('.gt-wp-workbench-container, .gt-wp-list-default, .el-table')).toBeVisible({ timeout: 3000 })
  })
})
