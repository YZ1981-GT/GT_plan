/**
 * UAT — 坏账准备明细表 D2-3 Playwright 实测（重构版 D2TabBadDebt）
 *
 * 验证：
 * 1. D2 底稿 → 切换到「坏账准备明细表D2-3」→ 渲染 D2TabBadDebt
 * 2. 三分类区块 + 添加子行
 * 3. 合计行展示
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { TEST_PROJECT_ID } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const D2_3_SHEET_PATTERN = /坏账准备明细表D2-3|D2-3/

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
  return token as string
}

async function findD2WpId(request: APIRequestContext, token: string): Promise<string | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const d2 = list.find((w: { wp_code?: string }) => (w.wp_code || '').toUpperCase() === 'D2')
  return d2?.id || null
}

async function waitEditorReady(page: Page) {
  await page.waitForSelector('.gt-wp-editor, .gt-wp-editor-loading', { timeout: 15_000 })
  await page.waitForTimeout(3_000)
  const overlay = page.locator('.gt-loading-overlay')
  if (await overlay.count() > 0) {
    await expect(overlay).toBeHidden({ timeout: 20_000 })
  }
}

async function openD2_3Sheet(page: Page) {
  const tab = page.getByRole('tab', { name: D2_3_SHEET_PATTERN })
  await expect(tab, '顶部 tab 应存在 D2-3 sheet').toBeVisible({ timeout: 10_000 })
  await tab.click()
  await page.waitForTimeout(1_500)
}

test.describe('坏账准备明细表 D2-3（D2TabBadDebt 重构版）', () => {
  test('11.3 — 三分类渲染 + 添加子行 + 合计', async ({ page, request }) => {
    test.setTimeout(120_000)

    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (/\/ai\//.test(text) && /405/.test(text)) return
        if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

    const token = await loginAs(page, 'admin', 'admin123')
    const wpId = await findD2WpId(request, token)
    test.skip(!wpId, '测试项目无 D2 底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await waitEditorReady(page)
    await openD2_3Sheet(page)

    const badDebt = page.locator('.d2-tab-bad-debt')
    await expect(badDebt, '应渲染 D2TabBadDebt 组件').toBeVisible({ timeout: 10_000 })

    // 三分类区块标题
    await expect(badDebt.getByText('按单项计提')).toBeVisible()
    await expect(badDebt.getByText('按账龄组合计提')).toBeVisible()

    // 添加子行
    const addBtn = badDebt.getByRole('button', { name: '+ 添加子行' }).first()
    await addBtn.click()
    await page.waitForTimeout(500)

    const labelInput = badDebt.locator('.el-input input').first()
    if (await labelInput.isVisible()) {
      await labelInput.fill('E2E测试债务人')
      await labelInput.press('Tab')
    }

    // 合计行
    await expect(badDebt.getByText(/合计|小计/).first()).toBeVisible()

    const critical = consoleErrors.filter((e) =>
      /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
    )
    expect(critical, `控制台严重错误:\n${critical.join('\n')}`).toHaveLength(0)
  })
})
