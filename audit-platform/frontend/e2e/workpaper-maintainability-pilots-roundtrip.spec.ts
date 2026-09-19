/**
 * Task 4.4 — D2/K5/J2 fresh-navigation Round_Trip evidence.
 *
 * Validates: Requirements 3.9, 8.1, 8.2, 8.3, 8.4
 */
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const backendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../backend')

interface Pilot {
  code: 'D2' | 'K5' | 'J2'
  wpId: string
  sheetCode: string
  root: string
  field: string
  itemId: string
}

const PILOTS: Pilot[] = [
  {
    code: 'D2', wpId: 'e2c95d10-181d-4549-8910-d5ab5bc5edd1', sheetCode: 'D2-7',
    root: '.d2-voucher-check', field: '.section-conclusion textarea', itemId: 'D2-vc-conclusion',
  },
  {
    code: 'K5', wpId: '26acda99-1409-42de-883a-47adc9769c1a', sheetCode: 'K5-1',
    root: '.k5-tab-adjudication', field: 'textarea[placeholder^="请填写审计说明"]',
    itemId: 'K5-1-audit-conclusion',
  },
  {
    code: 'J2', wpId: 'eb3cbf2d-394c-43e8-9296-a93ff41339ea', sheetCode: 'J2-3',
    root: '.j2-tab-adjustment', field: 'textarea[placeholder^="请输入审计说明"]', itemId: 'J2-3-note',
  },
]

