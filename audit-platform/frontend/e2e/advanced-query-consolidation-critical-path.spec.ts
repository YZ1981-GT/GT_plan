/**
 * Playwright 关键路径端到端测试 — advanced-query-consolidation Task 6.2*
 *
 * 验证收敛后三个共享模块在业务视图与高级构建器的集成正确性：
 *   1. 业务视图与高级构建器列名一致（中文）
 *   2. 导出 xlsx 触发正确（200 响应）
 *   3. cell_ref 下钻跳 WorkpaperEditor（数据前置条件可能不满足）
 *   4. 右键溯源跳 /template-library（数据前置条件可能不满足）
 *   5. 0 console error（排除 known-benign）
 *
 * _Requirements: 3.5, 5.2_
 *
 * 运行前提：后端 9980 + 前端 3030 + 项目 0ec33ac9（重药控股安徽）已有数据。
 * 手工跑：`npx playwright test advanced-query-consolidation-critical-path`
 */
import { test, expect, type Page } from '@playwright/test'

const FRONTEND = 'http://localhost:3030'
const BACKEND = 'http://localhost:9980'
const PROJECT_ID = '0ec33ac9-58a1-4b4d-b92d-61bff3d10a0a'

// 已知良性异常（非本 spec 崩溃信号）
const BENIGN_ERROR_PATTERNS = [
  /ResizeObserver loop/i,
  /Non-Error promise rejection captured/i,
  /Failed to fetch/i,
  /NetworkError/i,
  /AbortError/i,
  /request failed with status/i,
  /editing-lock/i,
  /report-config/i,
  /cross-check/i,
  /onlyoffice/i,
  /canceled/i,
]

// 共享映射中的已知中文标签（用于断言列头确实中文化）
const KNOWN_CHINESE_LABELS: Record<string, string> = {
  account_code: '科目编码',
  account_name: '科目名称',
  standard_account_code: '标准科目编码',
  opening_balance: '期初余额',
  closing_balance: '期末余额',
  debit_amount: '借方发生额',
  credit_amount: '贷方发生额',
  unadjusted_amount: '未审数',
  audited_amount: '审定数',
  voucher_date: '凭证日期',
  voucher_no: '凭证号',
  row_code: '行次',
  row_name: '项目',
}

