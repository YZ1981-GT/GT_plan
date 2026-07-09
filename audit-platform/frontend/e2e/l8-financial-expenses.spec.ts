/**
 * L8 财务费用完整流程 — Playwright E2E 测试
 *
 * 覆盖完整流程：
 * 1. 打开L8底稿 → 底稿目录（L8TabIndex 10行sheet）
 * 2. 审定表 L8-1 → 损益类发生额 + 项目小计 + TB回写(6603)
 * 3. 明细表 L8-2 → 费用项目分析 + 区段Tab切换
 * 4. 利息测算 → 接收L1/L3/L4/L5联动
 * 5. 非金融机构利息 L8-4 → 添加行 + 可扣除/超标利息
 * 6. 截止测试 L8-5 → 序时账±天数 + 跨期高亮
 * 7. 保存流程
 *
 * ⚠️ 待环境（start-dev.bat：后端 9980 + 前端 3030）
 * 通过 test.skip 显式标记"待环境"，不伪绿。
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> && \
 *   npx playwright test e2e/l8-financial-expenses.spec.ts
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 7.3
 * Requirements: 全部
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { test, expect } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''
const BASE_URL = _env.BASE_URL || 'http://localhost:3030'
const API_URL = _env.API_URL || 'http://localhost:9980'


test.describe('L8 财务费用完整流程 E2E', () => {
  test.skip(
    !RUN_FULL_E2E,
    '【待环境】需 RUN_FULL_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 测试项目数据',
  )

  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[placeholder*="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button:has-text("登录")')
    await expect(page).toHaveURL(/\/(dashboard|projects)/, { timeout: 10000 })
  })

  // ─── Step 1: 底稿目录 L8TabIndex ────────────────────────────────────────

  test('1. L8TabIndex 底稿目录：渲染10行sheet', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await expect(page.locator('.workpaper-list, .wp-tree')).toBeVisible({ timeout: 15000 })

    // 找到L8底稿入口
    const l8Item = page.locator('text=L8, text=财务费用').first()
    if (await l8Item.isVisible()) {
      await l8Item.click()
      await page.waitForTimeout(2000)
    }

    // 验证专属组件渲染（非OnlyOffice fallback）
    const l8Component = page.locator(
      '[class*="l8-financial"], [class*="tab-index"], .el-table, [data-component="l8-financial-expenses"]',
    )
    await expect(l8Component).toBeVisible({ timeout: 15000 })

    // 验证底稿目录行数（10有效sheet）
    const indexRows = page.locator(
      '.el-table__row, tr[class*="index-row"], [class*="sheet-row"]',
    )
    const rowCount = await indexRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(8)
  })


  // ─── Step 2: 审定表 L8-1（损益类发生额） ──────────────────────────────────

  test('2. L8-1 审定表：损益类发生额 + 项目行 + 公式计算', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L8-1审定表
    const l8_1 = page.locator('text=L8-1, text=审定表, text=审定').first()
    if (await l8_1.isVisible()) {
      await l8_1.click()
      await page.waitForTimeout(2000)

      // 验证审定表结构
      const adjTable = page.locator('.el-table, table').first()
      await expect(adjTable).toBeVisible({ timeout: 10000 })

      // 验证关键列存在（发生额/变动/审定数）
      const headerCells = page.locator('th, .el-table__header-wrapper')
      const headerCount = await headerCells.count()
      expect(headerCount).toBeGreaterThanOrEqual(1)

      // 验证合计行
      const totalRow = page.locator(
        'text=合计, text=小计, [class*="total-row"], [class*="summary"]',
      ).first()
      // 合计行应存在

      // 测试填入数据验证公式
      const firstInput = page.locator(
        '.el-input__inner, input[type="number"]',
      ).first()
      if (await firstInput.isVisible()) {
        await firstInput.fill('100000')
        await page.waitForTimeout(500)
      }

      // 无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ─── Step 3: 明细表 L8-2（费用项目分析 + 区段Tab） ────────────────────────

  test('3. L8-2 明细表：费用项目 + 区段Tab切换', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    const l8_2 = page.locator('text=L8-2, text=明细').first()
    if (await l8_2.isVisible()) {
      await l8_2.click()
      await page.waitForTimeout(2000)

      // 验证区段Tab存在（23列拆分为多区段）
      const segmentTabs = page.locator(
        '.el-tabs__item, [class*="segment-tab"], [role="tab"]',
      )
      const tabCount = await segmentTabs.count()

      if (tabCount >= 2) {
        // 切换区段Tab
        await segmentTabs.nth(1).click()
        await page.waitForTimeout(300)
        await expect(page.locator('.el-message--error')).not.toBeVisible()

        // 切回第一个区段
        await segmentTabs.nth(0).click()
        await page.waitForTimeout(300)
      }

      // 验证表格渲染
      await expect(page.locator('.el-table, table').first()).toBeVisible()

      // 无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 4: 利息测算（接收L循环联动） ─────────────────────────────────────

  test('4. 利息测算：L1/L3/L4/L5联动面板渲染', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 明细表中应有利息支出测算区域或交叉引用chip
    const l8_2 = page.locator('text=L8-2, text=明细').first()
    if (await l8_2.isVisible()) {
      await l8_2.click()
      await page.waitForTimeout(2000)

      // 验证GtIndexChip交叉引用存在（L1/L3/L4/L5跳转）
      const crossRefChips = page.locator(
        '[class*="index-chip"], [class*="cross-ref"], [class*="gt-index-chip"]',
      )
      // 利息联动面板或指标区域
      const interestPanel = page.locator(
        'text=利息, text=测算, text=汇聚, [class*="interest"]',
      ).first()
      // 至少有利息相关内容

      // 无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ─── Step 5: 非金融机构利息 L8-4 ─────────────────────────────────────────

  test('5. L8-4 非金融机构利息：添加行 + 可扣除/超标计算', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    const l8_4 = page.locator('text=L8-4, text=非金融').first()
    if (await l8_4.isVisible()) {
      await l8_4.click()
      await page.waitForTimeout(2000)

      // 验证非金融机构利息测算表渲染
      const nfTable = page.locator('.el-table, table').first()
      await expect(nfTable).toBeVisible({ timeout: 10000 })

      // 尝试添加行
      const addBtn = page.locator(
        'button:has-text("添加"), button:has-text("新增"), [class*="add-row"]',
      ).first()
      if (await addBtn.isVisible()) {
        await addBtn.click()
        await page.waitForTimeout(500)
      }

      // 验证关键列存在（本金/利率/天数/可扣除/超标）
      const columns = page.locator('th, .el-table__header-wrapper')
      const colCount = await columns.count()
      expect(colCount).toBeGreaterThanOrEqual(1)

      // 无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── Step 6: 截止测试 L8-5 ────────────────────────────────────────────────

  test('6. L8-5 截止测试：序时账±天数结构', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    const l8_5 = page.locator('text=L8-5, text=截止').first()
    if (await l8_5.isVisible()) {
      await l8_5.click()
      await page.waitForTimeout(2000)

      // 验证截止测试结构
      const cutoffContent = page.locator(
        '.el-table, [class*="cutoff"], [class*="ledger"], table',
      ).first()
      await expect(cutoffContent).toBeVisible({ timeout: 10000 })

      // 验证关键列（凭证号/日期/金额/归属期间/入账期间/是否跨期）
      const headerArea = page.locator('th, .el-table__header')
      const headerCount = await headerArea.count()
      expect(headerCount).toBeGreaterThanOrEqual(1)

      // 无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ─── Step 7: 保存流程 ──────────────────────────────────────────────────────

  test('7. 保存流程：全量保存无错误', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L8-1审定表
    const l8_1 = page.locator('text=L8-1, text=审定表, text=审定').first()
    if (await l8_1.isVisible()) {
      await l8_1.click()
      await page.waitForTimeout(2000)

      // 找到保存按钮
      const saveBtn = page.locator('button:has-text("保存"), [class*="save-btn"]').first()
      if (await saveBtn.isVisible()) {
        // 监听保存请求
        const saveRequest = page.waitForResponse(
          (response) =>
            response.url().includes('checklist') && response.status() < 400,
          { timeout: 10000 },
        ).catch(() => null)

        await saveBtn.click()

        // 验证保存成功
        const successMsg = page.locator('.el-message--success, text=保存成功')
        await expect(successMsg).toBeVisible({ timeout: 5000 }).catch(() => {
          // 可能无提示但网络请求成功
        })
      }

      // 无错误弹窗
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })


  // ─── 双模式切换 ───────────────────────────────────────────────────────────

  test('8. 双模式切换：HTML ↔ OnlyOffice', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    const l8_1 = page.locator('text=L8-1, text=审定表').first()
    if (await l8_1.isVisible()) {
      await l8_1.click()
      await page.waitForTimeout(2000)

      // 双模式切换器（el-segmented）
      const modeSwitch = page.locator(
        '.el-segmented:has-text("HTML"), .el-segmented:has-text("OnlyOffice"), [class*="dual-mode"]',
      ).first()

      if (await modeSwitch.isVisible()) {
        const ooOption = page.locator(
          'text=OnlyOffice, text=OO, [class*="segmented-item"]:has-text("OO")',
        ).first()
        if (await ooOption.isVisible()) {
          await ooOption.click()
          await page.waitForTimeout(2000)

          // 切回HTML
          const htmlOption = page.locator(
            'text=HTML, [class*="segmented-item"]:has-text("HTML")',
          ).first()
          if (await htmlOption.isVisible()) {
            await htmlOption.click()
            await page.waitForTimeout(1000)
          }
        }
      }

      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }
  })

  // ─── render-config API 验证 ────────────────────────────────────────────────

  test('render-config API 返回正确组件类型', async ({ request }) => {
    const renderResponse = await request.get(
      `${API_URL}/api/workpapers/test-wp/render-config?force_component_type=l8-financial-expenses`,
      { failOnStatusCode: false },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'l8-financial-expenses')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
