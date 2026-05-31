/**
 * formula-engine-e2e — 公式引擎统一架构 全链路端到端验证
 *
 * 覆盖（需求 7.2）：
 * - 报表公式编辑（ReportConfigEditor 页面 → FormulaEditDialog）
 * - 公式求值（保存后触发内核 execute，结果回显）
 * - 审计历史查询（formula_audit_log GET → audit_log_entries 哈希链）
 *
 * ⚠️ 待环境（start-dev.bat：后端 9980 + 前端 3030）
 * 本测试文件已编写完整用例结构，但因开发环境未启动，
 * 通过 test.skip 显式标记"待环境"，不伪绿。
 *
 * 运行方式：
 *   1. 启动 start-dev.bat（后端 9980 + 前端 3030）
 *   2. 确保测试项目存在且有报表配置数据
 *   3. set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> && \
 *      npx playwright test e2e/formula-engine-e2e.spec.ts
 *
 * Spec: formula-engine-unification Task 19
 * Requirements: 7.2
 */
import { test, expect } from '@playwright/test'

// ─── 环境变量 ───
const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''
const TEST_YEAR = _env.TEST_YEAR || '2025'

test.describe('公式引擎全链路 E2E（formula-engine-unification）', () => {
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 待环境：需 start-dev.bat 启动后端 9980 + 前端 3030
  // 标记不伪绿——环境未就绪时整个 describe 跳过
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  test.skip(
    !RUN_FULL_E2E,
    '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 测试项目数据',
  )

  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/login')
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  test('报表公式编辑 → 求值 → 结果回显', async ({ page }) => {
    // Step 1: 导航到报表配置页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config`)
    await expect(page.locator('.report-config')).toBeVisible({ timeout: 15000 })

    // Step 2: 找到一个公式单元格并点击编辑
    // 报表配置页的公式行通常有 .formula-cell 或可编辑区域
    const formulaCell = page.locator('[data-testid="formula-cell"]').first()
      ?? page.locator('.formula-cell').first()
      ?? page.locator('td.formula').first()
    await formulaCell.click()

    // Step 3: 等待公式编辑对话框弹出（FormulaEditDialog）
    const dialog = page.locator('.el-dialog').filter({ hasText: /公式/ })
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Step 4: 输入/修改公式
    const formulaInput = dialog.locator('textarea, input[type="text"], .formula-input')
      .first()
    const testFormula = "TB('1002','期末余额')"
    await formulaInput.clear()
    await formulaInput.fill(testFormula)

    // Step 5: 触发求值预览（如有预览按钮）
    const previewBtn = dialog.locator('button:has-text("预览"), button:has-text("求值")')
    if (await previewBtn.isVisible()) {
      await previewBtn.click()
      // 验证求值结果显示（应为 Decimal 数值或 0）
      const resultArea = dialog.locator('.formula-result, .preview-result, [data-testid="formula-result"]')
      await expect(resultArea).toBeVisible({ timeout: 5000 })
    }

    // Step 6: 保存公式
    const saveBtn = dialog.locator('button:has-text("保存"), button:has-text("确定")')
    await saveBtn.click()

    // 验证对话框关闭 + 公式已保存（无错误提示）
    await expect(dialog).not.toBeVisible({ timeout: 5000 })
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  test('公式变更后审计历史可查', async ({ page }) => {
    // Step 1: 导航到报表配置页
    await page.goto(`/projects/${TEST_PROJECT_ID}/report-config`)
    await expect(page.locator('.report-config')).toBeVisible({ timeout: 15000 })

    // Step 2: 打开公式历史/审计面板
    // 可能通过工具栏按钮或右键菜单进入
    const historyBtn = page.locator(
      'button:has-text("历史"), button:has-text("变更记录"), [data-testid="formula-history"]',
    )
    if (await historyBtn.isVisible()) {
      await historyBtn.click()
    } else {
      // 备选：通过公式管理中心入口
      const managerBtn = page.locator('button:has-text("公式管理")')
      if (await managerBtn.isVisible()) {
        await managerBtn.click()
      }
    }

    // Step 3: 验证审计历史列表加载
    // GET /api/formula-audit-log/{project_id}/{year} 应返回 formula.changed 记录
    const historyList = page.locator(
      '.audit-history-list, .formula-history, [data-testid="audit-log-list"]',
    )
    await expect(historyList).toBeVisible({ timeout: 10000 })

    // Step 4: 验证历史条目包含关键字段
    const firstEntry = historyList.locator('.history-entry, .audit-entry, tr').first()
    await expect(firstEntry).toBeVisible()
    // 条目应包含：时间、操作者、旧公式/新公式
    await expect(firstEntry).toContainText(/formula|公式|变更/)
  })

  test('API 层验证：公式求值 + 审计写入哈希链', async ({ page, request }) => {
    // 直接调用后端 API 验证全链路数据一致性

    // Step 1: 调用公式求值 API
    const evalResponse = await request.post(
      `http://localhost:9980/api/formula/evaluate`,
      {
        data: {
          project_id: TEST_PROJECT_ID,
          year: parseInt(TEST_YEAR),
          formula: "TB('1002','期末余额')",
        },
        headers: { 'Content-Type': 'application/json' },
      },
    )
    // 求值应成功（200）或返回结构化结果
    expect(evalResponse.ok() || evalResponse.status() === 422).toBeTruthy()

    if (evalResponse.ok()) {
      const evalData = await evalResponse.json()
      // FormulaResult 结构：value + errors + warnings
      expect(evalData).toHaveProperty('value')
      expect(evalData).toHaveProperty('errors')
    }

    // Step 2: 查询审计历史 API
    const auditResponse = await request.get(
      `http://localhost:9980/api/formula-audit-log/${TEST_PROJECT_ID}/${TEST_YEAR}`,
    )
    expect(auditResponse.ok()).toBeTruthy()

    const auditData = await auditResponse.json()
    // 应返回数组，每条含 action_type='formula.changed' 的记录
    expect(Array.isArray(auditData)).toBeTruthy()

    if (auditData.length > 0) {
      const entry = auditData[0]
      // 哈希链字段验证
      expect(entry).toHaveProperty('entry_hash')
      expect(entry).toHaveProperty('prev_hash')
      // payload 含公式变更详情
      expect(entry.details || entry.payload).toBeDefined()
    }
  })
})
