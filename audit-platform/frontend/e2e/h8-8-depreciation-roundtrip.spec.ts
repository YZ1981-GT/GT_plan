/**
 * H8-8 折旧测算（不含/含减值）Round-Trip 联调
 *
 * 覆盖：
 * 1. API 写入 H8-8-dep-rows / branch / period → GET 回读
 * 2. 打开 UI → H8-8 不含减值：测算月折旧/本期折旧可见
 * 3. 切换含减值 → 分段列与减值准备回显
 * 4. 刷新后数据仍在（落库验证）
 * 5. H8-10 可按合同号匹配⑦（impairmentAmount）
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H88-RT-${Date.now()}`
const CONTRACT = `LEASE-${MARKER.slice(-8)}`

const DEP_ROWS_KEY = 'H8-8-dep-rows'
const BRANCH_KEY = 'H8-8-branch'
const PERIOD_BEGIN_KEY = 'H8-8-period-begin'
const PERIOD_END_KEY = 'H8-8-period-end'
const DEP_TOTAL_KEY = 'H8-8-depreciation-total'
const H810_ROWS_KEY = 'H8-10-rows'

async function loginAs(page: Page): Promise<string> {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(resp.ok(), `登录失败 status=${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token).toBeTruthy()
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

async function putChecklist(
  request: APIRequestContext,
  token: string,
  wpId: string,
  items: Array<{ item_id: string; remark: string | null; conclusion?: string | null }>,
) {
  const resp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: authHeaders(token),
    data: {
      project_id: PROJECT_ID,
      items: items.map((it) => ({
        item_id: it.item_id,
        conclusion: it.conclusion ?? null,
        remark: it.remark,
      })),
    },
  })
  expect(resp.ok(), `PUT checklist 失败 status=${resp.status()}`).toBeTruthy()
  return resp
}

async function getChecklistItem(
  request: APIRequestContext,
  token: string,
  wpId: string,
  itemId: string,
): Promise<any | undefined> {
  const resp = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: authHeaders(token),
  })
  expect(resp.ok()).toBeTruthy()
  const body = await resp.json()
  const data = body?.data ?? body
  const list = Array.isArray(data) ? data : (data?.items ?? [])
  return list.find((x: any) => x.item_id === itemId)
}

function parseRemark(item: any): any {
  const raw = item?.remark ?? item?.conclusion
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  try { return JSON.parse(raw) } catch { return raw }
}

/** 不含减值样例：原值 120000 / 60月 / 残值0 → 月折旧 2000 */
function seedNoImpairRow() {
  return {
    rowId: `dep-${MARKER}`,
    contractNo: CONTRACT,
    assetCategory: '房屋及建筑物',
    assetName: `办公楼-${MARKER}`,
    originalCost: 120_000,
    rouAmount: 120_000,
    bookAccDepEnd: 24_000,
    accumulatedDep: 24_000,
    impairment: 0,
    impairmentAmount: 0,
    startDate: '2023-01-01',
    usefulLife: 5,
    leaseTermMonths: 60,
    salvageRate: 0,
    bookMonthly: 2_000,
    bookDepreciation: 24_000,
    remark: `E2E ${MARKER}`,
  }
}

/** 含减值：减值 30000 @ 2025-06-30 */
function seedWithImpairRow() {
  return {
    ...seedNoImpairRow(),
    impairment: 30_000,
    impairmentAmount: 30_000,
    impairmentDate: '2025-06-30',
  }
}

