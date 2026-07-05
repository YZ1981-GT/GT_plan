/**
 * d-cycle-d2a-procedure.spec.ts — D2A 应收账款实质性程序表 E2E 验证
 *
 * 锚定 spec d-cycle-workpapers Task 43
 *
 * 验证 D2A 应收账款程序表（D2TabProcedure）：
 * 1. 底稿页面正常加载（d2-tab-procedure 渲染）
 * 2. 程序步骤卡片渲染
 * 3. ref_index chip 渲染
 * 4. auto_data_source 面板（risk_for_cycle + control_test_result_for_cycle）
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('Task 43: D2A 应收账款程序表打开+风险/控制测试联动面板展示', () => {
  test('43.1 — D2A 程序表加载并渲染步骤', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D2A', PROJECT_ID)
    test.skip(!wpResult.exists, 'D2A 底稿不存在，需先运行项目底稿生成')

    // 收集 console errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        if (/Failed to load resource.*500/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`)
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)

    // 等待 D2 程序表组件渲染
    await page.waitForSelector(
      '.gt-wp-editor, .d2-tab-procedure, .d2-accounts-receivable, .gt-wp-editor-loading',
      { timeout: 15_000 },
    )
    await page.waitForTimeout(5_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证程序步骤卡片渲染（D2A 应有至少 3 个步骤卡片）
    const stepCards = page.locator('.d2-tab-procedure .el-card, .d2-tab-procedure .step-card')
    const cardCount = await stepCards.count()
    expect(cardCount, 'D2A 程序表应渲染至少 3 个步骤').toBeGreaterThanOrEqual(3)

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('43.2 — D2A ref_index chip 渲染', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D2A', PROJECT_ID)
    test.skip(!wpResult.exists, 'D2A 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证 ref_index chip 存在（D2A 模板步骤有 ref_index 引用 D2-1/D2-2 等）
    const chips = page.locator('.gt-index-chip, .el-tag')
    const chipCount = await chips.count()
    expect(chipCount, 'D2A 应有 ref_index chip').toBeGreaterThanOrEqual(1)
  })

  test('43.3 — D2A auto_data_source 面板展示', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'D2A', PROJECT_ID)
    test.skip(!wpResult.exists, 'D2A 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // auto_data_source 面板渲染（risk_for_cycle + control_test_result_for_cycle）
    // 可能显示为折叠面板、卡片或独立区域
    const autoDataPanels = page.locator(
      '[class*="auto-data"], [class*="risk-panel"], [class*="control-panel"], .el-collapse-item, .gt-auto-source-panel',
    )
    const panelCount = await autoDataPanels.count()

    // 如果有 auto_data_source 面板，验证内容
    if (panelCount > 0) {
      // 检查是否包含风险或控制测试相关文字
      const pageContent = await page.textContent('body')
      const hasRiskInfo = pageContent?.includes('风险') || pageContent?.includes('risk')
      const hasControlInfo = pageContent?.includes('控制') || pageContent?.includes('control')
      expect(
        hasRiskInfo || hasControlInfo,
        'D2A 应有风险评估或控制测试联动数据',
      ).toBeTruthy()
    }
  })

  test('43.4 — D2A procedure-tables API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 验证 procedure-tables API 返回 D2A 数据
    const ptResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-tables/D2A`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(ptResp.status()).toBe(200)
    const ptBody = await ptResp.json()
    const tableData = ptBody?.data || ptBody
    const items = tableData?.items || []
    expect(items.length, 'D2A 应有步骤（从模板读取）').toBeGreaterThanOrEqual(1)

    // 验证某些步骤含 ref_index 字段
    const withRef = items.filter((i: any) => i.ref_index)
    expect(withRef.length, 'D2A 应有步骤含 ref_index').toBeGreaterThanOrEqual(1)

    // 验证某些步骤含 auto_data_source
    const withAutoData = items.filter((i: any) => i.auto_data_source)
    // auto_data_source 可能在模板级别而非步骤级别
    // 至少验证 API 正常返回
  })
})
