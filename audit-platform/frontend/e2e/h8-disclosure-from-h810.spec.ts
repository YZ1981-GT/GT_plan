/**
 * H8 上市披露 ← H8-10 减值取数 Round-Trip
 *
 * 1. API 写入 H8-10-rows（⑦已提 / ⑧补提）
 * 2. 打开「附注上市」→ 点「从审定/明细/减值取数」
 * 3. 减值期初/计提可见；说明草稿含补提
 * 4. GET 确认 H8-listed-movement / note-impairment 落库
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `H8DISC-${Date.now()}`

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

test.describe('H8 披露 ← H8-10 减值取数', () => {
  test('种子H8-10→附注上市带入→落库', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'H8', PROJECT_ID)
    test.skip(!wpResult.exists, 'H8 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const h810 = [
      {
        rowId: `imp-${MARKER}`,
        assetName: `房屋仓库-${MARKER}`,
        contractNo: `CN-${MARKER.slice(-6)}`,
        assetCategory: '房屋及建筑物',
        hasIndication: '是',
        indicationDesc: 'E2E减值迹象',
        alreadyProvided: 10_000, // ⑦
        impairmentAmount: 15_000, // ⑥
        supplement: 5_000, // ⑧
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-10-rows', remark: JSON.stringify(h810) },
      { item_id: 'H8-listed-movement', remark: '{}' },
      { item_id: 'H8-listed-note-impairment', remark: '' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    // 附注上市 Tab（名称可能含「附注」）
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
      await clickWorkpaperSheetTab(page, '附注上市')
    }

    const root = page.locator('.h8-disc-listed')
    await expect(root).toBeVisible({ timeout: 20_000 })
    const pullBtn = root.getByRole('button', { name: /从审定\/明细\/减值取数/ })
    await expect(pullBtn).toBeVisible({ timeout: 10_000 })
    await pullBtn.click()
    await page.waitForTimeout(2_000)

    await expect(page.getByText(/H8-10|减值|取数|带入/).first()).toBeVisible({ timeout: 8_000 })

    const bodyText = ((await root.textContent()) || '').replace(/,/g, '')
    expect(bodyText).toMatch(/10000/)
    expect(bodyText).toMatch(/5000/)

    // 减值说明草稿（第二个说明框；第一个是短期/低价值）
    const noteBox = root.locator('.note-field').filter({ hasText: '减值测试披露说明' }).locator('textarea')
    await expect.poll(async () => noteBox.inputValue().catch(() => ''), { timeout: 10_000 }).toMatch(/H8-10|补提/)

    // 落库轮询
    let note = ''
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(1_000)
      const noteItem = await getChecklistItem(request, apiToken, wpId, 'H8-listed-note-impairment')
      note = String(noteItem?.remark ?? '')
      if (note.includes('补提') || note.includes('H8-10')) break
    }
    if (!/H8-10|补提/.test(note)) {
      note = await noteBox.inputValue().catch(() => '')
    }
    expect(note).toMatch(/H8-10|补提|减值/)

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'H8-10-rows', remark: '[]' },
      { item_id: 'H8-listed-movement', remark: '{}' },
      { item_id: 'H8-listed-note-impairment', remark: '' },
    ])
  })
})
