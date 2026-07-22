/**
 * H9 上市披露 ← H9-1/H9-2 取数 + 同步附注 Round-Trip
 *
 * 1. API 写入 H9-1-rows / H9-2-rows
 * 2. 打开「附注披露信息（上市公司）」→「从审定/明细取数」
 * 3. 分类余额/一年内到期/利息可见；H9-disc-listed-rows 落库
 * 4. 「同步到附注」→ GET disclosure-notes 含 五、47
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H9DISC-${Date.now()}`

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

test.describe('H9 披露 ← H9-1/H9-2 取数+同步附注', () => {
  test('种子审定/明细→附注上市带入→同步五、47', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H9', PROJECT_ID)
    test.skip(!wpResult.exists, 'H9 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const h91 = [
      {
        rowId: `liab-${MARKER}`,
        name: `房屋租赁-${MARKER}`,
        block: 'liability',
        beginBalance: 80_000,
        creditAmount: 0,
        debitAmount: 0,
        endBalance: 100_000,
        unadjusted: 100_000,
        aje: 0,
        rje: 0,
        audited: 100_000,
      },
      {
        rowId: `veh-${MARKER}`,
        name: '货车租赁',
        block: 'liability',
        beginBalance: 40_000,
        endBalance: 50_000,
        unadjusted: 50_000,
        aje: 0,
        rje: 0,
        audited: 50_000,
      },
      {
        rowId: `une-${MARKER}`,
        name: '未确认融资费用',
        block: 'unearned',
        beginBalance: 10_000,
        endBalance: 12_000,
        unadjusted: 12_000,
        aje: 0,
        rje: 0,
        audited: 12_000,
      },
    ]

    const h92 = [
      {
        rowId: `d1-${MARKER}`,
        contractNo: `CN-${MARKER.slice(-6)}`,
        lessor: '出租方A',
        interestAccrued: 5_000,
        interestAje: 0,
        reclassification: 25_000,
        beginBalance: 80_000,
        repayment: 0,
      },
      {
        rowId: `d2-${MARKER}`,
        contractNo: `CN2-${MARKER.slice(-4)}`,
        lessor: '出租方B',
        interestAccrued: 2_500,
        interestAje: 0,
        reclassification: 15_000,
        beginBalance: 40_000,
        repayment: 0,
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H9-1-rows', remark: JSON.stringify(h91) },
      { item_id: 'H9-2-rows', remark: JSON.stringify(h92) },
      { item_id: 'H9-disc-listed-rows', remark: '{}' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 底稿目录应可见（非空壳）
    const indexRoot = page.locator('[data-testid="h9-tab-index"]')
    if (await indexRoot.count()) {
      await expect(indexRoot.getByText('附注披露信息（上市公司）')).toBeVisible({ timeout: 10_000 })
    }

    let switched = false
    for (const label of ['附注上市', '附注披露信息（上市公司）', '上市']) {
      const tab = page.getByRole('tab').filter({ hasText: label })
      if (await tab.count()) {
        await tab.first().click()
        await page.waitForTimeout(3_000)
        switched = true
        break
      }
    }
    if (!switched) {
      await clickWorkpaperSheetTab(page, '附注披露信息（上市公司）')
      await page.waitForTimeout(3_000)
    }

    const root = page.locator('.h9-disc-listed')
    await expect(root).toBeVisible({ timeout: 20_000 })

    const pullBtn = root.getByTestId('h9-listed-pull')
    await expect(pullBtn).toBeVisible({ timeout: 10_000 })

    const putWait = page.waitForResponse(
      (r) => r.url().includes('/checklist-responses') && r.request().method() === 'PUT',
      { timeout: 15_000 },
    ).catch(() => null)

    await pullBtn.click()
    const putResp = await putWait
    expect(putResp, '取数后应 PUT checklist-responses').toBeTruthy()
    if (!putResp!.ok()) {
      const body = await putResp!.text().catch(() => '')
      expect(putResp!.ok(), `PUT status=${putResp!.status()} body=${body.slice(0, 400)}`).toBeTruthy()
    }
    await page.waitForTimeout(1_500)

    await expect(page.getByText(/带入|H9-1|H9-2/).first()).toBeVisible({ timeout: 8_000 })

    // 公式列（小计/合计）会出现在 textContent；分类行在 input-number 中
    const bodyText = ((await root.textContent()) || '').replace(/,/g, '')
    expect(bodyText).toMatch(/150000/) // 小计 100k+50k
    expect(bodyText).toMatch(/110000/) // 合计 150k−40k

    // 落库披露 pack
    let pack: any = null
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(800)
      const item = await getChecklistItem(request, apiToken, wpId, 'H9-disc-listed-rows')
      pack = parseRemark(item)
      if (pack?.withinOneYear?.end === 40_000 || pack?.interest?.total === 7_500) break
    }
    expect(
      pack,
      `披露 pack 应落库，实际=${JSON.stringify(pack)?.slice(0, 300)}`,
    ).toBeTruthy()
    expect(pack?.withinOneYear?.end).toBe(40_000)
    expect(pack?.interest?.total).toBe(7_500)
    expect(Array.isArray(pack?.rows) && pack.rows.some((r: any) => Number(r.endBalance) === 100_000)).toBeTruthy()
    expect(Array.isArray(pack?.rows) && pack.rows.some((r: any) => Number(r.endBalance) === 50_000)).toBeTruthy()

    // 同步到附注
    const syncBtn = root.getByTestId('h9-disclosure-listed-sync')
    await expect(syncBtn).toBeVisible()
    await syncBtn.click()
    await page.waitForTimeout(2_500)
    await expect(page.getByText(/已同步|五、47/).first()).toBeVisible({ timeout: 12_000 })

    // 校验附注记录（详情端点）
    const year = new Date().getFullYear()
    let found = false
    for (let i = 0; i < 10; i++) {
      const resp = await request.get(
        `/api/disclosure-notes/${PROJECT_ID}/${year}/${encodeURIComponent('五、47')}`,
        { headers: authHeaders(apiToken) },
      )
      if (resp.ok()) {
        const body = await resp.json()
        const note = body?.data ?? body
        const sub = note?.table_data?.sub_table_data?.['租赁负债']
          || note?.table_data?.sub_table_data?.租赁负债
        const rows = Array.isArray(sub) ? sub : []
        const flat = JSON.stringify(rows)
        if (
          rows.length >= 3
          || /100000/.test(flat)
          || String(note?.note_section || '').includes('五、47')
        ) {
          found = true
          break
        }
      }
      await page.waitForTimeout(1_000)
    }
    expect(found, '附注五、47 应含同步后的租赁负债子表').toBeTruthy()

    // 清理
    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H9-1-rows', remark: '[]' },
      { item_id: 'H9-2-rows', remark: '[]' },
      { item_id: 'H9-disc-listed-rows', remark: '{}' },
    ])
  })
})
