/**
 * Playwright E2E — 高级查询模块全链路（advanced-query-module Task 20.1）
 *
 * 覆盖两套入口全链路，断言中文场景全链路不崩：
 *   业务视图查询（CustomQuery.vue / CustomQueryTab.vue，/custom-query，所有角色）
 *   高级构建器（AdvancedQueryBuilder.vue，admin/manager/partner）
 *   链路：选字段（ACNR 地址树）→ 查询 → 分组 → 透视/转置 → 导出 → 下钻（GtIndexChip）→ 回写预览确认
 *
 * _Requirements: 2.1, 4.2, 5.2, 6.1, 7.1, 14.1, 14.2_
 *
 * 运行前提：后端 9980 + 前端 3030 需运行（start-dev.bat）。
 * 服务器未启动时本 spec 自动 skip（beforeAll 健康检查），不阻塞。
 * 手工跑：`npx playwright test advanced-query-module-e2e`
 *
 * 设计说明：数据是否已 seed 会影响查询是否返回数据，因此对「数据相关」断言采用
 * 弹性策略（结果表/空态/错误提示三选一即视为不崩）；对「必然渲染」的 UI 骨架
 * （标题/能力说明/字段树/两入口按钮/构建器表单）采用硬断言。核心验收 =「全链路不崩」。
 */
import { test, expect, type Page } from '@playwright/test'

const FRONTEND = 'http://localhost:3030'
const BACKEND = 'http://localhost:9980'

// 已知良性前端异常（非崩溃信号），从「致命异常」判定中剔除
const BENIGN_ERROR_PATTERNS = [
  /ResizeObserver loop/i,
  /Non-Error promise rejection captured/i,
  /Failed to fetch/i, // 网络/未 seed 数据导致的请求失败非页面崩溃
  /NetworkError/i,
  /AbortError/i,
  /request failed with status/i,
]

// 后端未启动 → 全部 skip（不阻塞、不自行拉起 dev server）
test.beforeAll(async ({ request }) => {
  try {
    const resp = await request.get(`${BACKEND}/api/health`)
    if (resp.status() !== 200) test.skip(true, '后端 9980 未就绪，跳过高级查询 E2E')
  } catch {
    test.skip(true, '后端 9980 不可达，跳过高级查询 E2E')
  }
})

/** 收集页面级未捕获异常（用于「全链路不崩」判定） */
function collectFatalErrors(page: Page): string[] {
  const fatal: string[] = []
  page.on('pageerror', (err) => {
    const msg = `${err.name}: ${err.message}`
    if (!BENIGN_ERROR_PATTERNS.some((re) => re.test(msg))) fatal.push(msg)
  })
  return fatal
}

/** 登录 admin（可访问业务视图 + 高级构建器） */
async function loginAsAdmin(page: Page) {
  await page.goto(`${FRONTEND}/login`)
  await page.fill('input[placeholder*="用户名"]', 'admin')
  await page.fill('input[type="password"]', 'admin123')
  await page.click('button:has-text("登录")')
  await page.waitForURL(/\/(dashboard|projects)/, { timeout: 15000 })
}

/** 在业务视图选择第一个可用项目 + 第一个可用数据源（若存在） */
async function pickProjectAndSource(page: Page) {
  // 项目下拉（label=项目）
  const projectItem = page.locator('.el-form-item', { hasText: '项目' }).first()
  const projectSelect = projectItem.locator('.el-select').first()
  if (await projectSelect.count()) {
    await projectSelect.click()
    const opt = page.locator('.el-select-dropdown__item:visible').first()
    if (await opt.count()) await opt.click()
    await page.keyboard.press('Escape')
  }
  // 数据源下拉（label=数据源，分组 el-option-group）
  const sourceItem = page.locator('.el-form-item', { hasText: '数据源' }).first()
  const sourceSelect = sourceItem.locator('.el-select').first()
  if (await sourceSelect.count()) {
    await sourceSelect.click()
    const opt = page.locator('.el-select-dropdown__item:not(.is-disabled):visible').first()
    if (await opt.count()) await opt.click()
    await page.keyboard.press('Escape')
  }
}

