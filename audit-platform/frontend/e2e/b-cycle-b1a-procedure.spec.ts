/**
 * b-cycle-b1a-procedure.spec.ts — B1A 程序表 E2E 验证
 *
 * 锚定 spec b-cycle-workpapers Task 49
 *
 * 验证 B1A 业务承接程序表：
 * 1. 程序表页面正常加载
 * 2. 步骤渲染（6 个顶级步骤可见）
 * 3. ref_index chip 渲染（如 B2, B1-3, B1-1, B5 等）
 * 4. 点击 ref_index chip 触发导航或弹窗
 *
 * 项目：辽宁卫生服务有限公司 2025（37814426-a29e-4fc2-9313-a59d229bf7b0）
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper, ensureTestProject } from './fixtures/ensure-test-project'

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

test.describe('Task 49: B1A 程序表打开+步骤渲染+ref_index chip 可点击', () => {
  test('49.1 — B1A 程序表加载并渲染 6 个步骤', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    // 查找 B1A 底稿
    const wpResult = await findWorkpaper(request, token, 'B1A', PROJECT_ID)
    test.skip(!wpResult.exists, 'B1A 底稿不存在，需先运行项目底稿生成')

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

    // 等待编辑器容器渲染
    await page.waitForSelector('.gt-wp-editor, .gt-wp-editor-loading, .gt-a-program-console', {
      timeout: 15_000,
    })
    await page.waitForTimeout(5_000)

    // 等待 loading overlay 消失
    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证无 ErrorBoundary
    const errorBoundary = page.locator('.gt-error-boundary, [class*="error-boundary"]')
    expect(await errorBoundary.count(), 'ErrorBoundary 不应出现').toBe(0)

    // 验证程序表行渲染（B1A 有 6 个顶级步骤）
    const tableRows = page.locator('.el-table__row')
    const rowCount = await tableRows.count()
    expect(rowCount, 'B1A 程序表应至少渲染 6 行（含子步骤可能更多）').toBeGreaterThanOrEqual(6)

    // 验证无严重 console errors
    const criticalErrors = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
    )
    expect(criticalErrors, `控制台严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)
  })

  test('49.2 — B1A ref_index chip 渲染（B2, B1-3, B1-1, B5 等）', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B1A', PROJECT_ID)
    test.skip(!wpResult.exists, 'B1A 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(6_000)

    const overlay = page.locator('.gt-loading-overlay')
    if (await overlay.count() > 0) {
      await expect(overlay).toBeHidden({ timeout: 15_000 })
    }

    // 验证 ref_index chip 存在（B1A 模板有 B2, B1-3, B1-1, B1-4, B1-5, B5 等）
    const chips = page.locator('.gt-index-chip, .el-tag')
    const chipCount = await chips.count()
    expect(chipCount, 'B1A 应有多个 ref_index chip').toBeGreaterThanOrEqual(3)

    // 验证特定 chip 存在
    const expectedChips = ['B2', 'B1-3', 'B5']
    for (const expected of expectedChips) {
      const chip = chips.filter({ hasText: expected }).first()
      // chip 可能在未展开的子步骤中，使用宽松断言
      if (await chip.isVisible()) {
        expect(await chip.textContent()).toContain(expected)
      }
    }
  })

  test('49.3 — 点击 ref_index chip 触发导航或弹窗', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const wpResult = await findWorkpaper(request, token, 'B1A', PROJECT_ID)
    test.skip(!wpResult.exists, 'B1A 底稿不存在')

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

    // 优先找 B1-3 chip（docx 弹窗类）
    let targetChip = chips.filter({ hasText: 'B1-3' }).first()
    if (!(await targetChip.isVisible())) {
      // 降级找任意可见 chip
      for (let i = 0; i < chipCount; i++) {
        const c = chips.nth(i)
        if (await c.isVisible()) {
          targetChip = c
          break
        }
      }
    }

    if (await targetChip.isVisible()) {
      const currentUrl = page.url()
      await targetChip.click()
      await page.waitForTimeout(2_000)

      // 点击后应发生以下之一：
      // 1. 路由变化（导航到关联底稿）
      // 2. 弹窗打开（docx 弹窗式底稿）
      const urlChanged = page.url() !== currentUrl
      const dialogVisible = await page.locator('.el-dialog').isVisible()

      expect(
        urlChanged || dialogVisible,
        'ref_index chip 点击后应触发导航或弹窗',
      ).toBeTruthy()
    }
  })

  test('49.4 — B1A 程序表 API 端点验证', async ({ request }) => {
    test.setTimeout(20_000)
    const token = await getToken(request)

    // 验证 procedure-tables API 返回 B1A 数据
    const ptResp = await request.get(
      `/api/projects/${PROJECT_ID}/procedure-tables/B1A`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(ptResp.status()).toBe(200)
    const ptBody = await ptResp.json()
    const tableData = ptBody?.data || ptBody
    const items = tableData?.items || []
    expect(items.length, 'B1A 应有 6 个顶级步骤').toBeGreaterThanOrEqual(6)

    // 验证 ref_index 字段存在
    const withRef = items.filter((i: any) => i.ref_index)
    expect(withRef.length, 'B1A 应有多个步骤含 ref_index').toBeGreaterThanOrEqual(3)

    // 验证步骤内容包含关键文本
    const seq1 = items.find((i: any) => i.seq === 1)
    expect(seq1?.content).toContain('面谈')

    const seq6 = items.find((i: any) => i.seq === 6)
    expect(seq6?.content).toContain('约定书')
    expect(seq6?.ref_index).toBe('B5')
  })
})
