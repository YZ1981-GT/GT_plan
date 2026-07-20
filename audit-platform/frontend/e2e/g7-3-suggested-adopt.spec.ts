/**
 * G7-3 建议草稿：落库 → 打开 → 采纳 → sourceKind 清除
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const PROJECT_ID = process.env.E2E_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const ROWS_KEY = 'G7-3-rows'
const MARKER = `G73-ADOPT-${Date.now()}`
const SOURCE_KIND = 'g7-14-suggested'

async function login(page: Page): Promise<string> {
  let response
  for (let attempt = 0; attempt < 3; attempt += 1) {
    response = await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (response.ok()) break
    await new Promise(r => setTimeout(r, 1000))
  }
  expect(response?.ok(), `登录应成功 status=${response?.status()}`).toBeTruthy()
  const body = await response!.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, '应返回 access_token').toBeTruthy()
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  return token as string
}

async function resolveG7MainWpId(request: APIRequestContext, token: string): Promise<string> {
  const envWp = process.env.E2E_G7_MAIN_WP_ID || process.env.E2E_G7_WP_ID
  if (envWp) return envWp

  const res = await request.get(`/api/projects/${PROJECT_ID}/workpapers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(res.ok(), '项目底稿列表应成功').toBeTruthy()
  const body = await res.json()
  const data = body?.data ?? body
  const list = Array.isArray(data) ? data : (data?.items ?? data?.workpapers ?? [])
  const hit = list.find((w: any) => {
    const code = String(w.wp_code ?? w.code ?? w.index_code ?? '')
    const name = String(w.name ?? w.sheet_name ?? w.title ?? w.wp_name ?? '')
    const ctype = String(w.component_type ?? w.componentType ?? '')
    return ctype.includes('g7-long-term-equity-main')
      || (code === 'G7' && !/权益法|子公司/.test(name))
      || /调整分录汇总|长期股权投资主/.test(name)
  })
  expect(hit?.id || hit?.wp_id, '应找到 G7 主表底稿').toBeTruthy()
  return String(hit.id ?? hit.wp_id)
}

async function checklistItem(
  request: APIRequestContext,
  token: string,
  wpId: string,
  itemId: string,
): Promise<any | undefined> {
  const response = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok(), 'checklist GET 应成功').toBeTruthy()
  const body = await response.json()
  const data = body?.data ?? body
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.find((item: any) => item.item_id === itemId)
}

function parseRows(item: any): any[] {
  const raw = item?.conclusion ?? item?.remark
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.entries)) return parsed.entries
  } catch { /* ignore */ }
  return []
}

async function openG73(page: Page) {
  const card = page.locator('.gt-b-arch__card').filter({ hasText: /G7-3|调整分录/ }).first()
  if (await card.isVisible({ timeout: 8000 }).catch(() => false)) {
    await card.scrollIntoViewIfNeeded()
    await card.click()
  } else {
    const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: /G7-3|调整分录/ })
    await expect(tab.first(), 'G7-3 tab 应可见').toBeVisible({ timeout: 30_000 })
    await tab.first().click()
  }
  await expect(page.locator('.g7-tab-adjustment'), 'G7-3 根容器应可见').toBeVisible({ timeout: 30_000 })
}

test.describe('G7-3 建议草稿采纳', () => {
  test('落库建议 → UI 显示草稿 → 采纳后清除 sourceKind', async ({ page, request }) => {
    test.setTimeout(90_000)
    const token = await login(page)
    const wpId = await resolveG7MainWpId(request, token)
    const before = await checklistItem(request, token, wpId, ROWS_KEY)
    const beforeRows = parseRows(before)

    const seedRows = [
      {
        id: `g73-manual-${MARKER}`,
        seq: 1,
        description: `${MARKER}-手工`,
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '1511',
        accountName: '长期股权投资',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: 'G7-3',
        remark: '',
        entryType: 'AJE',
      },
      {
        id: `g73-sug-dr-${MARKER}`,
        seq: 2,
        description: `${MARKER}-建议借`,
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '1511',
        accountName: '长期股权投资',
        debitAmount: 5000,
        creditAmount: 0,
        indexRef: 'G7-14',
        remark: `sourceKind=${SOURCE_KIND}`,
        sourceKind: SOURCE_KIND,
        investeeName: '联营甲',
        entryType: 'AJE',
      },
      {
        id: `g73-sug-cr-${MARKER}`,
        seq: 3,
        description: `${MARKER}-建议贷`,
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '6111',
        accountName: '投资收益',
        debitAmount: 0,
        creditAmount: 5000,
        indexRef: 'G7-14',
        remark: `sourceKind=${SOURCE_KIND}`,
        sourceKind: SOURCE_KIND,
        investeeName: '联营甲',
        entryType: 'AJE',
      },
    ]

    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: ROWS_KEY, conclusion: JSON.stringify(seedRows), remark: JSON.stringify(seedRows) },
        ],
      },
    })

    await page.goto(
      `/projects/${PROJECT_ID}/workpapers/${wpId}/edit?g73=${encodeURIComponent(MARKER)}`,
      { waitUntil: 'domcontentloaded' },
    )
    await openG73(page)

    const root = page.locator('.g7-tab-adjustment')
    await expect(root.getByRole('button', { name: /采纳全部建议/ })).toBeVisible({ timeout: 15_000 })
    await expect(root.locator('.draft-tag').filter({ hasText: /G7-14|建议/ }).first()).toBeVisible()

    // 建议行借贷应为只读（无 input-number）
    const sugRow = root.locator('.el-table__body tr').filter({ hasText: `${MARKER}-建议借` }).first()
    await expect(sugRow).toBeVisible()
    await expect(sugRow.locator('.el-input-number input')).toHaveCount(0)

    await root.getByRole('button', { name: /采纳全部建议/ }).click()
    const confirm = page.locator('.el-message-box').filter({ hasText: /采纳/ })
    if (await confirm.isVisible({ timeout: 3000 }).catch(() => false)) {
      await confirm.getByRole('button', { name: /采纳|确定|确认/ }).click()
    }

    await expect.poll(async () => {
      const item = await checklistItem(request, token, wpId, ROWS_KEY)
      const rows = parseRows(item)
      const sug = rows.filter(r => String(r.description || '').includes(MARKER) && String(r.description || '').includes('建议'))
      if (sug.length < 2) return false
      return sug.every(r => !r.sourceKind && !String(r.remark || '').includes(`sourceKind=${SOURCE_KIND}`))
    }, { timeout: 15_000 }).toBeTruthy()

    // 清理
    const cleaned = beforeRows.filter(r => !String(r.description || '').includes('G73-ADOPT-'))
    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: ROWS_KEY, conclusion: JSON.stringify(cleaned), remark: JSON.stringify(cleaned) },
        ],
      },
    })
  })
})