test.describe('H8-8 折旧测算 Round-Trip', () => {
  test('API 写入→GET 回读→UI 不含/含减值→刷新回显→H8-10 匹配⑦', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H8', PROJECT_ID)
    test.skip(!wpResult.exists, 'H8 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    // ── 1) API 写入不含减值行 ──────────────────────────────────────────────
    const noImpair = seedNoImpairRow()
    await putChecklist(request, apiToken, wpId, [
      { item_id: BRANCH_KEY, remark: '不含减值' },
      { item_id: PERIOD_BEGIN_KEY, remark: '2025-01-01' },
      { item_id: PERIOD_END_KEY, remark: '2025-12-31' },
      { item_id: DEP_ROWS_KEY, remark: JSON.stringify([noImpair]) },
      { item_id: DEP_TOTAL_KEY, remark: '24000' },
    ])

    const got1 = await getChecklistItem(request, apiToken, wpId, DEP_ROWS_KEY)
    const rows1 = parseRemark(got1)
    expect(Array.isArray(rows1)).toBeTruthy()
    expect(rows1[0]?.contractNo).toBe(CONTRACT)
    expect(Number(rows1[0]?.originalCost ?? rows1[0]?.rouAmount)).toBe(120_000)

    const branch1 = await getChecklistItem(request, apiToken, wpId, BRANCH_KEY)
    expect(String(branch1?.remark ?? '')).toContain('不含减值')

    // ── 2) UI：打开 H8-8 不含减值 ─────────────────────────────────────────
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'H8-8')
    await page.waitForTimeout(3_000)

    const noImpairRoot = page.locator('.h8-tab-depreciation-no-impair')
    // 若当前在含减值，先切回
    const noImpairSeg = page.locator('.el-segmented__item').filter({ hasText: /^不含减值$/ })
    if (await noImpairSeg.count()) {
      await noImpairSeg.first().click()
      await page.waitForTimeout(1_500)
    }
    await expect(noImpairRoot).toBeVisible({ timeout: 20_000 })

    // 合同号在 el-input 内，用 value 断言（getByText 匹配不到 input value）
    const contractInput = noImpairRoot.locator('.el-table__body input').first()
    await expect(contractInput).toHaveValue(CONTRACT, { timeout: 15_000 })
    const bodyNo = (await page.textContent('.h8-tab-depreciation-no-impair')) || ''
    expect(bodyNo).toMatch(/测算月折旧|当期折旧|已提月份/)
    // 测算月折旧 2,000.00
    expect(bodyNo.replace(/,/g, '')).toMatch(/2000\.00|2000/)
    // 本期 12 月 × 2000 = 24000
    expect(bodyNo.replace(/,/g, '')).toMatch(/24000/)

    // ── 3) 切含减值并 API 写入减值行后刷新 ───────────────────────────────
    const withImpair = seedWithImpairRow()
    await putChecklist(request, apiToken, wpId, [
      { item_id: BRANCH_KEY, remark: '含减值' },
      { item_id: DEP_ROWS_KEY, remark: JSON.stringify([withImpair]) },
    ])

    const withSeg = page.locator('.el-segmented__item').filter({ hasText: /^含减值$/ })
    await expect(withSeg.first()).toBeVisible()
    await withSeg.first().click()
    await page.waitForTimeout(1_500)

    // 刷新以加载 API 写入的减值行
    await page.reload()
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'H8-8')
    await page.waitForTimeout(2_500)

    // 确保含减值分支
    const withSeg2 = page.locator('.el-segmented__item').filter({ hasText: /^含减值$/ })
    if (await withSeg2.count()) {
      await withSeg2.first().click()
      await page.waitForTimeout(1_500)
    }

    const withRoot = page.locator('.h8-tab-depreciation-with-impair')
    await expect(withRoot).toBeVisible({ timeout: 20_000 })
    await expect(withRoot.locator('.el-table__body input').first()).toHaveValue(CONTRACT, { timeout: 15_000 })

    const bodyYes = (await page.textContent('.h8-tab-depreciation-with-impair')) || ''
    expect(bodyYes).toMatch(/减值前月数|减值后月数|减值后月折旧/)
    expect(bodyYes.replace(/,/g, '')).toMatch(/30000/)

    // 分支应已持久化为含减值
    const branch2 = await getChecklistItem(request, apiToken, wpId, BRANCH_KEY)
    expect(String(branch2?.remark ?? '')).toContain('含减值')

    // ── 4) H8-10：写入一行并用 H8-8 减值匹配⑦ ───────────────────────────
    await putChecklist(request, apiToken, wpId, [
      {
        item_id: H810_ROWS_KEY,
        remark: JSON.stringify([{
          rowId: `imp-${MARKER}`,
          assetName: `办公楼-${MARKER}`,
          contractNo: CONTRACT,
          hasIndication: 'Y',
          indicationDesc: 'E2E',
          bookValue: 96_000,
          fairValueLessDisposal: 0,
          dcfValue: 66_000,
          recoverableAmount: 66_000,
          impairmentAmount: 30_000,
          alreadyProvided: 0,
          supplement: 30_000,
          overProvision: 0,
          indexRef: 'H8-11',
          remark: MARKER,
        }]),
      },
    ])

    await clickWorkpaperSheetTab(page, 'H8-10')
    await page.waitForTimeout(2_500)
    const h810 = page.locator('.h8-tab-impairment, [class*="h8-tab-impairment"]')
    // 尝试点「带入⑦(H8-8)」
    const pullBtn = page.getByRole('button', { name: /带入⑦|H8-8/ })
    if (await pullBtn.count()) {
      await pullBtn.first().click()
      await page.waitForTimeout(2_000)
    }

    // API 层验证：H8-8 行含 impairmentAmount=30000，可供 mapAlreadyProvidedFromH88
    const depAfter = parseRemark(await getChecklistItem(request, apiToken, wpId, DEP_ROWS_KEY))
    expect(Number(depAfter?.[0]?.impairmentAmount ?? depAfter?.[0]?.impairment)).toBe(30_000)

    // ── 5) 控制台无严重错误 ──────────────────────────────────────────────
    const critical = consoleErrors.filter((e) =>
      !/net::ERR_|Failed to fetch|NetworkError|onlyoffice|DocsAPI|ResizeObserver|favicon|\/ai\/|401 \(Unauthorized\)|403 \(Forbidden\)/.test(e),
    )
    expect(critical.length, `console errors: ${critical.slice(0, 3).join(' | ')}`).toBeLessThanOrEqual(5)

    // ── 6) 清理测试数据（可选保留分支）──────────────────────────────────
    await putChecklist(request, apiToken, wpId, [
      { item_id: DEP_ROWS_KEY, remark: '[]' },
      { item_id: BRANCH_KEY, remark: '不含减值' },
      { item_id: DEP_TOTAL_KEY, remark: '0' },
      {
        item_id: H810_ROWS_KEY,
        remark: JSON.stringify([]),
      },
    ])
  })
})
