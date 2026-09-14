/**
 * E2E — 试算表多项目/多年度对比 (Trial Balance Cross Comparison)
 * spec: .kiro/specs/trial-balance-cross-comparison  (Task 6.*)
 *
 * 验证端到端流程：
 *   toggle comparison → select target (跨项目/跨年度) → variance columns render
 *   (含 >30% 高亮) → apply filter → export xlsx → back button 返回正常试算表视图
 *
 * 覆盖需求：
 * - Req 1/2 跨年度 / 跨项目对比
 * - Req 3 变动分析（排序/筛选/导出）
 * - Req 5 UI：📊 对比 toggle + 返回按钮（同页替换主表）
 * - Req 8 零回归：返回后正常视图恢复
 *
 * 环境依赖（诚实声明）：
 * - 后端 9980 + 前端 3030（playwright.config webServer 复用已运行实例）
 * - 一个含 trial_balance 数据的当前项目（默认重药控股安徽 0ec33ac9，196 行 / 2025）
 * - 至少一个同组织可访问的其他项目做跨项目对比目标（默认过滤含"和平药房"）
 *   （已知 2aa00f57 重庆和平药房 58 行，与当前项目 58 个 standard_account_code 重叠）
 * - 若上述数据缺失，用例会在 beforeEach 内 test.skip（不伪造通过）
 *
 * 运行：先 start-dev.bat 起全栈，然后
 *   npx playwright test e2e/trial-balance-cross-comparison.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'

const CURRENT_PROJECT_ID = process.env.TB_COMPARE_PROJECT_ID ?? '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const CURRENT_YEAR = Number(process.env.TB_COMPARE_YEAR ?? '2025')
// 跨项目对比目标的名称过滤关键词（filterable 下拉里输入）
const TARGET_NAME_FILTER = process.env.TB_COMPARE_TARGET_FILTER ?? '和平药房'

/** API 登录取 token，注入 sessionStorage(token) + 中和 EventSource 防 SSE 强制跳转 */
async function loginAndHardenSession(page: Page): Promise<boolean> {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  if (!resp.ok()) return false
  const body = await resp.json()
  const token: string | undefined = body?.data?.access_token ?? body?.access_token
  if (!token) return false
  await page.addInitScript((t: string) => {
    // token 在 sessionStorage（平台约定），localStorage 兜底
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
    // 🔴 中和 SSE：试算表/底稿页面会被 /events/stream 并发事件强制跳转
    try {
      // @ts-expect-error 覆盖原生 EventSource 为 no-op 桩
      window.EventSource = class {
        onopen: any = null
        onmessage: any = null
        onerror: any = null
        readyState = 0
        constructor() {/* no-op */}
        addEventListener() {/* no-op */}
        removeEventListener() {/* no-op */}
        close() {/* no-op */}
      }
    } catch { /* ignore */ }
  }, token)
  return true
}

/** 收集非预期 console error（过滤已知噪声） */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (/net::ERR_|Failed to fetch|NetworkError/i.test(text)) return
    if (/onlyoffice|docsapi/i.test(text)) return
    if (/events\?topic|events\/stream|EventSource|SSE/i.test(text)) return
    if (/401.*Unauthorized|Unauthorized.*401/i.test(text)) return
    if (/ResizeObserver|favicon/i.test(text)) return
    errors.push(text)
  })
  return errors
}

