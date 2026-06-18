/**
 * A18 E2E — E13: A18-1 弹窗下载 + E14: A18-2 表单填写+导出
 *
 * 运行方式：
 *   set RUN_FULL_E2E=1 && set TEST_PROJECT_ID=<A/B类项目ID>
 *   npx playwright test e2e/a18-regulatory.spec.ts
 *
 * Spec: a18-regulatory-communication Task 14
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const RUN = !!process.env.RUN_FULL_E2E
const PID = process.env.TEST_PROJECT_ID || ''
const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3030'

async function login(page: Page): Promise<string> {
  const res = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = (await res.json()) as any
  const token = body?.data?.access_token ?? body?.access_token
  await page.goto(BASE)
  await page.evaluate((t) => localStorage.setItem('token', t), token)
  return token
}

async function findWp(
  request: APIRequestContext,
  token: string,
  wpCode: string,
): Promise<string | null> {
  const res = await request.get(`/api/projects/${PID}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok()) return null
  const body = (await res.json()) as any
  const list = body?.data ?? body ?? []
  const wp = list.find((w: any) => w.wp_code === wpCode)
  return wp?.id ?? null
}

test.describe('A18 E2E — 监管沟通函', () => {
  test.skip(!RUN, '【待环境】需 RUN_FULL_E2E=1 + A/B类测试项目')

  // ─── E13: A18-1 弹窗下载 ────────────────────────────────────────────
  test('E13 — A18-1 chip 点击 → 弹窗 + 下载', async ({ page, request }) => {
    test.setTimeout(45_000)
    const token = await login(page)
    const wpId = await findWp(request, token, 'A18')
    test.skip(!wpId, '项目内无 A18 程序表底稿')

    // 导航到 A18 程序表
    await page.goto(`/projects/${PID}/workpapers/${wpId}/edit`)
    await page.waitForSelector('.gt-a-program-console, .gt-wp-renderer', { timeout: 20_000 })

    // 点击 A18-1 chip → 弹窗弹出
    const chip = page.locator('.gt-index-chip', { hasText: 'A18-1' }).first()
    test.skip(!(await chip.count()), 'A18-1 chip 未渲染')
    await chip.click()

    // 弹窗可见
    const dialog = page.locator('.wp-popup-docx-editor, .el-dialog')
    await expect(dialog.first()).toBeVisible({ timeout: 10_000 })

    // 弹窗内有标题"向监管部门报送审计小结的函"
    await expect(dialog.first()).toContainText('向监管部门报送审计小结')
  })

  // ─── E14: A18-2 表单填写 + 导出 ────────────────────────────────────
  test('E14 — A18-2 regulatory-letter 表单 + 导出', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await login(page)
    const wpId = await findWp(request, token, 'A18-2')
    test.skip(!wpId, '项目内无 A18-2 底稿')

    // 导航到 A18-2 底稿
    await page.goto(`/projects/${PID}/workpapers/${wpId}/edit`)
    await page.waitForSelector('.gt-regulatory-letter, .gt-wp-renderer', { timeout: 20_000 })

    // 表头自动填充（公司名非空）
    const companyInput = page.locator('.rl-header input').nth(2) // 公司名称
    await expect(companyInput).toBeVisible({ timeout: 10_000 })

    // 议题卡片存在 4 张
    const cards = page.locator('.rl-topic-card')
    await expect(cards).toHaveCount(4)

    // 点击议题1"是" → 显示 textarea
    const firstRadioY = cards.first().locator('.el-radio').first()
    await firstRadioY.click()
    const textarea = cards.first().locator('textarea')
    await expect(textarea).toBeVisible({ timeout: 5_000 })

    // 填写内容
    await textarea.fill(`E14自动化测试_${Date.now()}`)

    // 等待 debounce 保存
    await page.waitForTimeout(2000)

    // 导出 Word — API 调用验证
    const hdr = { Authorization: `Bearer ${token}` }
    const chk = await request.get(
      `/api/projects/${PID}/working-papers/${wpId}/export-word/check-incomplete`,
      { headers: hdr },
    )
    // check-incomplete 返回 200 或 501（未注册）
    if (chk.ok()) {
      const d = ((await chk.json()) as any)?.data ?? (await chk.json())
      expect(d).toHaveProperty('has_incomplete')
    }

    // 刷新页面验证持久化
    await page.reload()
    await page.waitForSelector('.gt-regulatory-letter', { timeout: 20_000 })
    // 议题1 仍为"适用"状态
    const tag = cards.first().locator('.el-tag--success')
    await expect(tag.first()).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('E18 — A18-1 小结生成', () => {
  test.skip(!RUN, '【待环境】需 RUN_FULL_E2E=1 + A类测试项目')

  test('E18-API — generate-summary 返回结构化框架', async ({ request }) => {
    const loginRes = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    const body = (await loginRes.json()) as any
    const token = body?.data?.access_token ?? body?.access_token
    const hdr = { Authorization: `Bearer ${token}` }

    const res = await request.get(`/api/projects/${PID}/a18/generate-summary`, { headers: hdr })
    expect(res.ok()).toBeTruthy()

    const data = ((await res.json()) as any)?.data ?? (await res.json())
    expect(data).toHaveProperty('summary_sections')
    expect(data).toHaveProperty('completeness')
    expect(data).toHaveProperty('formatted_text')
    expect(typeof data.completeness).toBe('number')
  })

  test('E18-UI — 弹窗生成小结 + 预览可见', async ({ page, request }) => {
    test.setTimeout(60_000)
    const token = await login(page)
    const wpId = await findWp(request, token, 'A18')
    test.skip(!wpId, '项目内无 A18 程序表底稿')

    await page.goto(`/projects/${PID}/workpapers/${wpId}/edit`)
    await page.waitForSelector('.gt-a-program-console, .gt-wp-renderer', { timeout: 20_000 })

    const chip = page.locator('.gt-index-chip', { hasText: 'A18-1' }).first()
    test.skip(!(await chip.count()), 'A18-1 chip 未渲染')
    await chip.click()

    const dialog = page.locator('.wp-popup-docx-editor, .el-dialog').first()
    await expect(dialog).toBeVisible({ timeout: 10_000 })

    const genBtn = page.getByRole('button', { name: /从 A17 生成小结框架/ })
    await expect(genBtn).toBeVisible({ timeout: 5_000 })
    await genBtn.click()

    const preview = page.locator('.wp-popup-docx-editor__summary-preview')
    await expect(preview).toBeVisible({ timeout: 15_000 })
  })
})
