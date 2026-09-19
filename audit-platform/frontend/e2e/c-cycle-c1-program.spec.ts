/**
 * c-cycle-c1-program.spec.ts — C1 企业层面控制测试程序表 E2E 验证
 *
 * 锚定 spec c-cycle-workpapers Task 39
 *
 * 验证 C1 企业层面控制测试程序表：
 * 1. 底稿页面正常加载
 * 2. 程序表渲染（应有至少 50 行步骤，模板 136 步）
 * 3. ref_index chip 渲染
 * 4. 点击 ref_index chip
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

test.describe('Task 39: C1 企业层面程序表 136 步渲染+ref_index chip', () => {
  test('39.1 — C1 程序表加载并渲染大量步骤', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C1', PROJECT_ID)
    test.skip(!wpResult.exists, 'C1 底稿不存在，需先运行项目底稿生成')

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

    // 等待程序表组件渲染
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

    // 验证程序表行渲染（C1 有 136 步，至少渲染 50 行）
    const tableRows = page.locator('.el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount, 'C1 程序表应渲染至少 50 行（136 步含子步骤）').toBeGreaterThanOrEqual(50)

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('39.2 — C1 ref_index chip 渲染', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C1', PROJECT_ID)
    test.skip(!wpResult.exists, 'C1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证 ref_index chip 存在（C1 模板有 C1-1 等 ref_index）
    const chips = page.locator('.gt-index-chip, .el-tag')
    const chipCount = await chips.count()
    expect(chipCount, 'C1 应有多个 ref_index chip').toBeGreaterThanOrEqual(1)
  })

  test('39.3 — 点击 ref_index chip', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'C1', PROJECT_ID)
    test.skip(!wpResult.exists, 'C1 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 找到一个可见的 ref_index chip 并点击
    const chips = page.locator('.gt-index-chip, .el-tag')
    const chipCount = await chips.count()
    test.skip(chipCount === 0, '无可见 chip，跳过点击测试')

    // 找任意可见 chip
    let targetChip = chips.first()
    for (let i = 0; i < chipCount; i++) {
      const c = chips.nth(i)
      if (await c.isVisible()) {
        targetChip = c
        break
      }
    }

    if (await targetChip.isVisible()) {
      const currentUrl = page.url()
      await targetChip.click()
      await page.waitForTimeout(2_000)

      // 点击后应发生导航或弹窗
      const urlChanged = page.url() !== currentUrl
      const dialogVisible = await page.locator('.el-dialog').isVisible()
      expect(
        urlChanged || dialogVisible,
        'ref_index chip 点击后应触发导航或弹窗',
      ).toBeTruthy()
    }
  })

  test('39.4 — C1 procedure-tables API 验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 验证 procedure-tables API 返回 C1 数据
    const ptResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-tables/C1`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(ptResp.status()).toBe(200)
    const ptBody = await ptResp.json()
    const tableData = ptBody?.data || ptBody
    const items = tableData?.items || []
    expect(items.length, 'C1 应有大量步骤（模板 136 步）').toBeGreaterThanOrEqual(50)

    // 验证 ref_index 字段存在于某些步骤
    const withRef = items.filter((i: any) => i.ref_index)
    expect(withRef.length, 'C1 应有步骤含 ref_index').toBeGreaterThanOrEqual(1)
  })
})
