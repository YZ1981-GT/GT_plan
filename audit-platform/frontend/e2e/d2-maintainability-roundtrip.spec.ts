import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'e2c95d10-181d-4549-8910-d5ab5bc5edd1'
const DETAIL_ITEM_ID = 'D2-detail-rows'

async function login(page: Page): Promise<string> {
  const response = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(response.ok(), `登录 API 应成功，status=${response.status()}`).toBeTruthy()
  const body = await response.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  return token
}

async function checklistItem(request: APIRequestContext, token: string): Promise<any> {
  const response = await request.get(`/api/workpapers/${WP_ID}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 15_000,
  })
  expect(response.ok(), 'D2 checklist GET 应成功').toBeTruthy()
  const body = await response.json()
  const data = body?.data ?? body
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.find((item: any) => item.item_id === DETAIL_ITEM_ID)
}

const SHEET_ROOTS: Record<string, string> = {
  'D2-2': '.d2-tab-detail',
  'D2-7': '.d2-voucher-check',
}

async function openSheet(page: Page, sheetCode: string, nonce: string): Promise<void> {
  await page.goto(
    `/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit?d2RoundTrip=${encodeURIComponent(nonce)}`,
    { waitUntil: 'domcontentloaded' },
  )

  // 目标卡片可见即证明 Renderer 与 loading overlay 均已完成，不做重复串行等待。
  const escaped = sheetCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const card = page.locator('.gt-b-arch__card')
    .filter({ hasText: new RegExp(`${escaped}(?!\\d)`) })
    .first()
  await expect(card, `${sheetCode} 目录卡片应可见`).toBeVisible({ timeout: 30_000 })
  await card.scrollIntoViewIfNeeded()
  await card.click()

  const root = SHEET_ROOTS[sheetCode]
  if (root) await expect(page.locator(root)).toBeVisible({ timeout: 30_000 })
}

async function switchSheet(page: Page, sheetCode: string): Promise<void> {
  const escaped = sheetCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]')
    .filter({ hasText: new RegExp(`${escaped}(?!\\d)`) })
  await expect(tab, `${sheetCode} sheet tab 应唯一`).toHaveCount(1)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
  const root = SHEET_ROOTS[sheetCode]
  if (root) await expect(page.locator(root)).toBeVisible({ timeout: 30_000 })
}

async function restoreOriginalRows(
  request: APIRequestContext,
  token: string,
  originalItem: any,
  originalRows: any[],
): Promise<void> {
  const response = await request.put(`/api/workpapers/${WP_ID}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      project_id: PROJECT_ID,
      items: [{
        item_id: DETAIL_ITEM_ID,
        conclusion: originalItem?.conclusion ?? null,
        remark: JSON.stringify(originalRows),
        wp_ref: originalItem?.wp_ref ?? null,
      }],
    },
    timeout: 15_000,
  })
  expect(response.ok(), `D2-2 失败清理 PUT 应成功，status=${response.status()}`).toBeTruthy()
}

function detailPut(page: Page) {
  return page.waitForResponse(response => {
    if (response.request().method() !== 'PUT') return false
    if (!response.url().includes(`/api/workpapers/${WP_ID}/checklist-responses`)) return false
    try {
      return response.request().postDataJSON()?.items?.some(
        (item: any) => item.item_id === DETAIL_ITEM_ID,
      ) ?? false
    } catch {
      return false
    }
  }, { timeout: 20_000 })
}