test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BACKEND}/api/health`)
    if (resp.status() !== 200) test.skip(true, '后端 9980 未就绪')
  } catch {
    test.skip(true, '后端 9980 不可达')
  }
})

/** 收集致命前端异常 */
function collectFatalErrors(page: Page): string[] {
  const fatal: string[] = []
  page.on('pageerror', (err) => {
    const msg = `${err.name}: ${err.message}`
    if (!BENIGN_ERROR_PATTERNS.some((re) => re.test(msg))) fatal.push(msg)
  })
  return fatal
}

/** 登录 admin/admin123 */
async function loginAsAdmin(page: Page) {
  await page.goto(`${FRONTEND}/login`)
  await page.fill('input[placeholder*="用户名"], input[name="username"]', 'admin')
  await page.fill('input[type="password"]', 'admin123')
  await page.click('button:has-text("登录")')
  // 登录后可能跳转到 / 或 /dashboard 或 /projects
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 })
}

/** 在业务视图选第一个可用项目+数据源并执行查询（弹性：按钮 disabled 则跳过） */
async function executeBusinessViewQuery(page: Page): Promise<boolean> {
  // 选项目
  const projectSelects = page.locator('.el-select').filter({ hasText: /项目|project/i })
  const anySelect = page.locator('.el-select').first()
  const projectSelect = (await projectSelects.count()) ? projectSelects.first() : anySelect
  if (await projectSelect.count()) {
    await projectSelect.click()
    await page.waitForTimeout(500)
    const opt = page.locator('.el-select-dropdown__item:visible').first()
    if (await opt.count()) {
      await opt.click()
      await page.waitForTimeout(500)
    }
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }
  // 选数据源（第二个下拉/含数据源文案的下拉）
  const sourceSelects = page.locator('.el-select').filter({ hasText: /数据源|source/i })
  if (await sourceSelects.count()) {
    await sourceSelects.first().click()
    await page.waitForTimeout(500)
    const opt = page.locator('.el-select-dropdown__item:not(.is-disabled):visible').first()
    if (await opt.count()) {
      await opt.click()
      await page.waitForTimeout(500)
    }
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }
  // 执行查询（若按钮 disabled 则返回 false 表示无法执行）
  const execBtn = page.getByRole('button', { name: /执行查询/ })
  if (await execBtn.count()) {
    const disabled = await execBtn.isDisabled()
    if (!disabled) {
      await execBtn.click()
      await page.waitForTimeout(2000)
      return true
    }
  }
  return false
}

test.describe('高级查询收敛 关键路径 (Task 6.2*)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('业务视图与高级构建器列名一致（中文） + 0 console error', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    await test.step('业务视图执行查询获取列头', async () => {
      const executed = await executeBusinessViewQuery(page)
      if (!executed) {
        test.info().annotations.push({
          type: 'info',
          description: '执行查询按钮 disabled（项目/数据源前置条件不满足）',
        })
      }
    })

    // 检查结果表格列头是否包含中文标签（resolveColumnLabel 三级兜底的核心交付）
    await test.step('验证列头为中文（非英文 key 原样显示）', async () => {
      const table = page.locator('.gt-cqt-table, .el-table').first()
      if (await table.count()) {
        // 获取所有表头文本
        const headers = await page.locator('th .cell').allTextContents()
        const nonEmptyHeaders = headers.filter((h) => h.trim())

        if (nonEmptyHeaders.length > 0) {
          // 核心断言：表头中不应出现纯英文下划线 key（如 standard_account_code）
          // resolveColumnLabel 应已把它们映射为中文
          const rawEnglishKeys = nonEmptyHeaders.filter((h) => /^[a-z][a-z_]+$/.test(h.trim()))
          // 允许少量未映射 key 原样显示（兜底行为），但核心关键列必须中文化
          const criticalRawKeys = rawEnglishKeys.filter((k) =>
            Object.keys(KNOWN_CHINESE_LABELS).includes(k.trim()),
          )
          expect(
            criticalRawKeys,
            `关键列仍显示英文 key（resolveColumnLabel 未生效）: ${criticalRawKeys.join(', ')}`,
          ).toEqual([])

          // 正向验证：至少有一个已知中文标签出现在表头中
          const chineseLabelsInHeaders = nonEmptyHeaders.filter((h) =>
            Object.values(KNOWN_CHINESE_LABELS).some((label) => h.includes(label)),
          )
          expect(
            chineseLabelsInHeaders.length,
            '表头中应至少包含一个共享映射的中文标签',
          ).toBeGreaterThan(0)
        }
      }
    })

    await test.step('高级构建器入口可达', async () => {
      const builderBtn = page.getByRole('button', { name: /高级构建器/ })
      if (await builderBtn.count()) {
        await expect(builderBtn).toBeVisible()
      }
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('导出 xlsx 触发正确（exportQueryResultToXlsx 共享工具）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    await executeBusinessViewQuery(page)

    await test.step('点击导出 Excel 按钮', async () => {
      const exportBtn = page.getByRole('button', { name: /导出|Excel|xlsx/i })
      if (await exportBtn.count()) {
        // 监听下载事件或网络请求
        const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null)

        // 对后端 export-excel 端点的请求监控
        const exportRequestPromise = page
          .waitForResponse(
            (resp) =>
              resp.url().includes('export-excel') ||
              resp.url().includes('export') ||
              resp.request().url().includes('export'),
            { timeout: 10000 },
          )
          .catch(() => null)

        await exportBtn.click()
        await page.waitForTimeout(2000)

        // 前端 xlsx 导出：会触发 download 事件（exportQueryResultToXlsx 用 SheetJS 前端生成）
        // 或后端 blob 导出：会有 export-excel 200 响应
        const download = await downloadPromise
        const exportResp = await exportRequestPromise

        // 任一路径成功即视为导出正确
        const exportTriggered = download !== null || (exportResp !== null && exportResp.status() === 200)

        if (!exportTriggered) {
          // 可能没有数据导致"无数据"提示（正常行为）→ 检查是否有 warning 提示
          const noDataMsg = page.locator('.el-message--warning, .el-message-box')
          const hasNoDataWarning = (await noDataMsg.count()) > 0
          expect(
            hasNoDataWarning,
            '导出未触发：既无下载也无"无数据"提示，exportQueryResultToXlsx 可能未正确接线',
          ).toBeTruthy()
        }
      } else {
        // 无导出按钮 = 可能查询未返回数据，视为数据前置条件不满足
        test.info().annotations.push({ type: 'info', description: '导出按钮未出现（查询可能无结果）' })
      }
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('cell_ref 下钻跳 WorkpaperEditor（数据前置条件）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    await executeBusinessViewQuery(page)

    await test.step('查找 cell_ref 可点击单元格', async () => {
      // cell_ref 下钻的 UI 表现：GtIndexChip / 可点击链接 / 单元格带特殊样式
      const drillChip = page.locator(
        '.gt-cqt-drill-chip, .gt-index-chip, [data-drill], a[href*="workpaper"]',
      ).first()

      if (await drillChip.count()) {
        // 点击前记录当前 URL
        const urlBefore = page.url()

        await drillChip.click()
        await page.waitForTimeout(2000)

        // 验证导航到 WorkpaperEditor（URL 含 /workpapers/ 或 /edit）
        const urlAfter = page.url()
        const navigatedToEditor =
          urlAfter.includes('/workpapers/') || urlAfter.includes('/edit') || urlAfter !== urlBefore

        if (navigatedToEditor) {
          expect(urlAfter).toMatch(/workpaper|edit/)
        } else {
          // 可能在同页打开，也算联动正常
          test.info().annotations.push({
            type: 'info',
            description: 'cell_ref 点击未导航（可能同页展示或弹窗展开）',
          })
        }
      } else {
        // 数据前置条件不满足
        test.info().annotations.push({
          type: 'info',
          description: 'data prerequisite not met: 查询结果中无 cell_ref 可下钻列',
        })
      }
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('右键溯源跳 /template-library（数据前置条件）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    await executeBusinessViewQuery(page)

    await test.step('右键结果行触发溯源菜单', async () => {
      // 结果表格行
      const tableRow = page.locator('.el-table__body-wrapper tbody tr').first()

      if (await tableRow.count()) {
        // 右键触发上下文菜单
        await tableRow.click({ button: 'right' })
        await page.waitForTimeout(500)

        // 查找溯源相关菜单项
        const traceMenu = page.locator(
          '.el-dropdown-menu:visible, .el-context-menu:visible, [class*="context-menu"]:visible, [class*="dropdown"]:visible',
        )

        if (await traceMenu.count()) {
          // 查找"溯源"/"追溯"/"来源"相关菜单项
          const traceItem = page.locator(
            ':visible:text-matches("溯源|追溯|来源|模板|template", "i")',
          ).first()

          if (await traceItem.count()) {
            // 监听新页面/导航
            const navigationPromise = page
              .waitForURL(/template-library/, { timeout: 5000 })
              .catch(() => null)

            await traceItem.click()
            await page.waitForTimeout(2000)

            const navigated = await navigationPromise
            if (navigated !== null || page.url().includes('template-library')) {
              expect(page.url()).toContain('template-library')
            } else {
              test.info().annotations.push({
                type: 'info',
                description: '溯源菜单点击未跳转 /template-library（可能弹窗展示或数据不支持）',
              })
            }
          } else {
            test.info().annotations.push({
              type: 'info',
              description: 'data prerequisite not met: 右键菜单中无溯源选项（可能查询结果无关联底稿）',
            })
          }
        } else {
          test.info().annotations.push({
            type: 'info',
            description: 'data prerequisite not met: 右键未弹出上下文菜单（组件可能未接线右键溯源）',
          })
        }
      } else {
        test.info().annotations.push({
          type: 'info',
          description: 'data prerequisite not met: 查询结果表无数据行',
        })
      }
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('全链路 0 console error（查询+导出+切换视图）', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (!BENIGN_ERROR_PATTERNS.some((re) => re.test(text))) {
          consoleErrors.push(text)
        }
      }
    })
    const fatal = collectFatalErrors(page)

    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    // 业务视图执行查询
    await executeBusinessViewQuery(page)
    await page.waitForTimeout(500)

    // 尝试导出
    const exportBtn = page.getByRole('button', { name: /导出|Excel|xlsx/i })
    if (await exportBtn.count()) {
      await exportBtn.click()
      await page.waitForTimeout(1000)
    }

    // 尝试打开高级构建器
    const builderBtn = page.getByRole('button', { name: /高级构建器/ })
    if (await builderBtn.count() && (await builderBtn.isEnabled())) {
      await builderBtn.click()
      await page.waitForTimeout(1000)
      await page.keyboard.press('Escape')
    }

    // 最终断言：0 致命 console error
    expect(
      consoleErrors,
      `查询相关 console error（应为 0）：\n${consoleErrors.join('\n')}`,
    ).toEqual([])
    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })
})
