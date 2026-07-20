/**
 * G7-17 减值测试 Round-Trip
 * 打开页签 → 新增行 → 迹象=是 → 填公允/使用价值 → 公式取高+减值
 * → 防抖落库 G7-17-rows → 刷新回显 → 导出 200 → 清理
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const PROJECT_ID = process.env.E2E_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const ROWS_KEY = 'G7-17-rows'
const SECTION_KEY = 'G7-17-impairment-test'
const MARKER = `G717-RT-${Date.now()}`

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

async function resolveG7WpId(request: APIRequestContext, token: string): Promise<string> {
  const envWp = process.env.E2E_G7_WP_ID
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
    return code === 'G7' || code.startsWith('G7') || /长期股权投资/.test(name)
  })
  expect(hit?.id || hit?.wp_id, '应找到 G7 长期股权投资底稿').toBeTruthy()
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
    if (Array.isArray(parsed?.rows)) return parsed.rows
  } catch { /* ignore */ }
  return []
}

async function openG717(page: Page) {
  const card = page.locator('.gt-b-arch__card').filter({ hasText: /G7-17/ }).first()
  if (await card.isVisible({ timeout: 8000 }).catch(() => false)) {
    await card.scrollIntoViewIfNeeded()
    await card.click()
  } else {
    const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: /G7-17|减值测试/ })
    await expect(tab.first(), 'G7-17 tab 应可见').toBeVisible({ timeout: 30_000 })
    await tab.first().click()
  }
  await expect(page.locator('.g7-tab-impairment-test'), 'G7-17 根容器应可见').toBeVisible({ timeout: 30_000 })
}

async function findRowByInvesteeName(root: ReturnType<Page['locator']>, name: string) {
  const rows = root.locator('.el-table__body tr')
  const count = await rows.count()
  for (let i = 0; i < count; i += 1) {
    const row = rows.nth(i)
    const input = row.locator('.el-input input').first()
    if (!(await input.count())) continue
    const val = await input.inputValue().catch(() => '')
    if (val.includes(name)) return row
  }
  return null
}