async function editableCustomerInput(page: Page, filterText: string) {
  await expect(page.locator('.d2-tab-detail')).toBeVisible({ timeout: 30_000 })
  expect(filterText, 'D2-2 目标客户名称不得为空').not.toBe('')
  const searchInput = page.locator('.d2-tab-detail .toolbar-right input')
  await expect(searchInput).toBeEditable()
  await searchInput.fill(filterText)
  await expect.poll(async () => {
    const text = await page.locator('.d2-tab-detail .virtual-hint').textContent()
    const match = text?.match(/（(\d+) 行）/)
    return Number(match?.[1] ?? Number.POSITIVE_INFINITY)
  }, { message: 'D2-2 搜索应先把 1260 行收敛到少量目标行', timeout: 10_000 })
    .toBeLessThanOrEqual(10)

  const switchButton = page.getByRole('button', { name: '切换表格编辑' })
  if (await switchButton.isVisible().catch(() => false)) await switchButton.click()
  const input = page.locator('.d2-tab-detail .el-table__body-wrapper input').first()
  await expect(input, 'D2-2 筛选后应有一行可编辑客户明细').toBeEditable({ timeout: 30_000 })
  return input
}

test('D2: 明细编辑保存、fresh navigation 回显、真实复核与版本入口', async ({ page }) => {
  test.setTimeout(240_000)
  const consoleErrors: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => consoleErrors.push(`pageerror: ${error.message}`))

  const token = await login(page)
  const originalItem = await checklistItem(page.request, token)
  const originalRows = JSON.parse(originalItem?.remark || '[]')
  expect(originalRows.length, 'D2-2 测试数据应至少有一行').toBeGreaterThan(0)
  const originalName = String(originalRows[0]?.customerName ?? '')
  const marker = `D2明细RT-${Date.now()}`
  console.log('[d2-rt] baseline loaded')

  try {
    await openSheet(page, 'D2-2', `write-${marker}`)
    console.log('[d2-rt] first D2-2 navigation complete')
    const input = await editableCustomerInput(page, originalName)
    console.log('[d2-rt] filtered edit input ready')
    const saveResponse = detailPut(page)
    await input.fill(marker)
    expect((await saveResponse).ok(), 'D2-2 明细 PUT 应成功').toBeTruthy()
    console.log('[d2-rt] PUT response observed')
    const savedRows = JSON.parse((await checklistItem(page.request, token))?.remark || '[]')
    expect(savedRows[0]?.customerName).toBe(marker)
    console.log('[d2-rt] write + API readback complete')

    await openSheet(page, 'D2-2', `read-${marker}`)
    await expect(await editableCustomerInput(page, marker)).toHaveValue(marker)
    console.log('[d2-rt] fresh navigation UI readback complete')

    await page.locator('.gt-wp-review-rail').click()
    await expect(page.locator('.review-dialog-drawer')).toBeVisible()
    await expect(page.locator('.review-dialog-drawer .header-title')).toContainText(/D2|复核/)
    await page.keyboard.press('Escape')
    await expect(page.locator('.review-dialog-drawer')).toBeHidden()
    console.log('[d2-rt] review drawer complete')

    await switchSheet(page, 'D2-7')
    console.log('[d2-rt] D2-7 navigation complete')
    await page.getByRole('button', { name: '版本历史' }).first().click()
    await expect(page.locator('.version-trail-drawer')).toBeVisible()
    await expect(page.locator('.version-trail-drawer')).toContainText('版本历史')
    await page.keyboard.press('Escape')
    await expect(page.locator('.version-trail-drawer')).toBeHidden()
    console.log('[d2-rt] version drawer complete')

    await restoreOriginalRows(page.request, token, originalItem, originalRows)
    const restoredRows = JSON.parse((await checklistItem(page.request, token))?.remark || '[]')
    expect(restoredRows[0]?.customerName).toBe(originalName)

    expect(consoleErrors, 'D2 整个 fresh-navigation Round_Trip console/pageerror 必须为 0').toEqual([])
  } finally {
    // 任一用户可见断言失败也不得把 marker 留在共享测试项目中。
    try {
      const currentItem = await checklistItem(page.request, token)
      const currentRows = JSON.parse(currentItem?.remark || '[]')
      if (currentRows.some((row: any) => row?.customerName === marker)) {
        await restoreOriginalRows(page.request, token, originalItem, originalRows)
      }
    } catch (cleanupError) {
      console.warn('[d2-rt] cleanup failed:', cleanupError)
    }
  }
})
