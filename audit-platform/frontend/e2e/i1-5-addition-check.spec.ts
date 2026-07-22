/**
 * I1-5 增加检查 — 带入 / 检查比例 N/A / 分段列填写
 *
 * 1. API 写入 I1-2-rows（购置增加）+ 清空 I1-5
 * 2. 打开 I1-5 → 从 I1-2 带入 → 可见样本行
 * 3. 总体为 0 时检查比例显示 N/A
 * 4. 切换完整视图并填写购买列 / 关联方
 * 5. 生成证→账追查并落库
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `I15-P2-${Date.now()}`

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

test.describe('I1-5 增加检查 P2', () => {
  test('带入明细 + N/A + 分段列 + 证→账追查落库', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'I1', PROJECT_ID)
    test.skip(!wpResult.exists, 'I1 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const detailRows = [
      {
        rowId: `d-${MARKER}-1`,
        name: `${MARKER}-外购软件`,
        costIncrease: 120000,
        costIncreaseMethod: '购置',
        acquisitionDate: '2024-03-15',
      },
      {
        rowId: `d-${MARKER}-2`,
        name: `${MARKER}-零增加`,
        costIncrease: 0,
        costIncreaseMethod: '购置',
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'I1-2-rows', remark: JSON.stringify(detailRows) },
      { item_id: 'I1-5-rows', remark: JSON.stringify([]) },
      { item_id: 'I1-5-trace-rows', remark: JSON.stringify([]) },
      { item_id: 'I1-5-period-total', remark: JSON.stringify({ periodTotal: 0, manual: true }) },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(3_000)
    await clickWorkpaperSheetTab(page, 'I1-5')
    await page.waitForTimeout(2_500)

    const root = page.locator('.i1-tab-addition-check')
    await expect(root).toBeVisible({ timeout: 30_000 })

    // 总体为 0 → 检查比例 N/A
    await expect(root.getByText(/检查比例\s*N\/A/)).toBeVisible()

    await root.getByRole('button', { name: /从 I1-2 带入增加明细/ }).click()
    await page.waitForTimeout(1_500)
    await expect(root.getByText(`${MARKER}-外购软件`)).toBeVisible({ timeout: 15_000 })

    // 精简视图下购买列可见；切完整视图
    const fullView = root.getByText('完整视图')
    if (await fullView.isVisible()) {
      await fullView.click()
      await page.waitForTimeout(500)
    }

    // 写入已填购买/关联方字段后刷新，验证比例与追查
    await putChecklist(request, apiToken, wpId, [
      {
        item_id: 'I1-5-rows',
        remark: JSON.stringify([{
          rowId: `r-${MARKER}`,
          name: `${MARKER}-外购软件`,
          acquisitionMethod: '购买',
          entryAmount: 120000,
          entryDate: '2024-03-15',
          voucherNo: `PZ-${MARKER}`,
          counterparty: '关联供应商X',
          invoiceAmountExTax: 120000,
          inputVat: 15600,
          vatSplitOk: 'Y',
          purchaseContractComplete: 'Y',
          purchasePaymentApproved: 'Y',
          purchaseEntryCorrect: 'Y',
          isRelatedParty: 'Y',
          relatedPartyName: '关联供应商X',
          fundOccupationRisk: 'N',
          checkConclusion: '无异常',
        }]),
      },
      {
        item_id: 'I1-5-period-total',
        remark: JSON.stringify({ periodTotal: 500000, manual: true }),
      },
    ])

    await page.reload()
    await page.waitForTimeout(3_000)
    await clickWorkpaperSheetTab(page, 'I1-5')
    await page.waitForTimeout(2_500)

    await expect(root.getByText(`${MARKER}-外购软件`)).toBeVisible({ timeout: 20_000 })
    await expect(root.getByText(/24\.00%|24%/)).toBeVisible({ timeout: 10_000 })

    await root.getByRole('button', { name: /从账→证样本生成/ }).click()
    await page.waitForTimeout(1_500)
    await expect(root.locator('#i1-5-trace-section')).toContainText(`${MARKER}-外购软件`, { timeout: 10_000 })

    // 落库核对
    await page.waitForTimeout(1_000)
    const rowsItem = await getChecklistItem(request, apiToken, wpId, 'I1-5-rows')
    const rows = parseRemark(rowsItem)
    expect(Array.isArray(rows)).toBeTruthy()
    expect(rows.some((r: any) => r.name === `${MARKER}-外购软件` && r.isRelatedParty === 'Y')).toBeTruthy()

    const traceItem = await getChecklistItem(request, apiToken, wpId, 'I1-5-trace-rows')
    const traces = parseRemark(traceItem)
    expect(Array.isArray(traces)).toBeTruthy()
    expect(traces.some((t: any) => String(t.bookAssetName || '').includes(MARKER))).toBeTruthy()
  })
})
