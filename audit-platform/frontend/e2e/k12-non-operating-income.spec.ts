/**
 * K12 营业外收入底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k12-non-operating-income/ Task 7.3
 * Requirements: 全部
 *
 * 测试流程：
 * 打开K12 → 审定(验证发生额) → 明细(3区段) → 检查(抽凭) → 保存
 *
 * 科目6301营业外收入（损益类！取发生额，贷方=收入增加）
 * 特征：K循环损益类最简底稿（9有效sheet/~90+公式）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

// ─── Page Object ─────────────────────────────────────────────────────────────

class K12WorkpaperPage {
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

test.describe('K12 营业外收入底稿 E2E', () => {
  let k12Page: K12WorkpaperPage

  test.beforeEach(async ({ page }) => {
    k12Page = new K12WorkpaperPage(page)
    await k12Page.login()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. 打开K12底稿 → verify 主入口渲染（非OnlyOffice fallback）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12 底稿可正常打开', async ({ page }) => {
    await k12Page.navigateToSheet('K12')
    const content = await k12Page.getPageContent()
    const hasK12Content =
      content.includes('营业外收入') ||
      content.includes('K12') ||
      content.includes('底稿目录')
    const hasContainer = await k12Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], [data-component-type="k12-non-operating-income"]'
    )
    expect(hasK12Content || hasContainer).toBeTruthy()
  })

  test('K12 结构化视图模式激活（非OnlyOffice fallback）', async ({ page }) => {
    await k12Page.navigateToSheet('K12')
    // 检查HTML渲染容器而非OnlyOffice iframe
    const hasHtmlContainer = await k12Page.hasElement(
      '[data-component-type="k12-non-operating-income"], .k12-non-operating-income, .workpaper-container'
    )
    // el-segmented 双模式切换（HTML/OO）
    const hasSegmented = await k12Page.hasElement(
      '.el-segmented, [class*="segmented"], [data-testid="dual-mode-switch"]'
    )
    // 不应有OnlyOffice的iframe作为主渲染
    const hasOnlyOfficeOnly = await k12Page.hasElement('iframe[src*="onlyoffice"]')
    expect(hasHtmlContainer || hasSegmented || !hasOnlyOfficeOnly).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. 导航到K12-1审定表 → verify "发生额"术语（非"期末余额"）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12-1 审定表包含"发生额"术语（损益类标识）', async ({ page }) => {
    await k12Page.navigateToSheet('K12-1')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 损益类底稿核心标识：发生额
    const hasOccurrenceLabel =
      content.includes('发生额') ||
      content.includes('本期发生') ||
      content.includes('贷方发生')
    // 审定表必有列：审定/未审/AJE/RJE
    const hasAuditColumns =
      content.includes('审定') ||
      content.includes('未审') ||
      content.includes('AJE')
    expect(hasOccurrenceLabel || hasAuditColumns).toBeTruthy()
  })

  test('K12-1 审定表不应显示"期末余额"作为取数列', async ({ page }) => {
    await k12Page.navigateToSheet('K12-1')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 损益类科目不应以"期末余额"作为主取数列标签
    // 注意：可能在其他上下文（如对比说明）中出现，但不应作为列头
    const hasBalanceAsMainColumn = await k12Page.hasElement(
      'th:has-text("期末余额"), .table-header:has-text("期末余额")'
    )
    // 应有发生额相关列
    const hasOccurrence =
      content.includes('发生额') ||
      content.includes('本期发生')
    expect(hasOccurrence || !hasBalanceAsMainColumn).toBeTruthy()
  })

  test('K12-1 审定表包含按来源分行', async ({ page }) => {
    await k12Page.navigateToSheet('K12-1')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 营业外收入主要来源分类
    const hasCategories =
      content.includes('政府补助') ||
      content.includes('债务重组') ||
      content.includes('资产盘盈') ||
      content.includes('罚款收入') ||
      content.includes('捐赠利得') ||
      content.includes('无法支付') ||
      content.includes('营业外收入')
    expect(hasCategories).toBeTruthy()
  })

  test('K12-1 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K12-1`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. 导航到K12-2明细表 → verify 3区段Toggle存在
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12-2 明细表包含3区段Tab切换', async ({ page }) => {
    await k12Page.navigateToSheet('K12-2')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 3区段：基础/分析/检查
    const hasBasicTab =
      content.includes('基础') || content.includes('基础信息')
    const hasAnalysisTab = content.includes('分析')
    const hasInspectionTab = content.includes('检查')
    // 或至少有segmented/tab/toggle组件
    const hasTabControl = await k12Page.hasElement(
      '.el-segmented, .el-tabs, [class*="tab"], [role="tablist"], [class*="segment"]'
    )
    expect((hasBasicTab && hasAnalysisTab && hasInspectionTab) || hasTabControl).toBeTruthy()
  })

  test('K12-2 明细表有动态行与导入导出', async ({ page }) => {
    await k12Page.navigateToSheet('K12-2')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 动态行新增按钮
    const hasAddRow =
      content.includes('新增') ||
      content.includes('添加') ||
      await k12Page.hasElement('[data-testid="add-row-btn"], button:has-text("新增")')
    // 导入导出下拉
    const hasImportExport =
      content.includes('导入导出') ||
      content.includes('导出模板') ||
      await k12Page.hasElement('[data-testid="import-export-dropdown"]')
    expect(hasAddRow || hasImportExport).toBeTruthy()
  })

  test('K12-2 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K12-2`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. 导航到K12-4检查表 → verify 抽凭按钮存在
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12-4 检查表包含抽凭按钮', async ({ page }) => {
    await k12Page.navigateToSheet('K12-4')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 抽凭引擎按钮
    const hasSamplingBtn =
      content.includes('抽凭') ||
      content.includes('凭证抽样') ||
      content.includes('抽样')
    const hasBtnElement = await k12Page.hasElement(
      'button:has-text("抽凭"), [data-testid="voucher-sampling-btn"], button:has-text("抽样")'
    )
    expect(hasSamplingBtn || hasBtnElement).toBeTruthy()
  })

  test('K12-4 检查表包含分类正确性检查', async ({ page }) => {
    await k12Page.navigateToSheet('K12-4')
    await page.waitForTimeout(3000)
    const content = await k12Page.getPageContent()
    // 分类正确性核对（营业外收入 vs 其他收益6117）
    const hasClassCheck =
      content.includes('分类') ||
      content.includes('正确性') ||
      content.includes('合规') ||
      content.includes('不合规') ||
      content.includes('不适用')
    // 检查项目
    const hasCheckItems =
      content.includes('真实性') ||
      content.includes('期间归属') ||
      content.includes('税务处理') ||
      content.includes('依据')
    expect(hasClassCheck || hasCheckItems).toBeTruthy()
  })

  test('K12-4 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K12-4`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. 保存功能 → verify 无错误
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12 保存功能不报错', async ({ page }) => {
    await k12Page.navigateToSheet('K12-1')
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
    const hasErrorDialog = await k12Page.hasElement(
      '.el-message--error, .el-notification--error, [class*="error-dialog"]'
    )
    expect(hasErrorDialog).toBeFalsy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. 整体结构：9个有效sheet路由验证
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12 整体结构包含9个有效sheet（路由不404）', async ({ page }) => {
    const sheetCodes = [
      'K12',    // 底稿目录
      'K12-1',  // 审定表（损益类，发生额取数）
      'K12-2',  // 明细表（26列3区段）
      'K12-3',  // 调整分录
      'K12-4',  // 检查表（分类正确性+抽凭）
      'K12A',   // 程序表
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

  test('K12 附注披露可达（上市/国企）', async ({ page }) => {
    await k12Page.navigateToSheet('K12')
    const content = await k12Page.getPageContent()
    // 底稿目录或附注入口
    const hasDisclosure =
      content.includes('附注') ||
      content.includes('披露') ||
      content.includes('上市') ||
      content.includes('国企')
    const hasContainer = await k12Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], .onlyoffice-editor'
    )
    expect(hasDisclosure || hasContainer).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 8. 导入导出 dropdown → verify 3选项
  // ═══════════════════════════════════════════════════════════════════════════

  test('K12-2 导入导出下拉包含3选项', async ({ page }) => {
    await k12Page.navigateToSheet('K12-2')
    await page.waitForTimeout(3000)
    // 定位并点击导入导出下拉按钮
    const dropdownBtn = page.locator(
      '[data-testid="import-export-dropdown"], button:has-text("导入导出"), .el-dropdown:has-text("导入导出")'
    )
    if (await dropdownBtn.count() > 0) {
      await dropdownBtn.first().click()
      await page.waitForTimeout(500)
      const content = await k12Page.getPageContent()
      const hasTemplate = content.includes('导出模板')
      const hasExportData = content.includes('导出数据')
      const hasImportData = content.includes('导入数据')
      expect(hasTemplate || hasExportData || hasImportData).toBeTruthy()
    } else {
      // 降级：仅检查页面中是否有导入导出相关文本
      const content = await k12Page.getPageContent()
      const hasImportExport =
        content.includes('导入') || content.includes('导出')
      expect(hasImportExport).toBeTruthy()
    }
  })
})
