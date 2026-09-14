/**
 * H10 上市披露 ← H10-1 带入 + 试运行明细 + 同步附注 Round-Trip
 *
 * 1. API 写入 H10-adj-rows / H10-1-adjudicated-amount
 * 2. 打开「附注披露信息（上市公司）」→「从审定表带入」
 * 3. 填试运行收入/成本 → 主表试运行行净额回写
 * 4. 「同步到附注」→ GET disclosure-notes 含 三、资产处置收益
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickDisclosureSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H10DISC-${Date.now()}`

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
  items: Array<{ item_id: string; remark?: string | null; conclusion?: string | null }>,
) {
  const resp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: authHeaders(token),
    data: {
      project_id: PROJECT_ID,
      items: items.map((it) => ({
        item_id: it.item_id,
        conclusion: it.conclusion ?? null,
        remark: it.remark ?? null,
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

test.describe('H10 披露 ← H10-1 带入+试运行+同步附注', () => {
  test('种子审定→附注上市带入→试运行回写→同步三、资产处置收益', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const adjStore = {
      fixed_asset_disposal: {
        currentUnadjusted: 100_000,
        currentAje: 0,
        currentRje: 0,
        priorUnadjusted: 40_000,
        priorAje: 0,
        priorRje: 0,
        reasonAnalysis: MARKER,
        indexRef: 'H10-2',
      },
      construction_disposal: {
        currentUnadjusted: 50_000,
        currentAje: 0,
        currentRje: 0,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    }

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H10-adj-rows', remark: JSON.stringify(adjStore) },
      { item_id: 'H10-1-adjudicated-amount', conclusion: '150000', remark: null },
      { item_id: 'H10-disclosure-listed', remark: '[]' },
      { item_id: 'H10-disclosure-listed-trial', remark: '[]' },
    ])

    // 确认种子落库
    const seeded = parseRemark(await getChecklistItem(request, apiToken, wpId, 'H10-adj-rows'))
    expect(seeded?.fixed_asset_disposal?.currentUnadjusted).toBe(100_000)
    expect(seeded?.construction_disposal?.currentUnadjusted).toBe(50_000)

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickDisclosureSheetTab(page, 'listed')
    await page.waitForTimeout(2_500)

    const root = page.locator('[data-testid="h10-disclosure-listed"]')
    await expect(root).toBeVisible({ timeout: 20_000 })
    await expect(root.getByText('试运行销售损益').first()).toBeVisible()
    await expect(page.locator('[data-testid="h10-disclosure-trial"]')).toBeVisible()

    const pullBtn = root.getByTestId('h10-disclosure-pull-adj')
    await expect(pullBtn).toBeVisible({ timeout: 10_000 })

    const putWait = page.waitForResponse(
      (r) => r.url().includes('/checklist-responses') && r.request().method() === 'PUT',
      { timeout: 15_000 },
    ).catch(() => null)

    await pullBtn.click()
    const putResp = await putWait
    expect(putResp, '带入后应 PUT checklist-responses').toBeTruthy()
    expect(putResp!.ok(), `PUT status=${putResp!.status()}`).toBeTruthy()
    await page.waitForTimeout(1_500)

    await expect(page.getByText(/带入|H10-1/).first()).toBeVisible({ timeout: 8_000 })

    // 审定数条可见（金额可能带千分位/小数）
    await expect(root.getByText(/已同步审定数/).first()).toBeVisible({ timeout: 8_000 })
    await expect(root.getByText(/150[,.]?000/).first()).toBeVisible({ timeout: 8_000 })

    // 落库披露主表（勿依赖 input-number 的 textContent）
    let rows: any[] | null = null
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(800)
      const item = await getChecklistItem(request, apiToken, wpId, 'H10-disclosure-listed')
      const parsed = parseRemark(item)
      if (
        Array.isArray(parsed)
        && parsed.some((r: any) => r.rowKey === 'fixed_asset_disposal' && Number(r.currentAmount) === 100_000)
        && parsed.some((r: any) => r.rowKey === 'construction_disposal' && Number(r.currentAmount) === 50_000)
      ) {
        rows = parsed
        break
      }
    }
    expect(
      rows,
      `披露主表应落库 FA=100000 CIP=50000，实际=${JSON.stringify(rows)?.slice(0, 400)}`,
    ).toBeTruthy()

    // 试运行：收入 30_000 − 成本 10_000 = 20_000 回写主表
    const trialRoot = page.locator('[data-testid="h10-disclosure-trial"]')
    const incomeInputs = trialRoot.locator('.el-input-number input')
    await expect(incomeInputs.first()).toBeVisible({ timeout: 8_000 })
    await incomeInputs.nth(0).fill('30000')
    await incomeInputs.nth(0).press('Tab')
    await page.waitForTimeout(500)
    await incomeInputs.nth(1).fill('10000')
    await incomeInputs.nth(1).press('Tab')
    await page.waitForTimeout(1_500)

    let trialOk = false
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(800)
      const item = await getChecklistItem(request, apiToken, wpId, 'H10-disclosure-listed')
      const parsed = parseRemark(item)
      if (Array.isArray(parsed) && parsed.some((r: any) => r.rowKey === 'trial_operation_sales' && Number(r.currentAmount) === 20_000)) {
        rows = parsed
        trialOk = true
        break
      }
    }
    expect(trialOk, '试运行净额 20000 应回写主表并落库').toBeTruthy()

    // 同步到附注
    const syncBtn = root.getByTestId('h10-disclosure-sync-notes')
    await expect(syncBtn).toBeVisible()
    await syncBtn.click()
    await page.waitForTimeout(2_500)
    await expect(page.getByText(/已同步|三、资产处置收益/).first()).toBeVisible({ timeout: 12_000 })

    const year = new Date().getFullYear()
    let found = false
    for (let i = 0; i < 10; i++) {
      const resp = await request.get(
        `/api/disclosure-notes/${PROJECT_ID}/${year}/${encodeURIComponent('三、资产处置收益')}`,
        { headers: authHeaders(apiToken) },
      )
      if (resp.ok()) {
        const body = await resp.json()
        const note = body?.data ?? body
        const flat = JSON.stringify(note?.table_data ?? note ?? {})
        if (
          /100000|固定资产|试运行|20000/.test(flat)
          || String(note?.note_section || '').includes('资产处置')
        ) {
          found = true
          break
        }
      }
      await page.waitForTimeout(1_000)
    }
    expect(found, '附注「三、资产处置收益」应含同步后的子表').toBeTruthy()

    // 清理
    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H10-adj-rows', remark: '{}' },
      { item_id: 'H10-1-adjudicated-amount', conclusion: '', remark: null },
      { item_id: 'H10-disclosure-listed', remark: '[]' },
      { item_id: 'H10-disclosure-listed-trial', remark: '[]' },
    ])
  })
})
