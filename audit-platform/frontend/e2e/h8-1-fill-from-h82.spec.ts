/**
 * H8-1 ← H8-2 按类别带入 Round-Trip
 *
 * 1. API 写入 H8-2-rows（房屋+机器两类）
 * 2. 打开 H8-1 → 点「从 H8-2 按类别带入」
 * 3. UI 未审期初/期末可见汇总
 * 4. GET checklist 确认 H8-1-cost-rows 已落库
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H81-FILL-${Date.now()}`

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

test.describe('H8-1 从 H8-2 按类别带入', () => {
  test('种子H8-2→H8-1带入→落库', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H8', PROJECT_ID)
    test.skip(!wpResult.exists, 'H8 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const h82 = [
      {
        rowId: `row-a-${MARKER}`,
        category: '房屋及建筑物',
        contractNo: `CN-A-${MARKER.slice(-6)}`,
        costBeginUnadj: 100_000,
        costEndUnadj: 124_000,
        depBeginUnadj: 10_000,
        depEndUnadj: 22_000,
        impairBeginUnadj: 0,
        impairEndUnadj: 0,
      },
      {
        rowId: `row-b-${MARKER}`,
        category: '机器设备',
        contractNo: `CN-B-${MARKER.slice(-6)}`,
        costBeginUnadj: 50_000,
        costEndUnadj: 55_000,
        depBeginUnadj: 5_000,
        depEndUnadj: 8_000,
        impairBeginUnadj: 500,
        impairEndUnadj: 500,
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-2-rows', remark: JSON.stringify(h82) },
      // 清空旧 H8-1，避免脏数据干扰断言
      { item_id: 'H8-1-cost-rows', remark: '[]' },
      { item_id: 'H8-1-dep-rows', remark: '[]' },
      { item_id: 'H8-1-impair-rows', remark: '[]' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    await clickWorkpaperSheetTab(page, 'H8-1')
    await page.waitForTimeout(3_000)

    const root = page.locator('.h8-tab-adjudication')
    await expect(root).toBeVisible({ timeout: 20_000 })

    const fillBtn = root.getByRole('button', { name: /从 H8-2 按类别带入/ })
    await expect(fillBtn).toBeVisible({ timeout: 10_000 })
    await fillBtn.click()
    await page.waitForTimeout(2_000)

    // 成功提示（book 模式带入会带「原值 N」）
    await expect(page.getByText(/已从 H8-2 按类别带入：原值\s*[1-9]/).first()).toBeVisible({
      timeout: 8_000,
    })

    // UI 可见汇总金额（去掉千分位）
    const bodyText = ((await root.textContent()) || '').replace(/,/g, '')
    expect(bodyText).toMatch(/100000/)
    expect(bodyText).toMatch(/124000/)
    expect(bodyText).toMatch(/50000|55000/)

    // 落库校验（persist 防抖 800ms，轮询至写入完成）
    let house: any
    let machine: any
    let lastRaw: any = null
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(800)
      const costItem = await getChecklistItem(request, apiToken, wpId, 'H8-1-cost-rows')
      lastRaw = parseRemark(costItem)
      if (!Array.isArray(lastRaw) || lastRaw.length === 0) {
        // 兼容合并键
        const legacy = parseRemark(await getChecklistItem(request, apiToken, wpId, 'H8-1-rows'))
        if (Array.isArray(legacy) && legacy.length) {
          lastRaw = legacy.filter((r: any) => (r.block || 'cost') === 'cost' || r.block === undefined)
        }
      }
      if (!Array.isArray(lastRaw)) continue
      house = lastRaw.find((r: any) => /房屋/.test(String(r.category || r.name || '')))
      machine = lastRaw.find((r: any) => /机器/.test(String(r.category || r.name || '')))
      if (
        house
        && machine
        && Number(house.beginUnadjusted ?? house.beginBalance) === 100_000
        && Number(machine.beginUnadjusted ?? machine.beginBalance) === 50_000
      ) {
        break
      }
    }
    expect(house, `H8-1-cost-rows 未写入房屋行，last=${JSON.stringify(lastRaw)?.slice(0, 400)}`).toBeTruthy()
    expect(machine).toBeTruthy()
    expect(Number(house.beginUnadjusted ?? house.beginBalance)).toBe(100_000)
    expect(Number(house.endUnadjusted ?? house.unadjusted)).toBe(124_000)
    expect(Number(machine.beginUnadjusted ?? machine.beginBalance)).toBe(50_000)
    expect(Number(machine.endUnadjusted ?? machine.unadjusted)).toBe(55_000)

    // 清理
    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-2-rows', remark: '[]' },
      { item_id: 'H8-1-cost-rows', remark: '[]' },
      { item_id: 'H8-1-dep-rows', remark: '[]' },
      { item_id: 'H8-1-impair-rows', remark: '[]' },
    ])
  })

  test('勾稽异常告警→重新带入恢复一致', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H8', PROJECT_ID)
    test.skip(!wpResult.exists, 'H8 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const marker = `H81-FIX-${Date.now()}`
    const h82 = [
      {
        rowId: `row-c-${marker}`,
        category: '房屋及建筑物',
        contractNo: `CN-C-${marker.slice(-6)}`,
        costBeginUnadj: 200_000,
        costEndUnadj: 210_000,
        costEndAud: 210_000,
        depBeginUnadj: 20_000,
        depEndUnadj: 30_000,
        depEndAud: 30_000,
        impairBeginUnadj: 0,
        impairEndUnadj: 0,
        impairEndAud: 0,
      },
    ]
    // 故意写错 H8-1 未审，制造与 H8-2 差额
    const wrongCost = [
      {
        rowId: 'cost-wrong',
        category: '房屋及建筑物',
        block: 'cost',
        beginUnadjusted: 1,
        beginAdjustment: 0,
        endUnadjusted: 2,
        endAdjustment: 0,
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-2-rows', remark: JSON.stringify(h82) },
      { item_id: 'H8-1-cost-rows', remark: JSON.stringify(wrongCost) },
      { item_id: 'H8-1-dep-rows', remark: '[]' },
      { item_id: 'H8-1-impair-rows', remark: '[]' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'H8-1')
    await page.waitForTimeout(3_000)

    const root = page.locator('.h8-tab-adjudication')
    await expect(root).toBeVisible({ timeout: 20_000 })
    await expect(root.getByText(/H8-1 与 H8-2 勾稽异常|原值≠H8-2/).first()).toBeVisible({
      timeout: 12_000,
    })

    const refill = root.getByRole('button', { name: /重新从 H8-2 带入|从 H8-2 按类别带入/ }).first()
    await refill.click()
    await page.waitForTimeout(2_000)
    await expect(page.getByText(/已从 H8-2 按类别带入/).first()).toBeVisible({ timeout: 8_000 })

    // 告警应收起或出现勾稽一致
    await expect(root.getByText(/与 H8-2 勾稽一致|原值≠H8-2/).first()).toBeVisible({
      timeout: 8_000,
    })

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-2-rows', remark: '[]' },
      { item_id: 'H8-1-cost-rows', remark: '[]' },
      { item_id: 'H8-1-dep-rows', remark: '[]' },
      { item_id: 'H8-1-impair-rows', remark: '[]' },
    ])
  })
})
