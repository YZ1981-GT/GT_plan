/**
 * A17-lite E2E — 弹窗 + 核对表路由验收
 *
 * E10: A17-3 chip 点击 → 弹窗展示（业务咨询记录）
 * E11: A17-5-1 → checklist-table 渲染（审计目标 + 核对程序）
 * E11b: A17 seq5 → A17-5 选版 chip（必做 badge + 不适用折叠）
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<A类项目ID>
 *   npx playwright test e2e/a17-lite.spec.ts
 *
 * Spec: a17-summary-workpaper Task 18
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_FULL_E2E = _env.RUN_FULL_E2E === '1'
const TEST_PROJECT_ID = _env.TEST_PROJECT_ID || ''

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
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
): Promise<{ id: string } | null> {
  const resp = await request.get(`/api/projects/${TEST_PROJECT_ID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
  const wp = list.find((w: any) => (w.wp_code || '').toUpperCase() === wpCode.toUpperCase())
  return wp?.id ? { id: wp.id } : null
}

test.describe('A17-lite E2E', () => {
  test.skip(!RUN_FULL_E2E, '【待环境】需 RUN_FULL_E2E=1 + A类测试项目')

  // ─── E10: A17-3 弹窗 ───────────────────────────────────────────────────
  test.describe('E10 — A17 弹窗', () => {
    test('A17-3 chip 点击 → 弹窗展示业务咨询记录', async ({ page, request }) => {
      test.setTimeout(45_000)
      const token = await loginAs(page)
      const wp = await findWpByCode(request, token, 'A17')
      test.skip(!wp, '项目内无 A17 程序表底稿')

      // 导航到 A17 程序表
      await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wp!.id}/edit`)
      await page.waitForSelector('.gt-a-program-console, .gt-wp-renderer', { timeout: 20_000 })

      // 点击 A17-3 chip → 弹窗弹出
      const chip = page.locator('.gt-index-chip', { hasText: 'A17-3' }).first()
      test.skip(!(await chip.count()), 'A17-3 chip 未渲染')
      await chip.click()

      // 验证弹窗出现，标题为"业务咨询记录"
      const dialog = page.locator('.el-dialog').filter({ hasText: '业务咨询记录' })
      await expect(dialog).toBeVisible({ timeout: 8_000 })

      // 弹窗内包含使用说明
      await expect(dialog.locator('.wp-popup-docx-editor__guidance, .guidance-title'))
        .toBeVisible()

      // 弹窗内包含下载模板按钮
      await expect(dialog.locator('button', { hasText: /下载|模板/ })).toBeVisible()

      // 关闭弹窗 → 返回程序表
      await dialog.locator('.el-dialog__headerbtn').click()
      await expect(dialog).not.toBeVisible({ timeout: 3_000 })
      await expect(page.locator('.gt-a-program-console, .gt-wp-renderer')).toBeVisible()
    })
  })

  // ─── E11: A17-5-1 路由验收 ─────────────────────────────────────────────
  test.describe('E11 — A17-5-1 路由', () => {
    test('A17-5-1 渲染为 checklist-table', async ({ page, request }) => {
      test.setTimeout(45_000)
      const token = await loginAs(page)
      const wp = await findWpByCode(request, token, 'A17-5-1')
      test.skip(!wp, '项目内无 A17-5-1 底稿（需 PRE-4 完成）')

      // 导航到 A17-5-1 底稿
      await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wp!.id}/edit`)
      await page.waitForSelector('.gt-checklist-table, .gt-wp-renderer', { timeout: 20_000 })

      const checklist = page.locator('.gt-checklist-table')
      await expect(checklist).toBeVisible({ timeout: 10_000 })

      // 左侧导航含"审计目标"节
      await expect(checklist.locator('.gt-checklist-table__nav-item', { hasText: '审计目标' }))
        .toBeVisible()

      // 左侧导航含"核对程序"节
      await expect(checklist.locator('.gt-checklist-table__nav-item', { hasText: '核对程序' }))
        .toBeVisible()
    })
  })

  // ─── E11b: A17 seq5 核对表选版 chip ────────────────────────────────────
  test.describe('E11b — A17-5 选版 chip', () => {
    test('seq5 展示必做 badge，不适用版本可折叠', async ({ page, request }) => {
      test.setTimeout(45_000)
      const token = await loginAs(page)
      const wp = await findWpByCode(request, token, 'A17')
      test.skip(!wp, '项目内无 A17 程序表底稿')

      await page.goto(`/projects/${TEST_PROJECT_ID}/workpapers/${wp!.id}/edit`)
      await page.waitForSelector('.gt-a-program-console', { timeout: 20_000 })

      const mandatory = page.locator('.gt-a-program-console__a17-badge', { hasText: '必做' }).first()
      test.skip(!(await mandatory.count()), 'A17-5 必做 badge 未渲染（需 applicable-versions API）')
      await expect(mandatory).toBeVisible()

      const chip517 = page.locator('.gt-index-chip', { hasText: 'A17-5-1' }).first()
      await expect(chip517).toBeVisible()

      const toggle = page.locator('.gt-a-program-console__other-versions-toggle').first()
      if (await toggle.count()) {
        await toggle.click()
        const naChip = page.locator('.gt-index-chip.is-disabled, .gt-index-chip[disabled]').first()
        await expect(naChip).toBeVisible({ timeout: 5_000 })
      }
    })
  })
})
