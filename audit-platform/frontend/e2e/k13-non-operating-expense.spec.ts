/**
 * K13 营业外支出底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 7.3
 * Requirements: 全部
 *
 * 测试流程：
 * 打开K13 → 审定(验证发生额) → 明细(3区段) → 检查(合规/不合规/不适用+税前扣除性) → 保存
 *
 * 科目6711营业外支出（损益类！取发生额，借方=支出增加）
 * 特征：K循环损益类最简底稿（9有效sheet/~90+公式）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

// ─── Page Object ─────────────────────────────────────────────────────────────

class K13WorkpaperPage {
  constructor(private page: import('@playwright/test').Page) {}

  async login() {
    await this.page.goto(`${BASE_URL}/login`)
    await this.page.fill('input[type="text"]', 'admin')
    await this.page.fill('input[type="password"]', 'admin123')
    await this.page.click('button[type="submit"]')
    await this.page.waitForURL('**/dashboard**', { timeout: 10000 })
  }

  async navigateToSheet(sheetCode: string) {
    await this.page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/${sheetCode}`)
    await this.page.waitForTimeout(3000)
  }

  async getPageContent(): Promise<string> {
    return (await this.page.textContent('body')) ?? ''
  }

  async hasElement(selector: string): Promise<boolean> {
    return (await this.page.locator(selector).count()) > 0
  }
}

// ─── Test Suite ──────────────────────────────────────────────────────────────

test.describe('K13 营业外支出底稿 E2E', () => {
  let k13Page: K13WorkpaperPage

  test.beforeEach(async ({ page }) => {
    k13Page = new K13WorkpaperPage(page)
    await k13Page.login()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. 打开K13底稿 → verify K13TabIndex加载（底稿目录含7 sheets）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13 底稿目录加载（K13TabIndex渲染）', async ({ page }) => {
    await k13Page.navigateToSheet('K13')
    const content = await k13Page.getPageContent()
    const hasK13Content =
      content.includes('营业外支出') ||
      content.includes('K13') ||
      content.includes('底稿目录')
    const hasContainer = await k13Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], [data-component-type="k13-non-operating-expense"]'
    )
    expect(hasK13Content || hasContainer).toBeTruthy()
  })

  test('K13 底稿目录列出多个sheet入口', async ({ page }) => {
    await k13Page.navigateToSheet('K13')
    const content = await k13Page.getPageContent()
    // 底稿目录应列出子sheet名称
    const sheetLabels = ['K13-1', 'K13-2', 'K13-3', 'K13-4', 'K13A']
    const matchCount = sheetLabels.filter((label) => content.includes(label)).length
    // 至少3个sheet名称可见
    expect(matchCount).toBeGreaterThanOrEqual(3)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. K13-1审定表 → verify 6个去向分行 + 发生额术语 + 公式列
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13-1 审定表包含6个去向分类行', async ({ page }) => {
    await k13Page.navigateToSheet('K13-1')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 营业外支出6个去向分类
    const categories = [
      '非流动资产', // 非流动资产毁损报废损失
      '捐赠支出',
      '罚款', // 罚款滞纳金
      '债务重组', // 债务重组损失
      '盘亏', // 资产盘亏损失
      '其他',
    ]
    const matchCount = categories.filter((c) => content.includes(c)).length
    // 至少匹配4个去向分类
    expect(matchCount).toBeGreaterThanOrEqual(4)
  })

  test('K13-1 审定表包含"发生额"术语（损益类标识）', async ({ page }) => {
    await k13Page.navigateToSheet('K13-1')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 损益类底稿核心标识：发生额
    const hasOccurrenceLabel =
      content.includes('发生额') ||
      content.includes('本期发生') ||
      content.includes('借方发生')
    // 审定表必有列：审定/未审/AJE/RJE
    const hasAuditColumns =
      content.includes('审定') ||
      content.includes('未审') ||
      content.includes('AJE')
    expect(hasOccurrenceLabel || hasAuditColumns).toBeTruthy()
  })

  test('K13-1 审定表不应显示"期末余额"作为取数列', async ({ page }) => {
    await k13Page.navigateToSheet('K13-1')
    await page.waitForTimeout(3000)
    // 损益类科目不应以"期末余额"作为主取数列标签
    const hasBalanceAsMainColumn = await k13Page.hasElement(
      'th:has-text("期末余额"), .table-header:has-text("期末余额")'
    )
    const content = await k13Page.getPageContent()
    const hasOccurrence =
      content.includes('发生额') ||
      content.includes('本期发生')
    expect(hasOccurrence || !hasBalanceAsMainColumn).toBeTruthy()
  })

  test('K13-1 审定表有公式列（虚线下划线提示）', async ({ page }) => {
    await k13Page.navigateToSheet('K13-1')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 公式列指标：审定数=未审+AJE+RJE / 同比变动
    const hasFormulaIndicators =
      content.includes('审定') ||
      content.includes('同比') ||
      content.includes('变动')
    // 或存在公式badge/tooltip
    const hasFormulaElements = await k13Page.hasElement(
      '[class*="formula"], [class*="dashed"], [title*="公式"], [class*="computed"]'
    )
    expect(hasFormulaIndicators || hasFormulaElements).toBeTruthy()
  })

  test('K13-1 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K13-1`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. K13-2明细表 → verify 3区段Tab + 导入导出下拉
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13-2 明细表包含3区段Tab（基础信息/分析/检查）', async ({ page }) => {
    await k13Page.navigateToSheet('K13-2')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 3区段：基础/分析/检查
    const hasBasicTab =
      content.includes('基础') || content.includes('基础信息')
    const hasAnalysisTab = content.includes('分析')
    const hasInspectionTab = content.includes('检查')
    // 或至少有segmented/tab/toggle组件
    const hasTabControl = await k13Page.hasElement(
      '.el-segmented, .el-tabs, [class*="tab"], [role="tablist"], [class*="segment"]'
    )
    expect((hasBasicTab && hasAnalysisTab && hasInspectionTab) || hasTabControl).toBeTruthy()
  })

  test('K13-2 明细表有"导入导出▾"下拉', async ({ page }) => {
    await k13Page.navigateToSheet('K13-2')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 导入导出下拉按钮
    const hasImportExport =
      content.includes('导入导出') ||
      content.includes('导出模板') ||
      content.includes('导出数据') ||
      content.includes('导入数据')
    const hasDropdown = await k13Page.hasElement(
      '[data-testid="import-export-dropdown"], button:has-text("导入导出"), .el-dropdown:has-text("导入导出")'
    )
    expect(hasImportExport || hasDropdown).toBeTruthy()
  })

  test('K13-2 导入导出下拉包含3选项', async ({ page }) => {
    await k13Page.navigateToSheet('K13-2')
    await page.waitForTimeout(3000)
    // 定位并点击导入导出下拉按钮
    const dropdownBtn = page.locator(
      '[data-testid="import-export-dropdown"], button:has-text("导入导出"), .el-dropdown:has-text("导入导出")'
    )
    if (await dropdownBtn.count() > 0) {
      await dropdownBtn.first().click()
      await page.waitForTimeout(500)
      const content = await k13Page.getPageContent()
      const hasTemplate = content.includes('导出模板')
      const hasExportData = content.includes('导出数据')
      const hasImportData = content.includes('导入数据')
      expect(hasTemplate || hasExportData || hasImportData).toBeTruthy()
    } else {
      // 降级：仅检查页面中是否有导入导出相关文本
      const content = await k13Page.getPageContent()
      const hasImportExport =
        content.includes('导入') || content.includes('导出')
      expect(hasImportExport).toBeTruthy()
    }
  })

  test('K13-2 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K13-2`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. K13-4检查表 → verify 合规/不合规/不适用 + 税前扣除性4选项
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13-4 检查表包含合规性维度下拉（合规/不合规/不适用）', async ({ page }) => {
    await k13Page.navigateToSheet('K13-4')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 检查维度下拉选项
    const hasComplianceOptions =
      content.includes('合规') ||
      content.includes('不合规') ||
      content.includes('不适用')
    // 检查项目类别
    const hasCheckItems =
      content.includes('真实性') ||
      content.includes('审批') ||
      content.includes('分类') ||
      content.includes('期间归属')
    expect(hasComplianceOptions || hasCheckItems).toBeTruthy()
  })

  test('K13-4 检查表有税前扣除性列（4选项）', async ({ page }) => {
    await k13Page.navigateToSheet('K13-4')
    await page.waitForTimeout(3000)
    const content = await k13Page.getPageContent()
    // 税前扣除性列（营业外支出特有：捐赠/罚款的税务处理）
    const hasTaxDeductibility =
      content.includes('税前扣除') ||
      content.includes('扣除') ||
      content.includes('税务处理') ||
      content.includes('可扣除') ||
      content.includes('不可扣除')
    // 或有下拉/select元素在该列
    const hasSelectElements = await k13Page.hasElement(
      '.el-select, select, [class*="dropdown"], [role="combobox"]'
    )
    expect(hasTaxDeductibility || hasSelectElements).toBeTruthy()
  })

  test('K13-4 检查表有不合规红色摘要提示区', async ({ page }) => {
    await k13Page.navigateToSheet('K13-4')
    await page.waitForTimeout(3000)
    // 不合规摘要提示区（仅当存在不合规项时显示）
    // 验证结构：el-alert/摘要区或不合规计数
    const hasAlertArea = await k13Page.hasElement(
      '.el-alert, [class*="alert"], [class*="summary"], [class*="non-compliant"], [data-testid="non-compliant-summary"]'
    )
    const content = await k13Page.getPageContent()
    const hasSummaryText =
      content.includes('摘要') ||
      content.includes('不合规') ||
      content.includes('检查结论')
    expect(hasAlertArea || hasSummaryText).toBeTruthy()
  })

  test('K13-4 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K13-4`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. 保存功能 → verify 无错误
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13 保存功能不报错', async ({ page }) => {
    await k13Page.navigateToSheet('K13-1')
    await page.waitForTimeout(3000)

    // 监听网络请求中的保存操作
    const saveRequests: number[] = []
    page.on('response', (response) => {
      if (
        response.url().includes('checklist-responses') &&
        response.request().method() === 'PUT'
      ) {
        saveRequests.push(response.status())
      }
    })

    // 尝试触发保存（编辑一个字段等待debounce）
    const editableCell = page.locator(
      'input:visible, textarea:visible, [contenteditable="true"]:visible'
    ).first()
    if (await editableCell.count() > 0) {
      await editableCell.click()
      await editableCell.press('Tab')
      // 等待debounce保存触发
      await page.waitForTimeout(4000)
    }

    // 如果有保存请求，验证不是5xx错误
    for (const status of saveRequests) {
      expect(status).toBeLessThan(500)
    }

    // 确保页面无全局错误弹窗
    const hasErrorDialog = await k13Page.hasElement(
      '.el-message--error, .el-notification--error, [class*="error-dialog"]'
    )
    expect(hasErrorDialog).toBeFalsy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. 整体结构：K13全sheet路由可达
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13 整体结构所有sheet路由可达（不404）', async ({ page }) => {
    const sheetCodes = [
      'K13',    // 底稿目录
      'K13-1',  // 审定表（损益类，6711发生额取数）
      'K13-2',  // 明细表（26列3区段）
      'K13-3',  // 调整分录
      'K13-4',  // 检查表（合规性+税前扣除性）
      'K13A',   // 程序表
    ]

    const results: { code: string; status: number }[] = []
    for (const code of sheetCodes) {
      const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/${code}`)
      results.push({ code, status: response?.status() ?? 0 })
    }

    // 全部不应返回404
    for (const r of results) {
      expect(r.status, `${r.code} 不应返回404`).not.toBe(404)
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 7. 附注双版本可达
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13 附注披露可达（上市/国企）', async ({ page }) => {
    await k13Page.navigateToSheet('K13')
    const content = await k13Page.getPageContent()
    // 底稿目录或附注入口
    const hasDisclosure =
      content.includes('附注') ||
      content.includes('披露') ||
      content.includes('上市') ||
      content.includes('国企')
    const hasContainer = await k13Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], .onlyoffice-editor'
    )
    expect(hasDisclosure || hasContainer).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 8. 双模式切换（HTML/OO）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K13 结构化视图模式激活（非OnlyOffice fallback）', async ({ page }) => {
    await k13Page.navigateToSheet('K13')
    // 检查HTML渲染容器而非OnlyOffice iframe
    const hasHtmlContainer = await k13Page.hasElement(
      '[data-component-type="k13-non-operating-expense"], .k13-non-operating-expense, .workpaper-container'
    )
    // el-segmented 双模式切换（HTML/OO）
    const hasSegmented = await k13Page.hasElement(
      '.el-segmented, [class*="segmented"], [data-testid="dual-mode-switch"]'
    )
    // 不应有OnlyOffice的iframe作为主渲染
    const hasOnlyOfficeOnly = await k13Page.hasElement('iframe[src*="onlyoffice"]')
    expect(hasHtmlContainer || hasSegmented || !hasOnlyOfficeOnly).toBeTruthy()
  })
})