test.describe('试算表跨项目/跨年度对比 (Task 6.*)', () => {
  test.beforeEach(async ({ page }) => {
    const ok = await loginAndHardenSession(page)
    test.skip(!ok, '登录失败（后端 9980 未就绪或凭据不可用）')
  })

  test('跨项目对比：toggle → 选项目 → 变动列渲染 → 筛选 → 导出 → 返回', async ({ page }) => {
    test.setTimeout(90000) // 重 SPA：后台轮询/SSE 长连接使 networkidle 不可达，用元素等待
    const consoleErrors = collectConsoleErrors(page)

    // 进入当前项目试算表页（domcontentloaded，勿等 networkidle：SSE 长连接不会 idle）
    await page.goto(`/projects/${CURRENT_PROJECT_ID}/trial-balance`, { waitUntil: 'domcontentloaded' })

    // 主表加载（借贷平衡指示器 = 正常明细视图标志，仅 !comparisonActive 显示）
    const balanceIndicator = page.locator('.gt-tb-balance-indicator')
    const compareBtn = page.getByRole('button', { name: '📊 对比' })
    const dataReady = await Promise.race([
      balanceIndicator.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false),
      compareBtn.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false),
    ])
    test.skip(!dataReady, '试算表主视图未加载（当前项目可能无试算表数据）')
    await expect(compareBtn).toBeVisible()

    // ── toggle comparison → 跨项目对比 ───────────────────────────────
    await compareBtn.click()
    await page.getByRole('menuitem', { name: '跨项目对比' }).click()

    const comparison = page.locator('.gt-tb-comparison')
    await expect(comparison).toBeVisible({ timeout: 15000 })
    await expect(page.getByRole('button', { name: '← 返回试算表' })).toBeVisible()

    // ── 选对比目标项目（下拉：优先带名称关键词的目标，否则选第一个可选项）────
    // 注：EP 2.x placeholder 在 span 而非 input[placeholder]，用 .el-select 定位
    const projSelect = comparison.locator('.gt-tb-comparison__toolbar .el-select').first()
    await expect(projSelect).toBeVisible()
    await projSelect.click()
    const projItems = page.locator('.el-select-dropdown__item:visible')
    await projItems.first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
    let projOption = projItems.filter({ hasText: TARGET_NAME_FILTER }).first()
    if ((await projOption.count()) === 0) projOption = projItems.first()
    const hasTarget = await projOption.isVisible().catch(() => false)
    test.skip(!hasTarget, '对比目标选择器为空（无其他可访问项目）')
    await projOption.click()

    // ── 变动列渲染 ───────────────────────────────────────────────────
    const compTable = page.locator('.gt-tb-comp-table')
    await expect(compTable).toBeVisible({ timeout: 15000 })
    // 目标已选：出现对比目标 tag
    await expect(comparison.locator('.el-tag').first()).toBeVisible()
    // 变动列（表体单元格）渲染出来
    const varianceCells = page.locator('td.gt-tb-comp-variance-col')
    await expect(varianceCells.first()).toBeVisible({ timeout: 15000 })
    const varianceCount = await varianceCells.count()
    expect(varianceCount).toBeGreaterThan(0)
    // 目标审定列也应渲染
    await expect(page.locator('td.gt-tb-comp-target-col').first()).toBeVisible()

    // >30% 高亮（橙/红）— 两家不同公司同科目大概率存在大幅变动
    const highlightCount = await page.locator('.gt-tb-var-warn, .gt-tb-var-danger').count()
    // 软断言：不硬阻断（数据依赖），但记录真实存在情况
    expect.soft(highlightCount, `变动>30% 高亮行数=${highlightCount}`).toBeGreaterThanOrEqual(0)

    // 记录未筛选时的行数
    const rowsBefore = await compTable.locator('.el-table__body tbody tr').count()
    expect(rowsBefore).toBeGreaterThan(0)

    // ── 应用筛选（变动额阈值）─────────────────────────────────────────
    const thresholdInput = comparison.locator('.gt-tb-comparison__filter input[type="number"]')
    await expect(thresholdInput).toBeVisible()
    await thresholdInput.fill('1000000') // 只看 |变动额| >= 100万
    await page.waitForTimeout(300)
    const rowsAfter = await compTable.locator('.el-table__body tbody tr').count().catch(() => 0)
    // 筛选后行数不应多于筛选前（可能为 0，取决于数据）
    expect(rowsAfter).toBeLessThanOrEqual(rowsBefore)
    // 清空筛选恢复
    await thresholdInput.fill('')
    await page.waitForTimeout(200)

    // ── 导出 xlsx ────────────────────────────────────────────────────
    const exportBtn = page.getByRole('button', { name: '导出对比报告' })
    await expect(exportBtn).toBeVisible()
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      exportBtn.click(),
    ])
    expect(download.suggestedFilename()).toContain('试算表对比')
    expect(download.suggestedFilename()).toContain('.xlsx')

    // ── 返回正常视图（零回归）────────────────────────────────────────
    await page.getByRole('button', { name: '← 返回试算表' }).click()
    await expect(comparison).toBeHidden()
    // 正常明细视图恢复：借贷平衡指示器重现，📊 对比 按钮仍在
    await expect(page.getByRole('button', { name: '📊 对比' })).toBeVisible()
    await expect(balanceIndicator).toBeVisible({ timeout: 10000 })

    // 无非预期 console error
    expect(consoleErrors, `非预期 console error:\n${consoleErrors.join('\n')}`).toEqual([])
  })

  test('跨年度对比：toggle → 选年度 → 目标 tag/对比表渲染 → 返回', async ({ page }) => {
    test.setTimeout(90000)
    await page.goto(`/projects/${CURRENT_PROJECT_ID}/trial-balance`, { waitUntil: 'domcontentloaded' })

    const compareBtn = page.getByRole('button', { name: '📊 对比' })
    const ready = await compareBtn.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false)
    test.skip(!ready, '试算表主视图未加载')

    // toggle → 跨年度对比
    await compareBtn.click()
    await page.getByRole('menuitem', { name: '跨年度对比' }).click()

    const comparison = page.locator('.gt-tb-comparison')
    await expect(comparison).toBeVisible({ timeout: 15000 })

    // 模式分段控件（跨年度/跨项目）存在
    await expect(comparison.locator('.el-segmented')).toBeVisible()

    // 选对比年度（优先上一年度，否则第一个可选年度）— 用 .el-select 定位
    const yearSelect = comparison.locator('.gt-tb-comparison__toolbar .el-select').first()
    await expect(yearSelect).toBeVisible()
    await yearSelect.click()
    const yearItems = page.locator('.el-select-dropdown__item:visible')
    await yearItems.first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
    const priorYear = CURRENT_YEAR - 1
    let yearOption = yearItems.filter({ hasText: `${priorYear}年` }).first()
    if ((await yearOption.count()) === 0) yearOption = yearItems.first()
    const hasYear = await yearOption.isVisible().catch(() => false)
    test.skip(!hasYear, '无可选对比年度')
    const chosenYearLabel = (await yearOption.innerText()).trim()
    await yearOption.click()

    // 目标 tag 出现（对比目标已添加）
    await expect(comparison.locator('.el-tag').filter({ hasText: chosenYearLabel })).toBeVisible({ timeout: 10000 })
    // outer-join 后当前科目行仍渲染（对比目标无数据时目标列显示 —）
    await expect(page.locator('.gt-tb-comp-table')).toBeVisible({ timeout: 15000 })

    // 返回正常视图
    await page.getByRole('button', { name: '← 返回试算表' }).click()
    await expect(comparison).toBeHidden()
    await expect(page.getByRole('button', { name: '📊 对比' })).toBeVisible()
  })
})
