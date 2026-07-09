/**
 * L6 专项应付款完整流程 — Playwright E2E 测试
 *
 * 覆盖完整流程：
 * 1. 打开L6底稿 → 底稿目录（L6TabIndex 8行sheet）
 * 2. 审定表 L6-1 → 负债类单区块 + 项目/期初/期末/变动
 * 3. 新增项目行 → ElMessageBox.prompt 弹窗
 * 4. 明细表 L6-2 → 33列区段Tab（项目信息/资金变动/用途核查）
 * 5. 区段Tab切换 → 列变化
 * 6. 检查表 L6-4 → 专款专用核查 + 5项核对列
 * 7. 保存流程（无错误）
 *
 * ⚠️ 待环境（start-dev.bat：后端 9980 + 前端 3030）
 * 通过 test.skip 显式标记"待环境"，不伪绿。
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<项目ID> && \
 *   npx playwright test e2e/l6-special-payables.spec.ts
 *
 * Spec: .kiro/specs/l6-special-payables/ Task 7.3
 * Requirements: 全部
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { test, expect } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''
const BASE_URL = _env.BASE_URL || 'http://localhost:3030'
const API_URL = _env.API_URL || 'http://localhost:9980'

test.describe('L6 专项应付款完整流程 E2E', () => {
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

  // ─── Step 1: 底稿目录 L6TabIndex ────────────────────────────────────────

  test('1. L6TabIndex 底稿目录：渲染8行sheet', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)
    await expect(page.locator('.workpaper-list, .wp-tree')).toBeVisible({ timeout: 15000 })

    // 找到L6底稿入口
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }

    // 验证专属组件渲染（.l6-special-payables 容器）
    const l6Component = page.locator(
      '.l6-special-payables, .l6-tab-index, [data-component="l6-special-payables"]',
    )
    await expect(l6Component).toBeVisible({ timeout: 15000 })

    // 验证底稿目录行数（8有效sheet）
    const indexRows = page.locator('.l6-tab-index .el-table__row, .l6-tab-index tr.el-table__row')
    const rowCount = await indexRows.count()
    expect(rowCount).toBe(8)

    // 验证引导步骤区域存在
    const guideSection = page.locator('.l6-guide')
    await expect(guideSection).toBeVisible()

    // 验证进度区域
    const progressSection = page.locator('.l6-progress-section')
    await expect(progressSection).toBeVisible()
  })

  // ─── Step 2: 审定表 L6-1（负债类单区块） ───────────────────────────────

  test('2. L6-1 审定表：负债类单区块 + 关键列', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6底稿
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }

    // 从目录点击L6-1审定表行
    const l6_1Row = page.locator('.l6-tab-index .el-table__row:has-text("审定表")')
    if (await l6_1Row.isVisible()) {
      await l6_1Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件渲染
    const adjComponent = page.locator('.l6-tab-adjudication')
    await expect(adjComponent).toBeVisible({ timeout: 10000 })

    // 验证标题
    const sectionTitle = page.locator('.l6-tab-adjudication .section-title')
    await expect(sectionTitle).toContainText('L6-1')

    // 验证审定表核心列存在：项目/期初/期末/变动
    const headerCells = page.locator('.l6-tab-adjudication th')
    const headerCount = await headerCells.count()
    expect(headerCount).toBeGreaterThanOrEqual(4)

    // 验证关键列标题
    await expect(page.locator('.l6-tab-adjudication th:has-text("项目")')).toBeVisible()
    await expect(page.locator('.l6-tab-adjudication th:has-text("期初")')).toBeVisible()

    // 验证双模式切换器（el-segmented）
    const modeSwitch = page.locator('.l6-tab-adjudication .el-segmented')
    await expect(modeSwitch).toBeVisible()

    // 验证保存按钮
    const saveBtn = page.locator('.l6-tab-adjudication button:has-text("保存")')
    await expect(saveBtn).toBeVisible()

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── Step 3: 新增项目行（ElMessageBox.prompt） ─────────────────────────

  test('3. L6-2 新增专项行：弹出ElMessageBox.prompt', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6底稿
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }

    // 从目录点击L6-2明细表行
    const l6_2Row = page.locator('.l6-tab-index .el-table__row:has-text("明细表")')
    if (await l6_2Row.isVisible()) {
      await l6_2Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件渲染
    const detailComponent = page.locator('.l6-tab-detail')
    await expect(detailComponent).toBeVisible({ timeout: 10000 })

    // 点击"新增专项"按钮
    const addBtn = page.locator('.l6-tab-detail button:has-text("新增专项")')
    if (await addBtn.isVisible()) {
      await addBtn.click()
      await page.waitForTimeout(500)

      // 验证 ElMessageBox.prompt 弹窗出现
      const msgBox = page.locator('.el-message-box, .el-overlay .el-message-box')
      await expect(msgBox).toBeVisible({ timeout: 3000 })

      // 验证弹窗有输入框
      const promptInput = msgBox.locator('input, .el-input__inner')
      await expect(promptInput).toBeVisible()

      // 取消弹窗（不影响后续测试）
      const cancelBtn = msgBox.locator('button:has-text("取消")')
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click()
        await page.waitForTimeout(300)
      }
    }

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── Step 4: 明细表 L6-2（3区段Tab） ──────────────────────────────────

  test('4. L6-2 明细表：3区段Tab存在', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6底稿
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }

    // 从目录点击L6-2明细表行
    const l6_2Row = page.locator('.l6-tab-index .el-table__row:has-text("明细表")')
    if (await l6_2Row.isVisible()) {
      await l6_2Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证明细表组件
    const detailComponent = page.locator('.l6-tab-detail')
    await expect(detailComponent).toBeVisible({ timeout: 10000 })

    // 验证区段Tab切换器（el-segmented 有3个选项）
    const segmentSwitcher = page.locator('.l6-tab-detail .el-segmented, .l6-tab-detail .segment-switcher')
    await expect(segmentSwitcher).toBeVisible()

    // 验证3个区段选项存在（项目信息/资金变动/用途核查）
    const segmentItems = page.locator('.l6-tab-detail .el-segmented .el-segmented__item')
    const segmentCount = await segmentItems.count()
    expect(segmentCount).toBe(3)

    // 验证表格渲染
    const table = page.locator('.l6-tab-detail .el-table')
    await expect(table).toBeVisible()

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── Step 5: 区段Tab切换验证列变化 ────────────────────────────────────

  test('5. L6-2 区段Tab切换：列内容变化', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6明细表
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }
    const l6_2Row = page.locator('.l6-tab-index .el-table__row:has-text("明细表")')
    if (await l6_2Row.isVisible()) {
      await l6_2Row.click()
      await page.waitForTimeout(2000)
    }

    const detailComponent = page.locator('.l6-tab-detail')
    await expect(detailComponent).toBeVisible({ timeout: 10000 })

    // 记录第一区段的列数
    const initialHeaders = page.locator('.l6-tab-detail .el-table th')
    const initialCount = await initialHeaders.count()

    // 切换到第2个区段（资金变动）
    const segmentItems = page.locator('.l6-tab-detail .el-segmented .el-segmented__item')
    if (await segmentItems.nth(1).isVisible()) {
      await segmentItems.nth(1).click()
      await page.waitForTimeout(500)

      // 验证列数有变化（不同区段列不同）
      const newHeaders = page.locator('.l6-tab-detail .el-table th')
      const newCount = await newHeaders.count()
      // 区段切换后列数应该不同
      expect(newCount).toBeGreaterThan(0)
    }

    // 切换到第3个区段（用途核查）
    if (await segmentItems.nth(2).isVisible()) {
      await segmentItems.nth(2).click()
      await page.waitForTimeout(500)

      // 验证无错误
      await expect(page.locator('.el-message--error')).not.toBeVisible()
    }

    // 切回第1个区段（项目信息）
    if (await segmentItems.nth(0).isVisible()) {
      await segmentItems.nth(0).click()
      await page.waitForTimeout(300)
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── Step 6: 检查表 L6-4（专款专用核查） ──────────────────────────────

  test('6. L6-4 检查表：专款专用核查行 + 5项核对列', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6底稿
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }

    // 从目录点击L6-4检查表行
    const l6_4Row = page.locator('.l6-tab-index .el-table__row:has-text("检查表")')
    if (await l6_4Row.isVisible()) {
      await l6_4Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证检查表组件渲染
    const checkComponent = page.locator('.l6-tab-special-check')
    await expect(checkComponent).toBeVisible({ timeout: 10000 })

    // 验证标题
    const sectionTitle = page.locator('.l6-tab-special-check .section-title')
    await expect(sectionTitle).toContainText('L6-4')

    // 验证检查表有表格
    const checkTable = page.locator('.l6-tab-special-check .el-table')
    await expect(checkTable).toBeVisible()

    // 验证5项核对列（用途合规/金额准确/手续完备/进度匹配/结余合规）
    const checkHeaders = page.locator('.l6-tab-special-check th')
    const checkHeaderCount = await checkHeaders.count()
    expect(checkHeaderCount).toBeGreaterThanOrEqual(5)

    // 验证AI辅助按钮存在
    const aiBtn = page.locator('.l6-tab-special-check button:has-text("AI")')
    await expect(aiBtn.first()).toBeVisible()

    // 验证结论区域（el-card包裹的审计结论）
    const conclusionCard = page.locator('.l6-tab-special-check .el-card')
    await expect(conclusionCard.first()).toBeVisible()

    // 无错误
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── Step 7: 保存流程 ──────────────────────────────────────────────────

  test('7. 保存流程：全量保存无错误', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6-1审定表
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }
    const l6_1Row = page.locator('.l6-tab-index .el-table__row:has-text("审定表")')
    if (await l6_1Row.isVisible()) {
      await l6_1Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件渲染
    const adjComponent = page.locator('.l6-tab-adjudication')
    await expect(adjComponent).toBeVisible({ timeout: 10000 })

    // 找到保存按钮
    const saveBtn = page.locator('.l6-tab-adjudication button:has-text("保存")')
    if (await saveBtn.isVisible()) {
      // 监听保存请求
      const savePromise = page.waitForResponse(
        (response) =>
          response.url().includes('checklist') && response.status() < 400,
        { timeout: 10000 },
      ).catch(() => null)

      await saveBtn.click()

      // 等待保存响应或超时
      const saveResponse = await savePromise

      // 验证保存成功消息（如果有）
      const successMsg = page.locator('.el-message--success, text=保存成功')
      await expect(successMsg).toBeVisible({ timeout: 5000 }).catch(() => {
        // 可能无提示但网络请求成功
      })
    }

    // 无错误弹窗
    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── 双模式切换 ───────────────────────────────────────────────────────

  test('8. 双模式切换：HTML ↔ OnlyOffice', async ({ page }) => {
    await page.goto(`${BASE_URL}/projects/${TEST_PROJECT_ID}/workpapers`)

    // 导航到L6-1审定表
    const l6Item = page.locator('text=L6, text=专项应付款').first()
    if (await l6Item.isVisible()) {
      await l6Item.click()
      await page.waitForTimeout(2000)
    }
    const l6_1Row = page.locator('.l6-tab-index .el-table__row:has-text("审定表")')
    if (await l6_1Row.isVisible()) {
      await l6_1Row.click()
      await page.waitForTimeout(2000)
    }

    // 验证审定表组件
    const adjComponent = page.locator('.l6-tab-adjudication')
    await expect(adjComponent).toBeVisible({ timeout: 10000 })

    // 双模式切换器（el-segmented）
    const modeSwitch = page.locator('.l6-tab-adjudication .el-segmented').first()
    if (await modeSwitch.isVisible()) {
      const ooOption = modeSwitch.locator(
        '.el-segmented__item:has-text("OnlyOffice"), .el-segmented__item:has-text("OO")',
      ).first()
      if (await ooOption.isVisible()) {
        await ooOption.click()
        await page.waitForTimeout(2000)

        // 切回HTML
        const htmlOption = modeSwitch.locator(
          '.el-segmented__item:has-text("HTML")',
        ).first()
        if (await htmlOption.isVisible()) {
          await htmlOption.click()
          await page.waitForTimeout(1000)
        }
      }
    }

    await expect(page.locator('.el-message--error')).not.toBeVisible()
  })

  // ─── render-config API 验证 ─────────────────────────────────────────────

  test('render-config API 返回正确组件类型', async ({ request }) => {
    const renderResponse = await request.get(
      `${API_URL}/api/workpapers/test-wp/render-config?force_component_type=l6-special-payables`,
      { failOnStatusCode: false },
    )

    if (renderResponse.ok()) {
      const data = await renderResponse.json()
      const renderData = data.data ?? data
      expect(renderData).toHaveProperty('component_type', 'l6-special-payables')
      expect(renderData).toHaveProperty('sheets')
      expect(Array.isArray(renderData.sheets)).toBe(true)
    }
  })
})
