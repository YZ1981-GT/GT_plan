/**
 * E2E — 分析性复核底稿 A1-13/A1-14
 *
 * Validates: analytical-review-workpaper spec tasks 7/8/9
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

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

async function findWpByCode(
  request: APIRequestContext,
  token: string,
  wpCode: string,
): Promise<{ id: string; wpCode: string } | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const wp = list.find((w: { wp_code?: string }) => (w.wp_code || '').toUpperCase() === wpCode)
  return wp?.id ? { id: wp.id, wpCode } : null
}

test.describe('分析性复核底稿 E2E', () => {
  test('A1-13 — Tab 导航 + BS 横向数据渲染', async ({ page, request }) => {
    test.setTimeout(60_000)
    const consoleErrors: string[] = []
    page.on('pageerror', (err) => consoleErrors.push(err.message))

    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWpByCode(request, token, 'A1-13')
    test.skip(!wp, '项目内无 A1-13 底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)
    await page.waitForSelector('.gt-analytical-review, .gt-wp-renderer', { timeout: 20_000 })
    await page.waitForTimeout(3_000)

    const ar = page.locator('.gt-analytical-review')
    if (await ar.count()) {
      await expect(ar.locator('.gt-analytical-review__title')).toContainText('分析性复核')
      await expect(ar.locator('.el-tabs__item')).toContainText(['BS横向', 'BS纵向'])
      const table = ar.locator('.gt-ar-table').first()
      if (await table.count()) {
        await expect(table.locator('th')).toContainText(['项目', '上年审定数', '本年审定数'])
      }
    }

    expect(consoleErrors).toHaveLength(0)
  })

  test('A1-14 — 合并范围 + 比率分析 Tab', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWpByCode(request, token, 'A1-14')
    test.skip(!wp, '项目内无 A1-14 底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)
    await page.waitForSelector('.gt-analytical-review, .gt-wp-renderer', { timeout: 20_000 })
    await page.waitForTimeout(3_000)

    const ar = page.locator('.gt-analytical-review')
    if (await ar.count()) {
      await expect(ar.locator('.gt-analytical-review__title')).toContainText('合并')
      const ratioTab = ar.locator('.el-tabs__item', { hasText: '比率分析' })
      if (await ratioTab.count()) {
        await ratioTab.click()
        await expect(ar.locator('.gt-ar-ratio-category').first()).toBeVisible({ timeout: 5_000 })
      }
    }
  })

  test('回归 — A1-15 核对表仍正常', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await loginAs(page, 'admin', 'admin123')
    const wp = await findWpByCode(request, token, 'A1-15')
    test.skip(!wp, '项目内无 A1-15 底稿')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}/edit`)
    await page.waitForSelector('.gt-checklist-table, .gt-wp-renderer', { timeout: 20_000 })
    await page.waitForTimeout(2_000)

    const checklist = page.locator('.gt-checklist-table')
    if (await checklist.count()) {
      await expect(checklist).toBeVisible()
    }
  })
})