test.describe('G7-17 减值测试 Round-Trip', () => {
  test('迹象联动+公式列落库并刷新回显+导出', async ({ page, request }) => {
    test.setTimeout(90_000)
    const consoleErrors: string[] = []
    page.on('pageerror', err => consoleErrors.push(String(err)))
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const token = await login(page)
    const wpId = await resolveG7WpId(request, token)
    const before = await checklistItem(request, token, wpId, ROWS_KEY)
    const beforeRows = parseRows(before)

    // 仅写 ROWS 真源（与 IE/linkage 对齐）；避免 section 脏数据干扰
    const seedRows = [{
      id: `g17-${MARKER}`,
      seq: 1,
      investeeName: MARKER,
      bookValue: 100000,
      recoverableAmount: 0,
      hasImpairmentSign: false,
      impairmentAmount: 0,
      fvLessDisposalCost: 0,
      valueInUse: 0,
      auditConclusion: '',
      indexRef: '',
    }]
    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: ROWS_KEY, conclusion: JSON.stringify(seedRows), remark: JSON.stringify(seedRows) },
          { item_id: SECTION_KEY, conclusion: JSON.stringify({ rows: seedRows }), remark: null },
        ],
      },
    })

    await page.goto(
      `/projects/${PROJECT_ID}/workpapers/${wpId}/edit?g717=${encodeURIComponent(MARKER)}`,
      { waitUntil: 'domcontentloaded' },
    )
    await openG717(page)

    const root = page.locator('.g7-tab-impairment-test')
    await expect(root.getByText('减值判断标准（CAS8）')).toBeVisible()
    await expect(root.getByRole('button', { name: /从关联表带入/ })).toBeVisible()
    await expect(root.getByRole('button', { name: /导入导出/ })).toBeVisible()

    let row = await findRowByInvesteeName(root, MARKER)
    await expect.poll(async () => {
      row = await findRowByInvesteeName(root, MARKER)
      return row != null
    }, { timeout: 15_000 }).toBeTruthy()
    row = (await findRowByInvesteeName(root, MARKER))!

    // 减值迹象 → 是（Element Plus 选项 class 为 el-select-dropdown__item）
    const signSelect = row.locator('.el-select').first()
    await signSelect.click()
    const yesOpt = page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '是' }).first()
    await expect(yesOpt).toBeVisible({ timeout: 5_000 })
    await yesOpt.click()

    // 迹象=是后：账面/期初已提/公允/使用价值 可编辑（可收回为公式列）
    const enabledNums = row.locator('.el-input-number input:not([disabled])')
    await expect.poll(async () => enabledNums.count(), { timeout: 5_000 }).toBeGreaterThanOrEqual(4)
    await enabledNums.nth(2).fill('75000')
    await enabledNums.nth(2).blur()
    await enabledNums.nth(3).fill('82000')
    await enabledNums.nth(3).blur()

    await expect(row.locator('.formula-cell').filter({ hasText: /82[,.]?000/ }).first()).toBeVisible({ timeout: 5_000 })
    await expect(row.locator('.impairment-positive').first()).toContainText(/18[,.]?000/)
    await expect(root.getByRole('button', { name: /同步至 G7-14/ })).toBeVisible()
    await expect(root.locator('.recon-panel')).toBeVisible()

    // 双零告警：清空公允/使用价值后应出现
    await enabledNums.nth(2).fill('0')
    await enabledNums.nth(2).blur()
    await enabledNums.nth(3).fill('0')
    await enabledNums.nth(3).blur()
    await expect(root.locator('.warn-alert').filter({ hasText: /公允净额与使用价值均为 0/ })).toBeVisible({ timeout: 5_000 })
    await enabledNums.nth(2).fill('75000')
    await enabledNums.nth(2).blur()
    await enabledNums.nth(3).fill('82000')
    await enabledNums.nth(3).blur()
    await expect(row.locator('.impairment-positive').first()).toContainText(/18[,.]?000/)

    await page.waitForTimeout(1200)

    let savedRows: any[] = []
    let hit: any
    for (let i = 0; i < 10; i += 1) {
      const item = await checklistItem(request, token, wpId, ROWS_KEY)
      savedRows = parseRows(item)
      hit = savedRows.find(r => String(r.investeeName || '').includes(MARKER))
      if (hit && Number(hit.impairmentAmount) === 18000) break
      await page.waitForTimeout(400)
    }
    expect(hit, `应落库含 ${MARKER} 的减值行`).toBeTruthy()
    expect(hit.hasImpairmentSign === true || hit.hasImpairmentSign === '是').toBeTruthy()
    expect(Number(hit.recoverableAmount)).toBe(82000)
    expect(Number(hit.impairmentAmount)).toBe(18000)

    const sectionItem = await checklistItem(request, token, wpId, SECTION_KEY)
    const sectionRows = parseRows(sectionItem)
    expect(sectionRows.some(r => String(r.investeeName || '').includes(MARKER))).toBeTruthy()

    await page.reload({ waitUntil: 'domcontentloaded' })
    await openG717(page)
    const root2 = page.locator('.g7-tab-impairment-test')
    await expect.poll(async () => !!(await findRowByInvesteeName(root2, MARKER)), { timeout: 15_000 }).toBeTruthy()
    const row2 = (await findRowByInvesteeName(root2, MARKER))!
    await expect(row2.locator('.impairment-positive').first()).toContainText(/18/)

    const tpl = await request.post(`/api/workpapers/${wpId}/g7-equity-method/export-template?sheet=G7-17`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(tpl.ok(), `导出模板应成功 status=${tpl.status()}`).toBeTruthy()
    const exp = await request.post(`/api/workpapers/${wpId}/g7-equity-method/export-data?sheet=G7-17`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(exp.ok(), `导出数据应成功 status=${exp.status()}`).toBeTruthy()

    const cleaned = savedRows.filter(r => !String(r.investeeName || '').includes(MARKER) && !String(r.investeeName || '').includes('DBG-NAME') && !String(r.investeeName || '').includes('PROBE-G717'))
    const payload = cleaned.length ? cleaned : beforeRows.filter(r => !String(r.investeeName || '').includes('G717-RT-'))
    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: ROWS_KEY, conclusion: JSON.stringify(payload), remark: JSON.stringify(payload) },
          { item_id: SECTION_KEY, conclusion: JSON.stringify({ rows: payload }), remark: null },
        ],
      },
    })

    const fatal = consoleErrors.filter(e =>
      !/ResizeObserver|favicon|net::ERR_|401|SSE|EventSource/i.test(e),
    )
    expect(fatal, `不应有 console error: ${fatal.join(' | ')}`).toEqual([])
  })
})
