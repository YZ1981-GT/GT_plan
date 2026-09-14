/**
 * G7-18 凭证检查表 Round-Trip
 * UI 打开 → 样本标准区可见 → API 写入 rows/criteria → 刷新回显 → 导出 200 → 清理
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = process.env.E2E_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const ROWS_KEY = 'G7-18-rows'
const CRITERIA_KEY = 'G7-18-criteria'
const MARKER = `G718-RT-${Date.now()}`

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

  for (let page = 1; page <= 20; page += 1) {
    const res = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { page, page_size: 100 },
    })
    expect(res.ok(), `working-papers page=${page} 应成功`).toBeTruthy()
    const body = await res.json()
    const data = body?.data ?? body
    const list: any[] = Array.isArray(data) ? data : (data?.items ?? [])
    if (!list.length) break
    const hit = list.find((w: any) => String(w.wp_code || '') === 'G7')
    if (hit) return String(hit.wp_id ?? hit.id)
  }

  for (const code of ['G7', 'G7-18', 'G7-1']) {
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

async function openG718(page: Page) {
  const card = page.locator('.gt-b-arch__card').filter({ hasText: /G7-18|凭证检查/ }).first()
  if (await card.isVisible({ timeout: 8000 }).catch(() => false)) {
    await card.scrollIntoViewIfNeeded()
    await card.click()
  } else {
    const tab = page.locator('.gt-wp-renderer__sheet-tabs-inner [role="tab"]').filter({ hasText: /G7-18|凭证检查/ })
    await expect(tab.first(), 'G7-18 tab 应可见').toBeVisible({ timeout: 30_000 })
    await tab.first().click()
  }
  await expect(page.locator('.g7-tab-voucher-check'), 'G7-18 根容器应可见').toBeVisible({ timeout: 30_000 })
}

test.describe('G7-18 凭证检查 Round-Trip', () => {
  test('样本标准区+行落库+刷新回显+导出', async ({ page, request }) => {
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
      `/projects/${PROJECT_ID}/workpapers/${wpId}/edit?g718=${encodeURIComponent(MARKER)}`,
      { waitUntil: 'domcontentloaded' },
    )
    await openG718(page)

    const root = page.locator('.g7-tab-voucher-check')
    await expect(root.getByText('样本选取标准与结果')).toBeVisible()
    await expect(root.getByText('检查比例').first()).toBeVisible()
    await expect(root.getByRole('button', { name: '+ 新增' })).toBeVisible()

    // UI 新增一行（验证可交互）
    await root.getByRole('button', { name: '+ 新增' }).click()
    await page.waitForTimeout(600)

    // API 写入 2 行 + criteria（权威 round-trip）
    const rows = [
      {
        id: `g18-${MARKER}-1`,
        seq: 1,
        voucherDate: '2025-06-01',
        voucherNo: `${MARKER}-V1`,
        businessContent: '取得子公司股权',
        counterAccount: '银行存款',
        debitAmount: 1000,
        creditAmount: 0,
        attachment: '',
        supportingDoc: '股权转让协议',
        check1Original: true,
        check2Authorization: true,
        check3Accounting: true,
        check4Amount: true,
        check5Classification: true,
        check6InvestmentIncome: true,
        indexRef: 'G7-18-1',
        isAbnormal: false,
        abnormalNote: '',
        riskLevel: '低',
        remark: MARKER,
      },
      {
        id: `g18-${MARKER}-2`,
        seq: 2,
        voucherDate: '2025-06-15',
        voucherNo: `${MARKER}-V2`,
        businessContent: '确认投资收益',
        counterAccount: '投资收益',
        debitAmount: 0,
        creditAmount: 200,
        supportingDoc: '利润分配决议',
        check1Original: true,
        check2Authorization: true,
        check3Accounting: true,
        check4Amount: false,
        check5Classification: true,
        check6InvestmentIncome: true,
        indexRef: 'G7-18-2',
        isAbnormal: true,
        abnormalNote: '金额待核实',
        riskLevel: '中',
        remark: MARKER,
      },
    ]

    const putRes = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          {
            item_id: ROWS_KEY,
            conclusion: JSON.stringify(rows),
            remark: null,
          },
          {
            item_id: CRITERIA_KEY,
            remark: JSON.stringify({
              testScope: '长期股权投资（1511）RoundTrip',
              populationCount: 10,
              populationAmount: 1_000_000,
              samplingMethod: '随机选样',
              specificSample: MARKER,
              representativeSize: 2,
              endBalance: 500_000,
              populationDebitAmount: 1_000_000,
              populationCreditAmount: 200_000,
            }),
            conclusion: null,
          },
        ],
      },
    })
    expect(putRes.ok(), `checklist PUT 应成功 status=${putRes.status()}`).toBeTruthy()

    // API 回读
    const saved = await checklistItem(request, token, wpId, ROWS_KEY)
    const savedRows = parseRows(saved)
    expect(savedRows.some(r => String(r.voucherNo || '').includes(MARKER))).toBeTruthy()
    expect(savedRows.find(r => String(r.voucherNo).includes('V2'))?.isAbnormal).toBeTruthy()

    const crit = await checklistItem(request, token, wpId, CRITERIA_KEY)
    const critObj = typeof crit?.remark === 'string' ? JSON.parse(crit.remark) : crit?.remark
    expect(String(critObj?.specificSample || '')).toContain(MARKER)

    // 刷新 UI 回显（凭证号在 input 内，不能用 toContainText 扫整卡）
    await page.reload({ waitUntil: 'domcontentloaded' })
    await openG718(page)
    const rootAfter = page.locator('.g7-tab-voucher-check')
    await expect(rootAfter).toContainText('样本选取标准与结果')
    await expect(rootAfter).toContainText('共 2 行')
    await expect(rootAfter).toContainText('异常 1')
    await expect(rootAfter).toContainText('1000.00')
    await expect(rootAfter).toContainText('200.00')
    const voucherInputs = rootAfter.locator('.el-tab-pane').first().locator('input')
    await expect
      .poll(async () => {
        const values = await voucherInputs.evaluateAll(els =>
          els.map(el => (el as HTMLInputElement).value || ''),
        )
        return values.some(v => v.includes(MARKER))
      }, { timeout: 10_000 })
      .toBeTruthy()

    // 导出
    const exportRes = await request.post(`/api/workpapers/${wpId}/g7-sub/export-data?sheet=G7-18`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(exportRes.ok(), `导出应成功 status=${exportRes.status()}`).toBeTruthy()

    // 清理
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
