/** A17-core E2E — E12: ch01 编辑 + Word 导出验证 (Spec: a17-summary-workpaper Task 19) */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN = _env.RUN_FULL_E2E === '1', PID = _env.TEST_PROJECT_ID || ''

async function login(page: Page) {
  const r = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
  const b = await r.json(); const token = (b.data?.access_token ?? b.access_token) as string
  await page.addInitScript((t: string) => { sessionStorage.setItem('token', t); localStorage.setItem('token', t) }, token)
  return token
}

async function findWp(req: APIRequestContext, token: string, code: string) {
  const r = await req.get(`/api/projects/${PID}/working-papers`, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok()) return null
  const b = await r.json()
  const list = b?.data?.items || b?.items || b?.data || (Array.isArray(b) ? b : [])
  return list.find((w: any) => (w.wp_code || '').toUpperCase() === code)?.id as string | undefined
}

test.describe('A17-core E2E', () => {
  test.skip(!RUN, '【待环境】需 RUN_FULL_E2E=1 + A类测试项目')

  test('E12 — ch01 编辑 → export Word → 无蓝【】/XX', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await login(page)
    const wpId = await findWp(request, token, 'A17-1')
    test.skip(!wpId, '项目内无 A17-1 底稿')

    await page.goto(`/projects/${PID}/workpapers/${wpId}/edit`)
    await page.waitForSelector('.gt-a17-summary, .gt-wp-renderer', { timeout: 20_000 })

    // 左侧目录 ≥ 16 章
    const nav = page.locator('.gt-a17-summary__nav-item, .gt-a17-summary .chapter-nav-item')
    await expect(nav.first()).toBeVisible({ timeout: 10_000 })
    expect(await nav.count()).toBeGreaterThanOrEqual(16)

    // 点击第 1 章 → 编辑 → 自动保存
    await nav.first().click()
    const ta = page.locator('.gt-a17-summary textarea').first()
    await expect(ta).toBeVisible({ timeout: 5_000 })
    await ta.fill(`E12测试_${Date.now()}`)
    await expect(page.locator('text=已保存')).toBeVisible({ timeout: 10_000 })

    // 导出 Word — 验证 PK magic bytes (docx = zip)
    const hdr = { Authorization: `Bearer ${token}` }
    const exp = await request.get(`/api/a17/export-word?project_id=${PID}&wp_id=${wpId}`, { headers: hdr })
    expect(exp.ok()).toBeTruthy()
    const buf = await exp.body()
    expect(buf.length).toBeGreaterThan(100)
    expect(buf[0]).toBe(0x50) // P
    expect(buf[1]).toBe(0x4b) // K

    // 完整性检查：无蓝色注释/XX 占位符
    const chk = await request.get(`/api/a17/check-completeness?project_id=${PID}&wp_id=${wpId}`, { headers: hdr })
    if (chk.ok()) {
      const d = ((await chk.json()) as any)?.data ?? (await chk.json())
      expect(d.has_blue_markers ?? d.hasBlueMarkers ?? false).toBe(false)
      expect(d.has_xx_placeholders ?? d.hasXxPlaceholders ?? false).toBe(false)
    }
  })
})