async function login(page: Page): Promise<string> {
  let response
  for (let attempt = 0; attempt < 3; attempt += 1) {
    response = await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (response.ok()) break
    await new Promise(resolve => setTimeout(resolve, 1_000))
  }
  expect(response?.ok(), `登录 API 应成功，status=${response?.status()}`).toBeTruthy()
  const body = await response!.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  return token
}
async function apiItem(request: APIRequestContext, token: string, pilot: Pilot): Promise<any | undefined> {
  const response = await request.get(`/api/workpapers/${pilot.wpId}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok(), `${pilot.code} checklist GET 应成功`).toBeTruthy()
  const body = await response.json()
  const data = body?.data ?? body
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.find((item: any) => item.item_id === pilot.itemId)
}

function dbItem(pilot: Pilot): any | null {
  const output = execFileSync(
    'python',
    ['scripts/e2e/read_checklist_response.py', pilot.wpId, pilot.itemId],
    { cwd: backendRoot, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } },
  )
  const line = output.split(/\r?\n/).find(value => value.startsWith('CHECKLIST_DB_RESULT='))
  if (!line) throw new Error(`未找到 DB 回读结果：${output}`)
  return JSON.parse(line.slice('CHECKLIST_DB_RESULT='.length))
}

function sheetTab(page: Page, text: string | RegExp) {
  return page
    .locator('.gt-wp-renderer__sheet-tabs-inner .el-tabs__item[role="tab"]')
    .filter({ hasText: text })
}

async function activateSheet(page: Page, pilot: Pilot): Promise<void> {
  const escaped = pilot.sheetCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const tab = sheetTab(page, new RegExp(`${escaped}(?!\\d)`))
  await expect(tab, `${pilot.code} 顶部 sheet tab 应唯一`).toHaveCount(1)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await expect(tab, `${pilot.code} 目标 sheet tab 应真正激活`).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator(pilot.root)).toBeVisible({ timeout: 30_000 })
}

async function openPilot(page: Page, pilot: Pilot, nonce: string): Promise<void> {
  await page.goto(
    `/projects/${PROJECT_ID}/workpapers/${pilot.wpId}/edit?roundTrip=${encodeURIComponent(nonce)}`,
    { waitUntil: 'domcontentloaded' },
  )
  await expect(page.locator('.gt-wp-renderer')).toBeVisible({ timeout: 30_000 })
  const overlay = page.locator('.gt-loading-overlay')
  if (await overlay.count()) await expect(overlay).toBeHidden({ timeout: 30_000 })

  if (pilot.code === 'J2') {
    const directoryTab = sheetTab(page, /底稿目录/)
    await directoryTab.click()
    await expect(page.locator('.j2-tab-index')).toBeVisible({ timeout: 30_000 })
    const adjustmentCard = page.locator('.j2-tab-index .gt-b-arch__card')
      .filter({ hasText: '调整分录汇总表J2-3' })
    await expect(adjustmentCard, 'J2 目录应有精确 J2-3 卡片').toHaveCount(1)
    await adjustmentCard.click()
  }
  await activateSheet(page, pilot)
}

function targetPut(page: Page, pilot: Pilot, timeout = 30_000) {
  return page.waitForResponse((response) => {
    if (response.request().method() !== 'PUT') return false
    if (!response.url().includes(`/api/workpapers/${pilot.wpId}/checklist-responses`)) return false
    try {
      return response.request().postDataJSON()?.items?.some(
        (item: any) => item.item_id === pilot.itemId,
      ) ?? false
    } catch { return false }
  }, { timeout })
}

async function assertVersionHistory(page: Page, pilot: Pilot): Promise<void> {
  const button = page.getByRole('button', { name: '版本历史', exact: true }).first()
  await expect(button, `${pilot.code} 版本入口应可见`).toBeVisible()
  await button.click()
  const drawer = page.locator('.version-trail-drawer')
  await expect(drawer, `${pilot.code} 真实版本抽屉应打开`).toBeVisible({ timeout: 20_000 })
  await expect(drawer.getByText('版本历史', { exact: true })).toBeVisible()
  await drawer.locator('.el-drawer__close-btn').click()
  await expect(drawer).toBeHidden()
}

async function assertReviewDialog(page: Page, pilot: Pilot): Promise<void> {
  if (pilot.code === 'D2') {
    await page.getByRole('button', { name: '底稿复核', exact: true }).click()
  } else if (pilot.code === 'K5') {
    const reviewTab = sheetTab(page, /K5-3(?!\d)/)
    await reviewTab.click()
    const adjustment = page.locator('.k5-tab-adjustment')
    await expect(adjustment).toBeVisible({ timeout: 30_000 })
    await adjustment.getByRole('button', { name: /复核/ }).click()
  } else {
    return
  }
  const drawer = page.locator('.review-dialog-drawer')
  await expect(drawer, `${pilot.code} 真实复核抽屉应打开`).toBeVisible({ timeout: 20_000 })
  await expect(drawer.locator('.header-title')).toContainText(/复核|对话/)
  await drawer.locator('.header-actions button').last().click()
  await expect(drawer).toBeHidden()
  if (pilot.code === 'K5') await activateSheet(page, pilot)
}

async function assertJ2Ai(page: Page, pilot: Pilot): Promise<void> {
  const button = page.locator(pilot.root).getByRole('button', { name: '🤖 AI辅助', exact: true }).first()
  await expect(button, 'J2 AI 辅助入口应可用').toBeEnabled()
  const aiResponsePromise = page.waitForResponse(response =>
    response.request().method() === 'POST'
      && response.url().includes(`/api/workpapers/${pilot.wpId}/ai/generate-text`),
  { timeout: 90_000 })
  const savePromise = targetPut(page, pilot, 90_000)
  await button.click()
  const aiResponse = await aiResponsePromise
  expect(aiResponse.ok(), 'J2 AI 请求应成功').toBeTruthy()
  const body = aiResponse.request().postDataJSON()
  expect(Object.values(body?.context ?? {}).every(value => typeof value === 'string'),
    'J2 AI context 值必须全部为字符串').toBeTruthy()
  expect((await savePromise).ok(), 'J2 AI 生成内容应进入统一持久化链').toBeTruthy()
}

test.describe('Task 4.4 — D2/K5/J2 pilot Round_Trip', () => {
  test.describe.configure({ mode: 'serial' })

  for (const pilot of PILOTS) {
    test(`${pilot.code}: fresh navigation → PUT → GET/DB → fresh navigation UI`, async ({ page }) => {
      test.setTimeout(240_000)
      const consoleErrors: string[] = []
      const counts = { renderConfigGet: 0, checklistGet: 0, checklistPut: 0, aiPost: 0 }
      page.on('console', message => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })
      page.on('pageerror', error => consoleErrors.push(`pageerror: ${error.message}`))
      page.on('request', request => {
        const url = request.url()
        if (request.method() === 'GET' && url.includes('render-config')) counts.renderConfigGet += 1
        if (request.method() === 'GET' && url.includes('/checklist-responses')) counts.checklistGet += 1
        if (request.method() === 'PUT' && url.includes('/checklist-responses')) counts.checklistPut += 1
        if (request.method() === 'POST' && url.includes('/ai/generate-text')) counts.aiPost += 1
      })

      const token = await login(page)
      const original = await apiItem(page.request, token, pilot)
      const originalRemark = original?.remark ?? ''
      const marker = `RT-${pilot.code}-${Date.now()}`

      await openPilot(page, pilot, `write-${marker}`)
      await assertVersionHistory(page, pilot)
      await assertReviewDialog(page, pilot)
      if (pilot.code === 'J2') await assertJ2Ai(page, pilot)

      const field = page.locator(pilot.root).locator(pilot.field).first()
      await expect(field).toBeEditable()
      const putPromise = targetPut(page, pilot)
      await field.fill(marker)
      await field.blur()
      const putResponse = await putPromise
      expect(putResponse.ok(), `${pilot.code} PUT 应成功`).toBeTruthy()
      const sent = putResponse.request().postDataJSON().items.find((item: any) => item.item_id === pilot.itemId)
      expect(sent.remark).toBe(marker)

      const savedByApi = await apiItem(page.request, token, pilot)
      expect(savedByApi?.remark, `${pilot.code} GET 应回读 marker`).toBe(marker)
      const savedByDb = dbItem(pilot)
      expect(savedByDb?.remark, `${pilot.code} DB 应回读 marker`).toBe(marker)
      await openPilot(page, pilot, `read-${marker}`)
      const reloadedField = page.locator(pilot.root).locator(pilot.field).first()
      await expect(reloadedField).toHaveValue(marker)

      const restorePromise = targetPut(page, pilot)
      await reloadedField.fill(originalRemark)
      await reloadedField.blur()
      expect((await restorePromise).ok(), `${pilot.code} 恢复 PUT 应成功`).toBeTruthy()
      expect((await apiItem(page.request, token, pilot))?.remark ?? '').toBe(originalRemark)
      expect(dbItem(pilot)?.remark ?? '').toBe(originalRemark)

      expect(consoleErrors, `${pilot.code} console/pageerror 必须为 0`).toEqual([])
      expect(counts.renderConfigGet).toBeGreaterThanOrEqual(2)
      expect(counts.checklistPut).toBeGreaterThanOrEqual(2)
      console.log(`ROUND_TRIP_METRICS ${pilot.code} ${JSON.stringify(counts)}`)
    })
  }
})
