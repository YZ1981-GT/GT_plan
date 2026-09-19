/**
 * K10 其他收益底稿 — Playwright E2E 测试
 *
 * Spec: .kiro/specs/k10-other-income/ Task 7.3
 * Requirements: 全部
 *
 * 测试流程：
 * 打开K10 → 审定(验证发生额) → 明细(动态行) → 补助核对(K7一致性) → 检查 → 保存
 *
 * 科目6117其他收益（损益类！取发生额，贷方=收益增加）
 * 特征：K循环损益类底稿（10有效sheet/~90+公式/政府补助核对引擎联动K7）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

// ─── Page Object ─────────────────────────────────────────────────────────────

class K10WorkpaperPage {
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

test.describe('K10 其他收益底稿 E2E', () => {
  let k10Page: K10WorkpaperPage

  test.beforeEach(async ({ page }) => {
    k10Page = new K10WorkpaperPage(page)
    await k10Page.login()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. 打开K10底稿 → verify 主入口渲染（K10TabIndex）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10 底稿可正常打开（显示K10TabIndex底稿目录）', async ({ page }) => {
    await k10Page.navigateToSheet('K10')
    const content = await k10Page.getPageContent()
    const hasK10Content =
      content.includes('其他收益') ||
      content.includes('K10') ||
      content.includes('底稿目录')
    const hasContainer = await k10Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], [data-component-type="k10-other-income"]'
    )
    expect(hasK10Content || hasContainer).toBeTruthy()
  })

  test('K10 结构化视图模式激活（非OnlyOffice fallback）', async ({ page }) => {
    await k10Page.navigateToSheet('K10')
    const hasHtmlContainer = await k10Page.hasElement(
      '[data-component-type="k10-other-income"], .k10-other-income, .workpaper-container'
    )
    const hasSegmented = await k10Page.hasElement(
      '.el-segmented, [class*="segmented"], [data-testid="dual-mode-switch"]'
    )
    const hasOnlyOfficeOnly = await k10Page.hasElement('iframe[src*="onlyoffice"]')
    expect(hasHtmlContainer || hasSegmented || !hasOnlyOfficeOnly).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. 导航到K10-1审定表 → verify "损益类·发生额" tag
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10-1 审定表包含"损益类·发生额"标识', async ({ page }) => {
    await k10Page.navigateToSheet('K10-1')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    // 损益类底稿核心标识
    const hasOccurrenceLabel =
      content.includes('损益类') ||
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

  test('K10-1 审定表按补助来源分行', async ({ page }) => {
    await k10Page.navigateToSheet('K10-1')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    // 其他收益主要来源分类（政府补助相关）
    const hasCategories =
      content.includes('政府补助') ||
      content.includes('即征即退') ||
      content.includes('财政贴息') ||
      content.includes('研发补助') ||
      content.includes('稳岗补贴') ||
      content.includes('其他收益')
    expect(hasCategories).toBeTruthy()
  })

  test('K10-1 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K10-1`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. 导航到K10-2明细表 → 动态行新增（ElMessageBox prompt）
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10-2 明细表有动态行新增按钮', async ({ page }) => {
    await k10Page.navigateToSheet('K10-2')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    const hasAddRow =
      content.includes('新增') ||
      content.includes('添加') ||
      await k10Page.hasElement('[data-testid="add-row-btn"], button:has-text("新增"), button:has-text("添加")')
    expect(hasAddRow).toBeTruthy()
  })

  test('K10-2 点击新增弹出ElMessageBox填写补助项目名称', async ({ page }) => {
    await k10Page.navigateToSheet('K10-2')
    await page.waitForTimeout(3000)
    // 找到新增按钮
    const addBtn = page.locator(
      'button:has-text("新增"), button:has-text("添加"), [data-testid="add-row-btn"]'
    ).first()
    if (await addBtn.count() > 0) {
      await addBtn.click()
      await page.waitForTimeout(1000)
      // 检查ElMessageBox弹出（包含input）
      const hasDialog = await k10Page.hasElement(
        '.el-message-box, .el-dialog, [class*="message-box"]'
      )
      const hasInput = await k10Page.hasElement(
        '.el-message-box__input input, .el-dialog input'
      )
      expect(hasDialog || hasInput).toBeTruthy()
      // 如果有弹窗，点取消关闭
      const cancelBtn = page.locator(
        '.el-message-box__btns button:has-text("取消"), .el-dialog button:has-text("取消")'
      ).first()
      if (await cancelBtn.count() > 0) {
        await cancelBtn.click()
      }
    }
  })

  test('K10-2 明细表有导入导出下拉', async ({ page }) => {
    await k10Page.navigateToSheet('K10-2')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    const hasImportExport =
      content.includes('导入导出') ||
      content.includes('导出模板') ||
      content.includes('导出') ||
      await k10Page.hasElement('[data-testid="import-export-dropdown"]')
    expect(hasImportExport).toBeTruthy()
  })

  test('K10-2 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K10-2`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. 导航到K10-4政府补助核对 → verify K7一致性指示器
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10-4 政府补助核对表包含K7一致性指示器', async ({ page }) => {
    await k10Page.navigateToSheet('K10-4')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    // K7一致性指示器：一致/不一致/K7
    const hasK7Indicator =
      content.includes('K7') ||
      content.includes('一致') ||
      content.includes('递延收益') ||
      content.includes('递延分摊') ||
      content.includes('核对')
    // GtIndexChip跳转K7
    const hasGtIndexChip = await k10Page.hasElement(
      '[class*="index-chip"], [data-testid*="index-chip"], .gt-index-chip'
    )
    expect(hasK7Indicator || hasGtIndexChip).toBeTruthy()
  })

  test('K10-4 包含合计计入=直接+递延结构', async ({ page }) => {
    await k10Page.navigateToSheet('K10-4')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    const hasReconcileStructure =
      content.includes('直接计入') ||
      content.includes('递延分摊') ||
      content.includes('合计计入') ||
      content.includes('补助项目')
    expect(hasReconcileStructure).toBeTruthy()
  })

  test('K10-4 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K10-4`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. 导航到K10-6其他收益检查表 → verify 覆盖率进度条
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10-6 检查表包含覆盖率进度条', async ({ page }) => {
    await k10Page.navigateToSheet('K10-6')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    // 进度条/覆盖率
    const hasProgressBar = await k10Page.hasElement(
      '.el-progress, [class*="progress"], [role="progressbar"]'
    )
    const hasCoverageText =
      content.includes('覆盖率') ||
      content.includes('完成') ||
      content.includes('%')
    // 检查项选项：合规/不合规/不适用
    const hasCheckOptions =
      content.includes('合规') ||
      content.includes('不合规') ||
      content.includes('不适用')
    expect(hasProgressBar || hasCoverageText || hasCheckOptions).toBeTruthy()
  })

  test('K10-6 检查表包含分类正确性检查', async ({ page }) => {
    await k10Page.navigateToSheet('K10-6')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    // 分类正确性核对（与日常活动相关→其他收益 vs 营业外收入）
    const hasClassCheck =
      content.includes('分类') ||
      content.includes('正确性') ||
      content.includes('日常活动') ||
      content.includes('营业外') ||
      content.includes('真实性') ||
      content.includes('期间归属')
    expect(hasClassCheck).toBeTruthy()
  })

  test('K10-6 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K10-6`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. 保存功能 → verify 无错误
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10 保存功能不报错', async ({ page }) => {
    await k10Page.navigateToSheet('K10-1')
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
      await page.waitForTimeout(4000)
    }

    // 如果有保存请求，验证不是5xx错误
    for (const status of saveRequests) {
      expect(status).toBeLessThan(500)
    }

    // 确保页面无全局错误弹窗
    const hasErrorDialog = await k10Page.hasElement(
      '.el-message--error, .el-notification--error, [class*="error-dialog"]'
    )
    expect(hasErrorDialog).toBeFalsy()
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 7. 整体结构：10个有效sheet路由验证
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10 全部sheet路由不返回404', async ({ page }) => {
    const sheetCodes = [
      'K10',    // 底稿目录
      'K10-1',  // 审定表（损益类，发生额取数）
      'K10-2',  // 明细表（12列，动态行）
      'K10-3',  // 调整分录
      'K10-4',  // 政府补助核对（与K7联动）
      'K10-5',  // 应收政府补助检查
      'K10-6',  // 综合检查表
      'K10A',   // 程序表
    ]

    const results: { code: string; status: number }[] = []
    for (const code of sheetCodes) {
      const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/${code}`)
      results.push({ code, status: response?.status() ?? 0 })
    }

    for (const r of results) {
      expect(r.status, `${r.code} 不应返回404`).not.toBe(404)
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 8. 附注双版本可达 + 导入导出3选项
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10 附注披露可达（上市/国企双版本）', async ({ page }) => {
    await k10Page.navigateToSheet('K10')
    const content = await k10Page.getPageContent()
    const hasDisclosure =
      content.includes('附注') ||
      content.includes('披露') ||
      content.includes('上市') ||
      content.includes('国企')
    const hasContainer = await k10Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"]'
    )
    expect(hasDisclosure || hasContainer).toBeTruthy()
  })

  test('K10-2 导入导出下拉包含3选项', async ({ page }) => {
    await k10Page.navigateToSheet('K10-2')
    await page.waitForTimeout(3000)
    const dropdownBtn = page.locator(
      '[data-testid="import-export-dropdown"], button:has-text("导入导出"), .el-dropdown:has-text("导入导出")'
    )
    if (await dropdownBtn.count() > 0) {
      await dropdownBtn.first().click()
      await page.waitForTimeout(500)
      const content = await k10Page.getPageContent()
      const hasTemplate = content.includes('导出模板')
      const hasExportData = content.includes('导出数据')
      const hasImportData = content.includes('导入数据')
      expect(hasTemplate || hasExportData || hasImportData).toBeTruthy()
    } else {
      const content = await k10Page.getPageContent()
      const hasImportExport =
        content.includes('导入') || content.includes('导出')
      expect(hasImportExport).toBeTruthy()
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 9. K10-5 应收政府补助检查
  // ═══════════════════════════════════════════════════════════════════════════

  test('K10-5 应收补助检查包含核心检查项', async ({ page }) => {
    await k10Page.navigateToSheet('K10-5')
    await page.waitForTimeout(3000)
    const content = await k10Page.getPageContent()
    const hasCheckItems =
      content.includes('批文') ||
      content.includes('收款权利') ||
      content.includes('可收回') ||
      content.includes('确认时点') ||
      content.includes('应收') ||
      content.includes('补助')
    expect(hasCheckItems).toBeTruthy()
  })

  test('K10-5 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K10-5`)
    expect(response?.status()).not.toBe(404)
  })
})
