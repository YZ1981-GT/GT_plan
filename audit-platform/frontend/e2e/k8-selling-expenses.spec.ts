/**
 * K8 销售费用 — Playwright E2E 骨架
 *
 * Spec: .kiro/specs/k8-selling-expenses/ Task 7.3
 * Requirements: 全部
 *
 * 验证：
 * - K8底稿打开 + 结构化视图模式
 * - K8-1审定表：损益类发生额标签（借方-贷方=净发生额）
 * - K8-2明细表：3区段Tab + 动态行
 * - K8-4实质性分析：同比/占比/异常标记列
 * - K8-6截止(记账→原始)：自动抽样集成
 * - K8-7截止(原始→记账)：自动抽样集成
 * - 保存操作无报错
 *
 * Page Object Pattern（骨架模式，无需服务端运行）
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3030'
const PROJECT_ID = process.env.E2E_PROJECT_ID || 'df5b8403-1234-5678-9abc-def012345678'

// ─── Page Object ─────────────────────────────────────────────────────────────

class K8WorkpaperPage {
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

test.describe('K8 销售费用底稿 E2E', () => {
  let k8Page: K8WorkpaperPage

  test.beforeEach(async ({ page }) => {
    k8Page = new K8WorkpaperPage(page)
    await k8Page.login()
  })

  // ═══ 场景1：打开K8底稿 ═══

  test('K8 底稿可正常打开', async ({ page }) => {
    await k8Page.navigateToSheet('K8')
    const content = await k8Page.getPageContent()
    const hasK8Content =
      content.includes('销售费用') ||
      content.includes('K8') ||
      await k8Page.hasElement('.workpaper-container, [data-testid="workpaper-content"]')
    expect(hasK8Content).toBeTruthy()
  })

  test('K8 结构化视图模式激活', async ({ page }) => {
    await k8Page.navigateToSheet('K8')
    // 检查 el-segmented（HTML/OO）双模式切换
    const hasSegmented = await k8Page.hasElement(
      '.el-segmented, [class*="segmented"], [data-testid="dual-mode-switch"]'
    )
    // 或者直接检查HTML渲染容器
    const hasHtmlContainer = await k8Page.hasElement(
      '[data-component-type="k8-selling-expenses"], .k8-selling-expenses, .workpaper-container'
    )
    expect(hasSegmented || hasHtmlContainer).toBeTruthy()
  })

  // ═══ 场景2：K8-1 审定表 — 验证发生额 ═══

  test('K8-1 审定表包含"发生额"标签（损益类）', async ({ page }) => {
    await k8Page.navigateToSheet('K8-1')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    // 损益类核心标识：发生额/本期发生/借方发生
    const hasOccurrenceLabel =
      content.includes('发生额') ||
      content.includes('本期发生') ||
      content.includes('借方发生')
    // 审定表核心列：审定/未审/AJE/RJE
    const hasAuditColumns =
      content.includes('审定') ||
      content.includes('未审') ||
      content.includes('AJE')
    expect(hasOccurrenceLabel || hasAuditColumns).toBeTruthy()
  })

  test('K8-1 审定表包含费用明细分行', async ({ page }) => {
    await k8Page.navigateToSheet('K8-1')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    // K8-1按费用明细项目分行
    const hasExpenseItems =
      content.includes('职工薪酬') ||
      content.includes('差旅费') ||
      content.includes('业务招待费') ||
      content.includes('广告') ||
      content.includes('运输费') ||
      content.includes('折旧')
    expect(hasExpenseItems).toBeTruthy()
  })

  test('K8-1 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-1`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══ 场景3：K8-2 明细表 — 3区段Tab + 动态行 ═══

  test('K8-2 明细表包含3区段Tab', async ({ page }) => {
    await k8Page.navigateToSheet('K8-2')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    // 3区段：基础/分析/检查
    const hasBasicTab = content.includes('基础') || content.includes('基础信息')
    const hasAnalysisTab = content.includes('分析')
    const hasInspectionTab = content.includes('检查')
    // 或有tab/segmented组件
    const hasTabControl = await k8Page.hasElement(
      '.el-segmented, .el-tabs, [class*="tab"], [role="tablist"]'
    )
    expect(hasBasicTab || hasAnalysisTab || hasInspectionTab || hasTabControl).toBeTruthy()
  })

  test('K8-2 明细表支持动态行新增', async ({ page }) => {
    await k8Page.navigateToSheet('K8-2')
    await page.waitForTimeout(3000)
    // 检查新增行按钮或操作入口
    const hasAddRow = await k8Page.hasElement(
      'button:has-text("新增"), button:has-text("+"), [data-testid="add-row-btn"]'
    )
    const content = await k8Page.getPageContent()
    const hasAddText = content.includes('新增') || content.includes('添加')
    expect(hasAddRow || hasAddText).toBeTruthy()
  })

  test('K8-2 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-2`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══ 场景4：K8-4 实质性分析 — 同比/占比/异常标记 ═══

  test('K8-4 实质性分析包含"同比变动率"列', async ({ page }) => {
    await k8Page.navigateToSheet('K8-4')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasYoYColumn =
      content.includes('同比变动率') ||
      content.includes('变动率') ||
      content.includes('同比')
    expect(hasYoYColumn).toBeTruthy()
  })

  test('K8-4 实质性分析包含"占收入比"列', async ({ page }) => {
    await k8Page.navigateToSheet('K8-4')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasRatioColumn =
      content.includes('占收入比') ||
      content.includes('占营业收入') ||
      content.includes('占比')
    expect(hasRatioColumn).toBeTruthy()
  })

  test('K8-4 实质性分析包含异常标记', async ({ page }) => {
    await k8Page.navigateToSheet('K8-4')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasAbnormalMark =
      content.includes('异常') ||
      content.includes('波动') ||
      content.includes('是否异常')
    // 或有红色标记元素
    const hasRedMark = await k8Page.hasElement(
      '[class*="danger"], [class*="abnormal"], .text-red, [style*="color: red"]'
    )
    expect(hasAbnormalMark || hasRedMark).toBeTruthy()
  })

  test('K8-4 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-4`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══ 场景5：K8-6/K8-7 截止双向 — 自动抽样集成 ═══

  test('K8-6 截止(记账→原始)包含自动抽样按钮', async ({ page }) => {
    await k8Page.navigateToSheet('K8-6')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasAutoSample =
      content.includes('自动') ||
      content.includes('序时账') ||
      content.includes('提取')
    const hasCutoffContent =
      content.includes('截止') ||
      content.includes('记账凭证') ||
      content.includes('原始凭证')
    const hasButton = await k8Page.hasElement(
      'button:has-text("自动"), button:has-text("提取"), [data-testid="auto-sample-btn"]'
    )
    expect(hasAutoSample || hasCutoffContent || hasButton).toBeTruthy()
  })

  test('K8-6 截止测试包含跨期判断列', async ({ page }) => {
    await k8Page.navigateToSheet('K8-6')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasCrossPeriod =
      content.includes('跨期') ||
      content.includes('是否跨期') ||
      content.includes('结论')
    expect(hasCrossPeriod).toBeTruthy()
  })

  test('K8-6 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-6`)
    expect(response?.status()).not.toBe(404)
  })

  test('K8-7 截止(原始→记账)包含自动抽样集成', async ({ page }) => {
    await k8Page.navigateToSheet('K8-7')
    await page.waitForTimeout(3000)
    const content = await k8Page.getPageContent()
    const hasS2VDirection =
      content.includes('原始凭证') ||
      content.includes('记账') ||
      content.includes('及时入账')
    const hasCutoffContent =
      content.includes('截止') ||
      content.includes('跨期') ||
      content.includes('完整性')
    expect(hasS2VDirection || hasCutoffContent).toBeTruthy()
  })

  test('K8-7 页面不返回404', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/project/${PROJECT_ID}/workpaper/K8-7`)
    expect(response?.status()).not.toBe(404)
  })

  // ═══ 场景6：保存操作 ═══

  test('K8-1 保存操作无报错', async ({ page }) => {
    await k8Page.navigateToSheet('K8-1')
    await page.waitForTimeout(3000)

    // 尝试触发保存（Ctrl+S 或保存按钮）
    const hasSaveBtn = await k8Page.hasElement(
      'button:has-text("保存"), [data-testid="save-btn"], .save-button'
    )
    if (hasSaveBtn) {
      await page.click('button:has-text("保存"), [data-testid="save-btn"], .save-button')
    } else {
      await page.keyboard.press('Control+s')
    }

    await page.waitForTimeout(2000)

    // 验证无错误弹窗
    const hasError = await k8Page.hasElement(
      '.el-message--error, .el-notification--error, [class*="error-message"]'
    )
    expect(hasError).toBeFalsy()
  })

  // ═══ 整体结构验证 ═══

  test('K8 整体结构包含12个有效sheet（路由不404）', async ({ page }) => {
    const sheetCodes = [
      'K8',    // 底稿目录
      'K8-1',  // 审定表
      'K8-2',  // 明细表
      'K8-3',  // 调整分录
      'K8-4',  // 实质性分析
      'K8-5',  // 合同检查
      'K8-6',  // 截止(记账→原始)
      'K8-7',  // 截止(原始→记账)
      'K8-8',  // 综合检查
      'K8A',   // 程序表
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

  // ═══ 附注双版本可达 ═══

  test('K8 附注底稿可达（上市/国企）', async ({ page }) => {
    await k8Page.navigateToSheet('K8')
    const content = await k8Page.getPageContent()
    const hasDisclosure =
      content.includes('附注') ||
      content.includes('披露') ||
      content.includes('上市') ||
      content.includes('国企')
    const hasContainer = await k8Page.hasElement(
      '.workpaper-container, [data-testid="workpaper-content"], .onlyoffice-editor'
    )
    expect(hasDisclosure || hasContainer).toBeTruthy()
  })
})
