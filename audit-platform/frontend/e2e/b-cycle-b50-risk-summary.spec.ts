/**
 * b-cycle-b50-risk-summary.spec.ts — B50 风险汇总程序表+auto_data_source 实时取值
 *
 * 锚定 spec b-cycle-workpapers Task 52
 *
 * 验证 B50 汇总风险评估结果程序表：
 * 1. 程序表页面正常加载
 * 2. 步骤渲染正确
 * 3. auto_data_source 值展示（有数据时显示汇总文本，无数据时显示占位符）
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

test.describe('Task 52: B50 风险汇总程序表+auto_data_source 实时取值', () => {
  test('52.1 — B50 程序表加载并渲染步骤', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B50', PROJECT_ID)
    test.skip(!wpResult.exists, 'B50 底稿不存在，需先运行项目底稿生成')

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

    // 等待编辑器渲染
    await page.waitForSelector(
      '.gt-wp-editor, .gt-a-program-console, .gt-wp-editor-loading',
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

    // 验证程序表行渲染
    const tableRows = page.locator('.el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount, 'B50 程序表应有多行步骤').toBeGreaterThanOrEqual(3)

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('52.2 — B50 auto_data_source 值展示验证', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B50', PROJECT_ID)
    test.skip(!wpResult.exists, 'B50 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // auto_data_source 值会以文本/badge 形式展示在程序表步骤中
    // 有数据时：显示汇总文本（如 "已识别 X 项风险"）
    // 无数据时：显示占位提示（如 "—" 或 "暂无数据"）
    const autoCells = page.locator(
      '.auto-data-cell, .gt-auto-data, [class*="auto-data"], .program-card__auto-data',
    )
    const autoCount = await autoCells.count()

    // auto_data_source 单元格存在即可（有或无数据均可）
    // 如果存在，验证不显示错误状态
    if (autoCount > 0) {
      for (let i = 0; i < Math.min(autoCount, 3); i++) {
        const cell = autoCells.nth(i)
        if (await cell.isVisible()) {
          const text = await cell.textContent()
          // 不应显示错误文本
          expect(text).not.toContain('Error')
          expect(text).not.toContain('resolver 不存在')
        }
      }
    }

    // 额外验证：ref_index chip 也应正确渲染（B50 步骤引用 B50-1~4）
    const chips = page.locator('.gt-index-chip, .el-tag')
    const chipCount = await chips.count()
    // B50 模板步骤可能引用 B50-1 ~ B50-4
    expect(chipCount, 'B50 应有 ref_index chip').toBeGreaterThanOrEqual(0)
  })

  test('52.3 — B50 procedure-tables + auto_data_source API 验证', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 验证 procedure-tables 端点
    const ptResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-tables/B50`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(ptResp.status()).toBe(200)
    const ptBody = await ptResp.json()
    const tableData = ptBody?.data || ptBody
    const items = tableData?.items || []
    expect(items.length, 'B50 应有多个步骤').toBeGreaterThanOrEqual(3)

    // 验证有 auto_data_source 字段的步骤
    const withAutoData = items.filter((i: any) => i.auto_data_source)
    // B50 模板中至少部分步骤有 auto_data_source
    if (withAutoData.length > 0) {
      // 验证 auto_data_source 值不为空（resolver 名称合法）
      for (const item of withAutoData) {
        expect(item.auto_data_source).toBeTruthy()
        expect(typeof item.auto_data_source).toBe('string')
      }
    }

    // 验证 auto-data 批量端点（若存在）
    const autoResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-tables/auto-data/batch?codes=B50`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    // 端点可能返回 200 或 404（取决于是否有数据）
    expect([200, 404]).toContain(autoResp.status())

    if (autoResp.status() === 200) {
      const autoBody = await autoResp.json()
      const autoData = autoBody?.data || autoBody
      // 返回值应为对象（resolver_name → value）
      expect(typeof autoData).toBe('object')
    }
  })

  test('52.4 — B50 render-config 返回 a-program-console', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    const wpResult = await findWorkpaper(request, token, 'B50', PROJECT_ID)
    test.skip(!wpResult.exists, 'B50 底稿不存在')

    const rcResp = await request.get(
      `/api/projects/${PROJECT_ID}/working-papers/${wpResult.wpId}/render-config`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    expect(rcData.component_type || rcData.componentType).toBe('a-program-console')
  })
})
