/**
 * H8-2 明细表 Round-Trip 联调
 *
 * 覆盖：
 * 1. API 写入 H8-2-rows（原值三项增 + 折旧计提 + CAS21）→ GET 回读
 * 2. 打开 UI → H8-2：区段切换、审定/净值公式可见
 * 3. 写入 H8-1 合计 → 勾稽一致 tag
 * 4. 刷新后数据仍在
 * 5. 导入导出下拉可见
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H82-RT-${Date.now()}`
const CONTRACT = `ROU-${MARKER.slice(-8)}`

const H82_ROWS_KEY = 'H8-2-rows'
const H81_COST_TOTAL = 'H8-1-cost-audited-total'
const H81_DEP_TOTAL = 'H8-1-dep-audited-total'
const H81_IMPAIR_TOTAL = 'H8-1-impair-audited-total'
const H81_NET_TOTAL = 'H8-1-net-audited'

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
  items: Array<{ item_id: string; remark: string | null }>,
) {
  const resp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: authHeaders(token),
    data: {
      project_id: PROJECT_ID,
      items: items.map((it) => ({
        item_id: it.item_id,
        conclusion: null,
        remark: it.remark,
      })),
    },
  })
  expect(resp.ok(), `PUT checklist 失败 status=${resp.status()}`).toBeTruthy()
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

/** 原值 100000+20000 租入+5000 重估 − 1000 其他减 = 124000；折旧计提 12000 */
function seedH82Row() {
  return {
    rowId: `row-${MARKER}`,
    category: '房屋及建筑物',
    contractNo: CONTRACT,
    assetName: `仓库-${MARKER}`,
    assetNo: 'A-001',
    lessor: '出租方甲',
    startDate: '2024-01-01',
    endDate: '2028-12-31',
    leaseTermMonths: 60,
    h9InitialAmount: 100_000,
    directCost: 2_000,
    incentive: 1_000,
    costBeginUnadj: 100_000,
    costIncLease: 20_000,
    costIncReval: 5_000,
    costIncOther: 0,
    costDecSublease: 0,
    costDecDisposal: 0,
    costDecOther: 1_000,
    depBeginUnadj: 10_000,
    depProvUnadj: 12_000,
    impairBeginUnadj: 0,
    remark: `E2E ${MARKER}`,
  }
}

test.describe('H8-2 明细表 Round-Trip', () => {
  test('API写入→UI四区段→勾稽H8-1→刷新回显→导入导出入口', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H8', PROJECT_ID)
    test.skip(!wpResult.exists, 'H8 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const seed = seedH82Row()
    // 预期公式：原值期末=100000+20000+5000-1000=124000；折旧期末=10000+12000=22000；净值=102000
    const costEnd = 124_000
    const depEnd = 22_000
    const netEnd = 102_000

    await putChecklist(request, apiToken, wpId, [
      { item_id: H82_ROWS_KEY, remark: JSON.stringify([seed]) },
      { item_id: H81_COST_TOTAL, remark: String(costEnd) },
      { item_id: H81_DEP_TOTAL, remark: String(depEnd) },
      { item_id: H81_IMPAIR_TOTAL, remark: '0' },
      { item_id: H81_NET_TOTAL, remark: String(netEnd) },
    ])

    const got = await getChecklistItem(request, apiToken, wpId, H82_ROWS_KEY)
    const rows = parseRemark(got)
    expect(Array.isArray(rows)).toBeTruthy()
    expect(rows[0]?.contractNo).toBe(CONTRACT)
    expect(Number(rows[0]?.costIncLease)).toBe(20_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'H8-2')
    await page.waitForTimeout(3_000)

    const root = page.locator('.h8-tab-detail')
    await expect(root).toBeVisible({ timeout: 20_000 })

    // 导入导出入口
    await expect(root.getByRole('button', { name: /导入导出/ })).toBeVisible()

    // 合同号回显（排除类别 el-select 的 combobox）
    const contractInput = root.locator('.el-table__body input:not([role="combobox"])').first()
    await expect(contractInput).toHaveValue(CONTRACT, { timeout: 15_000 })

    // 勾稽一致（H8-1 合计已对齐）
    await expect(root.getByText(/与 H8-1 勾稽一致/)).toBeVisible({ timeout: 10_000 })

    // 切到原值区段，看本期租入/审定
    const costSeg = root.locator('.el-segmented__item').filter({ hasText: /原值/ })
    if (await costSeg.count()) {
      await costSeg.first().click()
      await page.waitForTimeout(800)
    }
    const costBody = ((await root.textContent()) || '').replace(/,/g, '')
    // 审定增加=租入20000+重估5000→25000；期末124000（input 内数字未必进 textContent）
    expect(costBody).toMatch(/124000/)
    expect(costBody).toMatch(/100000/)

    // 切到累计折旧
    const depSeg = root.locator('.el-segmented__item').filter({ hasText: /累计折旧/ })
    if (await depSeg.count()) {
      await depSeg.first().click()
      await page.waitForTimeout(800)
    }
    const depBody = ((await root.textContent()) || '').replace(/,/g, '')
    expect(depBody).toMatch(/12000|22000/)

    // 切到减值与净值
    const netSeg = root.locator('.el-segmented__item').filter({ hasText: /减值/ })
    if (await netSeg.count()) {
      await netSeg.first().click()
      await page.waitForTimeout(800)
    }
    const netBody = ((await root.textContent()) || '').replace(/,/g, '')
    expect(netBody).toMatch(/102000/)
    // 刷新回显
    await page.reload()
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'H8-2')
    await page.waitForTimeout(3_000)
    const root2 = page.locator('.h8-tab-detail')
    await expect(root2).toBeVisible({ timeout: 20_000 })
    await expect(
      root2.locator('.el-table__body input:not([role="combobox"])').first(),
    ).toHaveValue(CONTRACT, { timeout: 15_000 })

    // 清理本轮种子，避免污染后续
    await putChecklist(request, apiToken, wpId, [
      { item_id: H82_ROWS_KEY, remark: '[]' },
    ])
  })
})
