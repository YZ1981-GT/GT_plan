/**
 * G7-12 一揽子处置 Round-Trip
 * UI 打开 → 六区段/各次交易可见 → API 写入含 steps → 刷新回显 → 导出 200 → 清理
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = process.env.E2E_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const ROWS_KEY = 'G7-12-rows'
const MARKER = `G712-RT-${Date.now()}`

test.setTimeout(90_000)

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

  for (let pageNo = 1; pageNo <= 20; pageNo += 1) {
    const res = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { page: pageNo, page_size: 100 },
    })
    expect(res.ok(), `working-papers page=${pageNo} 应成功`).toBeTruthy()
    const body = await res.json()
    const data = body?.data ?? body
    const list: any[] = Array.isArray(data) ? data : (data?.items ?? [])
    if (!list.length) break
    const hit = list.find((w: any) => String(w.wp_code || '') === 'G7')
    if (hit) return String(hit.wp_id ?? hit.id)
  }

  for (const code of ['G7', 'G7-12', 'G7-1']) {
    const hit = await findWorkpaper(request, token, code, PROJECT_ID)
    if (hit.exists && hit.wpId) return hit.wpId
  }
  throw new Error(`未找到 G7 底稿 project=${PROJECT_ID}`)
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

async function openG712(page: Page) {
  // 必须用 G7-12：G7-11 文案含「非一揽子」，用「一揽子」会误点到单次处置页
  const card = page.locator('.gt-b-arch__card').filter({ hasText: /G7-12/ }).first()
  if (await card.isVisible({ timeout: 8000 }).catch(() => false)) {
    await card.scrollIntoViewIfNeeded()
    await card.click()
  } else {
    const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: /G7-12/ })
    await expect(tab.first(), 'G7-12 tab 应可见').toBeVisible({ timeout: 30_000 })
    await tab.first().click()
  }
  await expect(page.locator('.g7-tab-disposal-package'), 'G7-12 根容器应可见').toBeVisible({ timeout: 30_000 })
}

test.describe('G7-12 一揽子处置 Round-Trip', () => {
  test('各次交易+公式区落库并刷新回显+导出', async ({ page, request }) => {
    const consoleErrors: string[] = []
    page.on('pageerror', err => consoleErrors.push(String(err)))
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const token = await login(page)
    const wpId = await resolveG7WpId(request, token)
    const before = await checklistItem(request, token, wpId, ROWS_KEY)
    const beforeRows = parseRows(before)

    await page.goto(
      `/projects/${PROJECT_ID}/workpapers/${wpId}/edit?g712=${encodeURIComponent(MARKER)}`,
      { waitUntil: 'domcontentloaded' },
    )
    await openG712(page)

    const root = page.locator('.g7-tab-disposal-package')
    await expect(root.getByRole('heading', { name: /各次交易明细/ })).toBeVisible()
    await expect(root.locator('summary').filter({ hasText: '编制提示' })).toBeVisible()
    await expect(root.getByRole('button', { name: '新增交易次' })).toBeVisible()

    const rows = [{
      id: `g712-${MARKER}`,
      seq: 1,
      investeeName: MARKER,
      registeredPlace: '深圳',
      businessNature: '制造',
      originalShareholdingRatio: 0.8,
      votingRatio: 0.8,
      disposalReason: '分步转让',
      judgmentSimultaneous: 'yes',
      judgmentCompleteResult: 'yes',
      judgmentInterdependent: 'no',
      judgmentEconomicTogether: 'yes',
      packageJudgmentConclusion: 'yes',
      packageJudgmentBasis: `${MARKER} 一揽子判断依据`,
      steps: [
        { id: 's1', seq: 1, stepDate: '2024-03-01', consideration: 400, shareChange: 0.2, note: '第1次' },
        { id: 's2', seq: 2, stepDate: '2025-06-15', consideration: 500, shareChange: 0.3, note: '第2次丧失控制' },
      ],
      transactionDate: '2024-03-01',
      transactionPrice: 900,
      disposalRatio: 0.5,
      remainingShareholdingRatio: 0.3,
      remainingInterestType: '联营',
      disposalMethod: '股权转让',
      lossOfControlDate: '2025-06-15',
      lossOfControlBasis: '交割完成',
      evidenceObtained: '协议+工商变更',
      indexRef: 'G7-12-1',
      individualBookValue: 800,
      residualFairValue: 360,
      associateJointVentureRecyclableOci: 0,
      financialAssetRecyclableOci: 0,
      nonRecyclableOci: 0,
      consolidatedNetAssets: 1000,
      goodwill: 50,
      residualFairValueMethod: '市场法',
      consolidatedRecyclableOci: 20,
      priorStepDifference: 10,
      equityMethodRatio: 0.3,
      preDisposalProfit: 100,
      currentProfit: 20,
      otherComprehensiveIncome: 10,
      otherEquityChanges: 5,
      surplusReserveRate: 0.1,
      auditConclusion: '',
    }]

    const putRes = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [{ item_id: ROWS_KEY, conclusion: JSON.stringify(rows), remark: null }],
      },
    })
    expect(putRes.ok(), `PUT 应成功 status=${putRes.status()}`).toBeTruthy()

    const saved = await checklistItem(request, token, wpId, ROWS_KEY)
    const savedRows = parseRows(saved)
    const hit = savedRows.find(r => String(r.investeeName || '').includes(MARKER))
    expect(hit, '应落库含 marker 的公司行').toBeTruthy()
    expect(hit.steps?.length).toBe(2)
    expect(Number(hit.transactionPrice)).toBe(900)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await openG712(page)
    const rootAfter = page.locator('.g7-tab-disposal-package')
    await expect(rootAfter).toContainText(MARKER)
    await expect(rootAfter.getByRole('heading', { name: /各次交易明细/ })).toBeVisible()
    await expect(rootAfter.locator('summary').filter({ hasText: '编制提示' })).toBeVisible()

    const exportRes = await request.post(`/api/workpapers/${wpId}/g7-sub/export-data?sheet=G7-12`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(exportRes.ok(), `导出应成功 status=${exportRes.status()}`).toBeTruthy()

    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [{
          item_id: ROWS_KEY,
          conclusion: JSON.stringify(beforeRows),
          remark: null,
        }],
      },
    })

    const fatal = consoleErrors.filter(e =>
      !/ResizeObserver|favicon|net::ERR_|Failed to load resource/i.test(e),
    )
    expect(fatal, `不应有 console error: ${fatal.join(' | ')}`).toEqual([])
  })
})
