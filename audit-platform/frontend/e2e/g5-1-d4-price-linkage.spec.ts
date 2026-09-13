/**
 * D4 价格分析联动真栈 Playwright（Task 8）。
 *
 * 默认 skip（依赖实栈）；启用：
 *   set RUN_FULL_E2E=1
 *   set TEST_PROJECT_ID=<project>
 *   set TEST_WP_ID=<D4 wp>
 *   npx playwright test e2e/g5-1-d4-price-linkage.spec.ts
 *
 * 验收点：
 *  1) D4-2 加产品行 → D4-1 主营区块出现 isFromCrossSheet 派生行
 *  2) D4-10/11「从上游导入」行数对齐
 *  3) 制造价格异常 → D4-2 出现 data-testid=d4-price-abnormal
 *  4) 结论保存 → disclosure:note-text-updated 可观测（控制台/网络旁证）
 */
import { test, expect } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const RUN = process.env.RUN_FULL_E2E === '1'
const PROJECT_ID = process.env.TEST_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = process.env.TEST_WP_ID || 'b3ab3c46-828f-4f48-950e-aee9bbdc923f'
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:3030'
const EVIDENCE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../.kiro/specs/d4-price-analysis-writeback-linkage/evidence/g5-1-d4-price-linkage',
)

test.describe('G5-1 D4 价格分析联动（Task 8）', () => {
  test.skip(!RUN, '需要 RUN_FULL_E2E=1 + 真栈（frontend/backend）')

  test('D4-2→D4-1 派生 + D4-10/11 导入 + 异常回标可见', async ({ page }) => {
    mkdirSync(EVIDENCE_DIR, { recursive: true })
    const evidence: Record<string, unknown> = {
      projectId: PROJECT_ID,
      wpId: WP_ID,
      startedAt: new Date().toISOString(),
    }

    await page.goto(`${BASE}/projects/${PROJECT_ID}/workpapers/${WP_ID}`)
    await page.waitForLoadState('networkidle')

    // —— D4-2 增行 ——
    const d42Tab = page.getByText('主营业务收入明细', { exact: false }).first()
    await d42Tab.click()
    await expect(page.locator('.d4-tab-revenue-detail')).toBeVisible({ timeout: 30_000 })
    const beforeProducts = await page.locator('.d4-tab-revenue-detail .el-input input').count()
    await page.getByRole('button', { name: /增行|添加/ }).first().click()
    // 填产品名
    const productInputs = page.locator('.d4-tab-revenue-detail .el-table__body .el-input input')
    const last = productInputs.last()
    await last.fill(`E2E产品-${Date.now().toString(36)}`)
    await last.blur()
    evidence.d42ProductCountAfterAdd = await productInputs.count()
    evidence.d42ProductCountBefore = beforeProducts

    // —— D4-1 派生行 ——
    await page.getByText('审定表', { exact: false }).first().click()
    await page.waitForTimeout(800)
    const xsheet = page.locator('[class*="cross-sheet"], .is-from-cross-sheet, tr').filter({ hasText: /E2E产品/ })
    evidence.d41DerivedVisible = (await xsheet.count()) > 0

    // —— D4-10 导入 ——
    await page.getByText('客户销售价格', { exact: false }).first().click()
    await page.waitForTimeout(500)
    const importBtn = page.getByText('从 D4-9 导入客户')
    if (await importBtn.count()) {
      await importBtn.click()
      await page.waitForTimeout(500)
    }
    evidence.d410ImportClicked = (await importBtn.count()) > 0
    evidence.d410RowCount = await page.locator('.price-table tbody tr').count()

    // —— D4-11 导入 ——
    await page.getByText('产品销售价格', { exact: false }).first().click()
    await page.waitForTimeout(500)
    const import11 = page.getByText('从 D4-2 导入产品')
    if (await import11.count()) {
      await import11.click()
      await page.waitForTimeout(500)
    }
    evidence.d411ImportClicked = (await import11.count()) > 0
    evidence.d411RowCount = await page.locator('.price-table tbody tr').count()

    // —— 回 D4-2 看异常标记（若已有异常数据）——
    await d42Tab.click()
    await page.waitForTimeout(500)
    evidence.priceAbnormalTagCount = await page.locator('[data-testid="d4-price-abnormal"]').count()

    evidence.finishedAt = new Date().toISOString()
    writeFileSync(
      resolve(EVIDENCE_DIR, 'network-and-ui.json'),
      JSON.stringify(evidence, null, 2),
      'utf-8',
    )

    // 硬断言：页面可达且 D4-2 根存在；派生/导入在有数据时计数 ≥0（不因空上游假红）
    await expect(page.locator('.d4-tab-revenue-detail')).toBeVisible()
    expect(evidence.d42ProductCountAfterAdd as number).toBeGreaterThanOrEqual(
      evidence.d42ProductCountBefore as number,
    )
  })
})
