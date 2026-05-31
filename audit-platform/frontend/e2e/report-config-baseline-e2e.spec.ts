/**
 * report-config-baseline-e2e — 报表配置主模板回填 + 主模板同步提示 端到端验证
 *
 * 覆盖需求：
 * - 1.1 项目级配置行 → 提交主模板候选 → 确认弹窗 → 提交成功提示
 * - 2.3 克隆项目 is_stale → banner 提示 → 同步主模板更新
 * - admin 候选审核 tab → 通过/驳回 → 状态变更
 *
 * ⚠️ 待环境（start-dev.bat：后端 9980 + 前端 3030）
 * 本测试文件已编写完整用例结构，但因开发环境未启动，
 * 通过 test.skip 显式标记"待环境"，不伪绿。
 *
 * 运行方式：
 *   1. 启动 start-dev.bat（后端 9980 + 前端 3030）
 *   2. 确保测试项目存在且有报表配置数据（含 standard 级主模板 + 已克隆项目）
 *   3. set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> && \
 *      npx playwright test e2e/report-config-baseline-e2e.spec.ts
 *
 * Spec: report-config-baseline Task 11
 * Requirements: 1.1, 2.3
 */
import { test, expect } from '@playwright/test'

// ─── 环境变量 ───
const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''

test.describe('报表配置主模板回填 + 同步提示 E2E（report-config-baseline）', () => {
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 待环境：需 start-dev.bat 启动后端 9980 + 前端 3030
  // 标记不伪绿——环境未就绪时整个 describe 跳过
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  test.skip(
    !RUN_FULL_E2E,
    '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 测试项目数据',
  )

  test.beforeEach(async ({ page }) => {
    // 登录 admin 账号（审核候选需 admin 权限）
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 场景 1：项目级配置行 → 点击"提交主模板候选" → 确认弹窗 → 提交成功提示
  // Validates: Requirements 1.1
  // ─────────────────────────────────────────────────────────────────────────
  test('项目配置行提交主模板候选 → 确认弹窗 → 成功提示', async ({ page }) => {
    // Step 1: 导航到项目的报表配置主模板管理页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config-baseline`)
    await expect(page.locator('.gt-rcb')).toBeVisible({ timeout: 15000 })

    // Step 2: 确认在"项目配置" tab
    const projectTab = page.locator('.el-tabs__item').filter({ hasText: '项目配置' })
    await expect(projectTab).toHaveClass(/is-active/)

    // Step 3: 等待配置表格加载完成
    const table = page.locator('.el-table')
    await expect(table).toBeVisible({ timeout: 10000 })

    // Step 4: 找到一个有公式的行，点击"提交主模板候选"按钮
    const suggestBtn = page.locator('button:has-text("提交主模板候选")').first()
    await expect(suggestBtn).toBeEnabled({ timeout: 5000 })
    await suggestBtn.click()

    // Step 5: 验证确认弹窗出现（ElMessageBox.confirm）
    const confirmDialog = page.locator('.el-message-box')
    await expect(confirmDialog).toBeVisible({ timeout: 3000 })
    await expect(confirmDialog).toContainText('提交为主模板候选')

    // Step 6: 点击"确认提交"
    const confirmBtn = confirmDialog.locator('button:has-text("确认提交")')
    await confirmBtn.click()

    // Step 7: 验证成功提示（ElMessage.success）
    const successMsg = page.locator('.el-message--success')
    await expect(successMsg).toBeVisible({ timeout: 5000 })
    await expect(successMsg).toContainText('已提交主模板候选')
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 场景 2：admin 登录 → 候选审核 tab → 通过/驳回 → 验证状态变更
  // Validates: Requirements 1.1 (admin 审核流程)
  // ─────────────────────────────────────────────────────────────────────────
  test('admin 候选审核 → 通过 → 状态变更为已通过', async ({ page }) => {
    // Step 1: 导航到报表配置主模板管理页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config-baseline`)
    await expect(page.locator('.gt-rcb')).toBeVisible({ timeout: 15000 })

    // Step 2: 切换到"候选审核" tab（仅 admin 可见）
    const reviewTab = page.locator('.el-tabs__item').filter({ hasText: '候选审核' })
    await expect(reviewTab).toBeVisible({ timeout: 3000 })
    await reviewTab.click()

    // Step 3: 确认筛选为"待审核"状态
    const statusSelect = page.locator('.rcb-toolbar .el-select').first()
    await expect(statusSelect).toContainText('待审核')

    // Step 4: 等待候选列表加载
    const candidateTable = page.locator('.el-table')
    await expect(candidateTable).toBeVisible({ timeout: 10000 })

    // Step 5: 点击第一条候选的"通过"按钮
    const approveBtn = page.locator('button:has-text("通过")').first()
    await expect(approveBtn).toBeVisible({ timeout: 5000 })
    await approveBtn.click()

    // Step 6: 确认弹窗
    const confirmDialog = page.locator('.el-message-box')
    await expect(confirmDialog).toBeVisible({ timeout: 3000 })
    await expect(confirmDialog).toContainText('确认通过')
    const confirmBtn = confirmDialog.locator('button:has-text("确认通过")')
    await confirmBtn.click()

    // Step 7: 验证成功提示
    const successMsg = page.locator('.el-message--success')
    await expect(successMsg).toBeVisible({ timeout: 5000 })
    await expect(successMsg).toContainText('候选已通过')
  })

  test('admin 候选审核 → 驳回 → 状态变更为已驳回', async ({ page }) => {
    // Step 1: 导航到报表配置主模板管理页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config-baseline`)
    await expect(page.locator('.gt-rcb')).toBeVisible({ timeout: 15000 })

    // Step 2: 切换到"候选审核" tab
    const reviewTab = page.locator('.el-tabs__item').filter({ hasText: '候选审核' })
    await reviewTab.click()

    // Step 3: 等待候选列表加载
    await page.waitForTimeout(1000)

    // Step 4: 点击第一条候选的"驳回"按钮
    const rejectBtn = page.locator('button:has-text("驳回")').first()
    await expect(rejectBtn).toBeVisible({ timeout: 5000 })
    await rejectBtn.click()

    // Step 5: 确认弹窗
    const confirmDialog = page.locator('.el-message-box')
    await expect(confirmDialog).toBeVisible({ timeout: 3000 })
    await expect(confirmDialog).toContainText('确认驳回')
    const confirmBtn = confirmDialog.locator('button:has-text("确认驳回")')
    await confirmBtn.click()

    // Step 6: 验证成功提示
    const successMsg = page.locator('.el-message--success')
    await expect(successMsg).toBeVisible({ timeout: 5000 })
    await expect(successMsg).toContainText('候选已驳回')
  })

  // ─────────────────────────────────────────────────────────────────────────
  // 场景 3：主模板更新后 → 克隆项目页面 → stale banner 显示
  //         → 点击"同步主模板更新" → 同步成功
  // Validates: Requirements 2.3
  // ─────────────────────────────────────────────────────────────────────────
  test('主模板更新后克隆项目显示 stale banner → 同步主模板更新成功', async ({ page, request }) => {
    // 前置条件：需要一个已克隆项目且 is_stale=true 的状态
    // 可通过 API 先触发主模板更新来制造 stale 状态

    // Step 1: （可选）通过 API 触发主模板更新以制造 stale 状态
    // POST /api/report-config/update 修改 standard 级配置
    // 这会触发 EventBus REPORT_CONFIG_MASTER_UPDATED → handler 标记克隆项目 is_stale

    // Step 2: 导航到克隆项目的报表配置主模板管理页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config-baseline`)
    await expect(page.locator('.gt-rcb')).toBeVisible({ timeout: 15000 })

    // Step 3: 验证 stale banner 显示
    const staleBanner = page.locator('.rcb-stale-banner')
    await expect(staleBanner).toBeVisible({ timeout: 5000 })
    // banner 应包含"主模板已更新"文案和 stale 行数
    await expect(staleBanner).toContainText('主模板已更新')
    await expect(staleBanner).toContainText('行配置与主模板不同步')

    // Step 4: 点击"同步主模板更新"按钮
    const syncBtn = staleBanner.locator('button:has-text("同步主模板更新")')
    await expect(syncBtn).toBeVisible()
    await syncBtn.click()

    // Step 5: 确认弹窗（ElMessageBox.confirm 保留本地覆盖提示）
    const confirmDialog = page.locator('.el-message-box')
    await expect(confirmDialog).toBeVisible({ timeout: 3000 })
    await expect(confirmDialog).toContainText('确认同步主模板更新')
    const confirmBtn = confirmDialog.locator('button:has-text("确认同步")')
    await confirmBtn.click()

    // Step 6: 验证同步成功提示
    const successMsg = page.locator('.el-message--success')
    await expect(successMsg).toBeVisible({ timeout: 5000 })
    await expect(successMsg).toContainText('同步完成')

    // Step 7: 验证 stale banner 消失（同步后 is_stale 应重置）
    await expect(staleBanner).not.toBeVisible({ timeout: 5000 })
  })

  test('stale banner 查看差异对话框', async ({ page }) => {
    // Step 1: 导航到有 stale 状态的项目
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config-baseline`)
    await expect(page.locator('.gt-rcb')).toBeVisible({ timeout: 15000 })

    // Step 2: 验证 stale banner 存在
    const staleBanner = page.locator('.rcb-stale-banner')
    await expect(staleBanner).toBeVisible({ timeout: 5000 })

    // Step 3: 点击"查看差异"按钮
    const diffBtn = staleBanner.locator('button:has-text("查看差异")')
    await expect(diffBtn).toBeVisible()
    await diffBtn.click()

    // Step 4: 验证差异对话框弹出
    const diffDialog = page.locator('.el-dialog').filter({ hasText: '项目 vs 主模板差异' })
    await expect(diffDialog).toBeVisible({ timeout: 5000 })

    // Step 5: 验证差异表格包含行次编码、项目公式、主模板公式、差异类型列
    const diffTable = diffDialog.locator('.el-table')
    await expect(diffTable).toBeVisible({ timeout: 5000 })

    // Step 6: 关闭对话框
    const closeBtn = diffDialog.locator('button:has-text("关闭")')
    await closeBtn.click()
    await expect(diffDialog).not.toBeVisible({ timeout: 3000 })
  })
})
