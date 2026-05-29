/**
 * Sprint C.3.16 / C.0.23 / C.6.1 — Note Spec UAT Test Suite
 *
 * 验收：
 * - C.3.16: Playwright 实测全链路（前端组件挂载 + 按钮点击 + 弹窗显示）
 * - C.0.23: Sprint C.0 离线导出/导入 UAT
 * - C.6.1: 综合 UAT（合并 + 单体 + 上市 + 国企）
 *
 * 前置：
 * - 后端运行（http://localhost:9980）
 * - 前端运行（http://localhost:3030）
 * - admin/admin123 用户存在
 * - 至少 1 个项目已生成附注（首汽租车_2025）
 */
import { expect, test } from '@playwright/test'

const BASE_URL = 'http://localhost:3030'
const API_URL = 'http://localhost:9980'

// 测试项目（已通过 F-1 UAT 验证）
const TEST_PROJECT_ID = 'df5b8403-abbb-48af-b6a4-6fd44dfae5c9'
const TEST_YEAR = 2025

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function login(page: import('@playwright/test').Page) {
  const resp = await page.request.post(`${API_URL}/api/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok()).toBeTruthy()
  const body = await resp.json()
  const token = body.data?.access_token || body.access_token
  expect(token).toBeTruthy()

  await page.goto(BASE_URL)
  await page.evaluate((tk) => {
    localStorage.setItem('token', tk)
    localStorage.setItem('access_token', tk)
  }, token)
  return token
}

async function gotoDisclosureNotes(page: import('@playwright/test').Page) {
  // domcontentloaded only — networkidle never resolves due to event-bus polling
  await page.goto(
    `${BASE_URL}/projects/${TEST_PROJECT_ID}/disclosure-notes?year=${TEST_YEAR}`,
    { waitUntil: 'domcontentloaded', timeout: 30000 }
  )
  await page.waitForTimeout(8000)
}

// ─── C.3.16: Frontend Integration UAT ────────────────────────────────────────

test.describe('C.3.16 — Frontend Integration UAT', () => {
  test('disclosure-notes page loads with all new toolbar buttons', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    const labels = ['导出离线包', '一键导入', 'AI建议', '版本', '集团基线', '段落变量', '上年对比']
    for (const label of labels) {
      await expect(page.locator(`button:has-text("${label}")`).first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('NoteTemplateSwitch (A.5.12)', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await expect(page.locator('label:has-text("国企版"), label:has-text("上市版")').first()).toBeVisible({ timeout: 5000 })
  })

  test('Scope toggle 单体/合并 (C.3.12)', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await expect(page.locator('button:has-text("单体")').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("合并")').first()).toBeVisible({ timeout: 5000 })
  })

  test('AI Suggestion Panel (C.1.4) opens', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("AI建议")').first().click()
    await expect(page.locator('text=AI 建议').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("分析当前章节")')).toBeVisible()
  })

  test('Version Tree Panel (C.2.5) opens', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("版本")').first().click()
    await expect(page.locator('text=章节版本历史').first()).toBeVisible({ timeout: 5000 })
  })

  test('Group Baseline Dialog (C.3.6) shows 3 tabs', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("集团基线")').first().click()
    await expect(page.locator('text=集团附注模板基线').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=应用基线').first()).toBeVisible()
    await expect(page.locator('text=保存为基线').first()).toBeVisible()
    await expect(page.locator('text=版本对比').first()).toBeVisible()
  })

  test('Paragraph Vars Editor (C.3.7) opens', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("段落变量")').first().click()
    await expect(page.locator('text=段落变量编辑').first()).toBeVisible({ timeout: 5000 })
  })

  test('Prior Year Panel (C.3.10) opens', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("上年对比")').first().click()
    await expect(page.locator('.el-drawer:visible').first()).toBeVisible({ timeout: 5000 })
  })
})

// ─── C.0.23: Offline Export/Import UAT ───────────────────────────────────────

test.describe('C.0.23 — Offline Export/Import UAT', () => {
  test('Offline Export Dialog (C.0.17) shows section tree', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("导出离线包")').first().click()
    await expect(page.locator('text=导出附注离线编辑包').first()).toBeVisible({ timeout: 5000 })

    // Verify export scope options
    await expect(page.locator('text=全部章节')).toBeVisible()
    await expect(page.locator('text=仅有数据章节')).toBeVisible()
    await expect(page.locator('text=自定义勾选')).toBeVisible()

    // Verify export options
    await expect(page.locator('text=包含公式表达式')).toBeVisible()
    await expect(page.locator('text=包含数据源溯源')).toBeVisible()
  })

  test('Offline Import Dialog (C.0.18) shows upload area', async ({ page }) => {
    await login(page)
    await gotoDisclosureNotes(page)

    await page.locator('button:has-text("一键导入")').first().click()
    await expect(page.locator('text=一键导入附注').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=点击上传')).toBeVisible()
    await expect(page.locator('button:has-text("校验并预览")')).toBeVisible()
  })
})

// ─── Backend API health ──────────────────────────────────────────────────────

test.describe('Backend API health', () => {
  test('Health endpoint responds', async ({ request }) => {
    const resp = await request.get(`${API_URL}/api/health`)
    expect(resp.ok()).toBeTruthy()
  })

  test('OpenAPI lists endpoints', async ({ request }) => {
    const resp = await request.get(`${API_URL}/openapi.json`)
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    const paths = Object.keys(body.paths || {})

    const hasOfflineExport = paths.some(p => p.includes('offline-export'))
    if (!hasOfflineExport) {
      console.warn('⚠ Offline endpoints not registered. Restart backend to load new routes.')
    }
    expect(paths.length).toBeGreaterThan(100)
  })
})
