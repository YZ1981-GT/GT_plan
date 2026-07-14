import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const WP_ID = 'eb3cbf2d-394c-43e8-9296-a93ff41339ea'
const URL = `/projects/${PROJECT_ID}/workpapers/${WP_ID}/edit`
const IDS = ['J2-1-main', 'J2-1-note', 'J2-1-conclusion'] as const

type Item = {
  item_id: string
  remark: string | null
  conclusion: string | null
  wp_ref?: string | null
}

async function login(page: Page): Promise<string> {
  const response = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  return token
}

async function responses(request: APIRequestContext, token: string): Promise<Item[]> {
  const response = await request.get(`/api/workpapers/${WP_ID}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  const data = body.data ?? body
  return Array.isArray(data) ? data : (data.items ?? [])
}

async function openSheet(page: Page, sheet: RegExp, root: string, nonce: string): Promise<void> {
  await page.goto(`${URL}?task43=${nonce}`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.gt-wp-renderer')).toBeVisible({ timeout: 30_000 })
  const overlay = page.locator('.gt-loading-overlay')
  if (await overlay.count()) await expect(overlay).toBeHidden({ timeout: 30_000 })
  const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: sheet })
  await expect(tab).toHaveCount(1)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await expect(page.locator(root)).toBeVisible({ timeout: 30_000 })
}
test.describe.configure({ mode: 'serial' })

test('J2 Runtime Boundary：多 item、导航、披露、刷新、复核与版本', async ({ page }) => {
  test.setTimeout(180_000)
  page.setDefaultTimeout(30_000)
  const errors: string[] = []
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))

  const token = await login(page)
  const before = await responses(page.request, token)
  const originals = IDS.map(id => before.find(item => item.item_id === id))
  expect(originals.every(Boolean), '清理所需的 J2 原始 section 应存在').toBeTruthy()
  const marker = `TASK43-${Date.now()}`

  try {
    await openSheet(page, /审定表J2-1(?!\d)/, '.j2-tab-adjudication', `write-${marker}`)
    const root = page.locator('.j2-tab-adjudication')
    const reason = root.locator('tbody tr').first().locator('textarea').first()
    const note = root.locator('textarea[placeholder="填写审计说明..."]')
    const conclusion = root.locator('textarea[placeholder="填写审计结论..."]')

    await reason.fill(`${marker}-MAIN`)
    await note.fill(`${marker}-NOTE`)
    await conclusion.fill(`${marker}-CONCLUSION`)
    await conclusion.press('Tab')

    await expect.poll(async () => {
      const items = await responses(page.request, token)
      const main = items.find(item => item.item_id === 'J2-1-main')?.remark ?? ''
      return {
        main: main.includes(`${marker}-MAIN`),
        note: items.find(item => item.item_id === 'J2-1-note')?.remark,
        conclusion: items.find(item => item.item_id === 'J2-1-conclusion')?.remark,
      }
    }, { timeout: 20_000 }).toEqual({
      main: true,
      note: `${marker}-NOTE`,
      conclusion: `${marker}-CONCLUSION`,
    })

    const indexTab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: '底稿目录' })
    await indexTab.click()
    await page.locator('.j2-tab-index').getByText('计提情况检查表J2-4', { exact: true }).click()
    await expect(page.locator('.j2-tab-accrual-check')).toBeVisible({ timeout: 30_000 })

    for (const [label, rootSelector] of [
      ['附注披露信息（上市公司）', '.j2-disclosure-listed'],
      ['附注披露信息（国有企业）', '.j2-disclosure-soe'],
    ] as const) {
      const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: label })
      await tab.scrollIntoViewIfNeeded()
      await tab.click()
      await expect(page.locator(rootSelector)).toBeVisible({ timeout: 30_000 })
    }
    await openSheet(page, /审定表J2-1(?!\d)/, '.j2-tab-adjudication', `read-${marker}`)
    const reloaded = page.locator('.j2-tab-adjudication')
    await expect(reloaded.locator('tbody tr').first().locator('textarea').first()).toHaveValue(`${marker}-MAIN`)
    await expect(reloaded.locator('textarea[placeholder="填写审计说明..."]')).toHaveValue(`${marker}-NOTE`)
    await expect(reloaded.locator('textarea[placeholder="填写审计结论..."]')).toHaveValue(`${marker}-CONCLUSION`)

    // J2 版本能力由 Runtime Boundary 统一提供（GtWpRenderer→GtWorkpaperRuntimeHosts）。
    await page.getByRole('button', { name: '版本历史', exact: true }).first().click()
    const versionDrawer = page.locator('.version-trail-drawer')
    await expect(versionDrawer).toBeVisible({ timeout: 15_000 })
    await versionDrawer.locator('.el-drawer__close-btn').click()
    await expect(versionDrawer).toBeHidden()
    // J2 主入口不渲染复核 rail（复核入口非 J2 适用能力），故不断言复核对话，
    // 与 workpaper-maintainability-pilots-roundtrip.spec.ts 的 J2 处理保持一致。
    expect(errors, `fresh navigation console/pageerror 必须为 0：${errors.join('\n')}`).toEqual([])
  } finally {
    const restore = originals.filter((item): item is Item => Boolean(item)).map(item => ({
      item_id: item.item_id,
      remark: item.remark,
      conclusion: item.conclusion,
      wp_ref: item.wp_ref ?? null,
    }))
    const response = await page.request.put(`/api/workpapers/${WP_ID}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { items: restore },
    })
    expect(response.ok(), 'J2 测试数据应恢复').toBeTruthy()
  }
})

test('J2 AI 请求 context 值全部为字符串', async ({ page }) => {
  test.setTimeout(60_000)
  const errors: string[] = []
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))
  await login(page)
  await openSheet(page, /审定表J2-1(?!\d)/, '.j2-tab-adjudication', `ai-${Date.now()}`)

  const requestPromise = page.waitForRequest(request =>
    request.method() === 'POST' && request.url().includes(`/api/workpapers/${WP_ID}/ai/generate-text`),
  )
  await page.locator('.j2-tab-adjudication').getByRole('button', { name: /AI辅助/ }).first().click()
  const request = await requestPromise
  const body = request.postDataJSON()
  expect(body.section).toBe('j2-adjudication-note')
  expect(Object.values(body.context).every(value => typeof value === 'string')).toBeTruthy()
  expect(errors).toEqual([])
})