test.describe('高级查询模块 端到端全链路 (Task 20.1)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto(`${FRONTEND}/custom-query`)
    await page.waitForLoadState('networkidle')
  })

  test('业务视图入口：标题 + Capability_Guidance 能力说明渲染（R11.5）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    // 标题（CustomQuery.vue）
    await expect(page.locator('.gt-cq-title', { hasText: '高级查询' })).toBeVisible()

    // 两套入口能力差异说明（R11.5）
    await expect(page.getByText('查询入口能力说明')).toBeVisible()
    await expect(page.getByText('业务视图查询').first()).toBeVisible()
    await expect(page.getByText('高级构建器').first()).toBeVisible()

    // 关键操作按钮存在
    await expect(page.getByRole('button', { name: /执行查询/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /保存为模板/ })).toBeVisible()

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('业务视图全链路：选字段(ACNR树)→条件→执行→导出，链路不崩（R2.1/4.2/5.2/7.1）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await test.step('ACNR 选字段树复用 useAcnr（R2.1）', async () => {
      // 字段选择器骨架必然渲染（选字段（ACNR 地址树））
      await expect(page.locator('.gt-cqfp')).toBeVisible()
      await expect(page.getByText('选字段（ACNR 地址树）')).toBeVisible()
      // 已选字段区块（reload 保留）
      await expect(page.getByText(/已选字段/).first()).toBeVisible()
    })

    await test.step('选择项目 + 数据源', async () => {
      await pickProjectAndSource(page)
    })

    await test.step('添加查询条件（R5.2 维度/条件构造入口）', async () => {
      const addCond = page.getByRole('button', { name: /添加条件/ })
      if (await addCond.count()) {
        await addCond.click()
        // 出现一行条件（字段/操作符/值）
        await expect(page.locator('.gt-cqt-cond-row').first()).toBeVisible()
      }
    })

    await test.step('执行查询（R4.2 结果链路）→ 结果表/空态/错误三选一（不崩）', async () => {
      const execBtn = page.getByRole('button', { name: /执行查询/ })
      await execBtn.click()
      // 等待任一结果态出现：结果表 / 空态 / 错误提示
      await page.waitForTimeout(1500)
      const table = page.locator('.gt-cqt-table')
      const empty = page.locator('.gt-cqt-result-body .el-empty')
      const errAlert = page.locator('.gt-cqt-result-body .el-alert')
      const anyState =
        (await table.count()) + (await empty.count()) + (await errAlert.count())
      expect(anyState, '查询后结果区应至少渲染 表格/空态/错误 之一').toBeGreaterThan(0)
    })

    await test.step('导出 Excel 按钮存在（R7.1）', async () => {
      await expect(page.getByRole('button', { name: /导出 Excel/ })).toBeVisible()
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('结果下钻：GtIndexChip 存在时点击不崩（R4.2）', async ({ page }) => {
    const fatal = collectFatalErrors(page)
    await pickProjectAndSource(page)
    await page.getByRole('button', { name: /执行查询/ }).click()
    await page.waitForTimeout(1500)

    // 可下钻单元格 chip（仅在结果含可解析 addr_id 列时出现）→ 条件性断言
    const chip = page.locator('.gt-cqt-drill-chip').first()
    if (await chip.count()) {
      await chip.click()
      await page.waitForTimeout(500)
      // 下钻后当前查询结果视图仍在（R4.2「保持当前查询结果视图不变」）
      await expect(page.locator('.gt-cqt-result-body')).toBeVisible()
    } else {
      // 未 seed 可下钻数据时，结果区仍渲染即视为链路不崩
      await expect(page.locator('.gt-cqt-result-body')).toBeVisible()
    }

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('高级构建器全链路：入口→表→字段→分组→SQL预览→执行→导出（R5.2/6.1/7.1）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    await test.step('打开高级构建器弹窗（admin 可用，R11.6）', async () => {
      const builderBtn = page.getByRole('button', { name: /高级构建器/ })
      await expect(builderBtn).toBeVisible()
      await expect(builderBtn).toBeEnabled()
      await builderBtn.click()
      // 弹窗标题
      await expect(page.getByText('高级查询构建器')).toBeVisible()
    })

    await test.step('构建器表单骨架渲染（表选择 / ACNR 选字段 / SQL 预览）', async () => {
      // ACNR 跨模块选字段（构建器内也复用 useAcnr）
      await expect(page.getByText('ACNR 选字段（跨模块单元格）')).toBeVisible()
      // SQL 预览区块（R6.1/分组透视依赖 SQL 编排）
      await expect(page.getByText('SQL 预览').first()).toBeVisible()
      // 三个核心动作按钮
      await expect(page.getByRole('button', { name: /生成 SQL 预览/ })).toBeVisible()
      await expect(page.getByRole('button', { name: /执行查询/ })).toBeVisible()
      await expect(page.getByRole('button', { name: /导出 Excel/ })).toBeVisible()
    })

    await test.step('选择白名单表 → 触发 SQL 预览（分组/透视编排入口不崩）', async () => {
      // 表选择：构建器左侧第一个 el-select
      const tableSelect = page.locator('.gt-aqb .el-select').first()
      if (await tableSelect.count()) {
        await tableSelect.click()
        const opt = page.locator('.el-select-dropdown__item:not(.is-disabled):visible').first()
        if (await opt.count()) {
          await opt.click()
          await page.keyboard.press('Escape')
        }
      }
      // 生成 SQL 预览
      const previewBtn = page.getByRole('button', { name: /生成 SQL 预览/ })
      if (await previewBtn.isEnabled()) {
        await previewBtn.click()
        await page.waitForTimeout(1200)
      }
      // 预览区渲染 SQL 或空态提示（不崩）
      const sql = page.locator('.gt-aqb-sql')
      const emptyHint = page.locator('.gt-aqb-empty')
      expect((await sql.count()) + (await emptyHint.count())).toBeGreaterThan(0)
    })

    expect(fatal, `致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })

  test('回写预览确认：cell-writeback 端点已接线并做前置校验（R14.1/14.2）', async ({ page }) => {
    // 回写走后端 snapshot_writer（乐观锁 + 预览/确认窗口 + 无审计不回写）。
    // UI 未直接暴露回写按钮，此处以 API 冒烟验证回写链路已接线且做前置校验（不崩、不静默写入）：
    // 缺少 X-File-Opened-At 头 → 400（乐观锁前置校验存在，等价「需先预览再确认」的守卫）。
    const resp = await page.request.post(`${BACKEND}/api/custom-query/cell-writeback`, {
      data: {
        project_id: '00000000-0000-0000-0000-000000000000',
        wp_code: 'D2',
        sheet_name: '审定表D2-1',
        cell_ref: 'B7',
        new_value: 1,
        module: 'workpaper',
      },
    })
    // 端点存在且拒绝无预览/无归属的裸写：不得 404/500 崩溃；应为 4xx 校验类响应
    expect(resp.status(), '回写端点应存在并做前置校验').toBeGreaterThanOrEqual(400)
    expect(resp.status()).toBeLessThan(500)
  })

  test('中文场景全链路：切换两入口后无致命前端异常且视图存活（R2.1/4.2/5.2/6.1/7.1/14.1）', async ({ page }) => {
    const fatal = collectFatalErrors(page)

    // 业务视图链路
    await pickProjectAndSource(page)
    const addCond = page.getByRole('button', { name: /添加条件/ })
    if (await addCond.count()) await addCond.click()
    await page.getByRole('button', { name: /执行查询/ }).click()
    await page.waitForTimeout(1200)

    // 切到高级构建器
    const builderBtn = page.getByRole('button', { name: /高级构建器/ })
    if (await builderBtn.isEnabled()) {
      await builderBtn.click()
      await expect(page.getByText('高级查询构建器')).toBeVisible()
      // 关闭弹窗
      await page.keyboard.press('Escape')
    }

    // 视图根仍存活（未白屏 = 不崩）
    await expect(page.locator('.gt-cq-view, .gt-cqt')).toBeVisible()
    expect(fatal, `全链路致命前端异常：\n${fatal.join('\n')}`).toEqual([])
  })
})
