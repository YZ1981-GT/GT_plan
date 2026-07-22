/**
 * I1 上市披露 ← I1-2 / I1-12 取数 Round-Trip
 *
 * 1. API 写入 I1-2-rows + I1-12-rows + I1-adj-audited-*
 * 2. 打开「附注上市」→「从 I1-2/检查表取数」
 * 3. 可见软件原值 / 减值说明草稿
 * 4. GET 确认 I1-listed-movement / note-impairment 落库
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `I1DISC-${Date.now()}`

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

test.describe('I1 披露 ← I1-2/I1-12 取数', () => {
  test('种子明细+减值→附注上市带入→落库', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'I1', PROJECT_ID)
    test.skip(!wpResult.exists, 'I1 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const detail = [
      {
        rowId: `d-${MARKER}`,
        name: `ERP软件-${MARKER}`,
        category: '软件',
        auditedCostBegin: 80000,
        costBegin: 80000,
        costIncrease: 20000,
        costIncreaseMethod: '购置',
        costDecrease: 0,
        auditedCostEnd: 100000,
        costEnd: 100000,
        accAmortBegin: 10000,
        amortProvision: 5000,
        impairmentBegin: 0,
        impairmentProvision: 0,
      },
    ]
    const i112 = [
      {
        rowId: `imp-${MARKER}`,
        name: `ERP软件-${MARKER}`,
        needTest: 'Y',
        hasIndication: 'Y',
        alreadyProvided: 0,
        impairmentAmount: 3000,
        supplement: 3000,
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'I1-2-rows', remark: JSON.stringify(detail) },
      { item_id: 'I1-12-rows', remark: JSON.stringify(i112) },
      { item_id: 'I1-adj-audited-cost', remark: '100000' },
      { item_id: 'I1-adj-audited-amort', remark: '15000' },
      { item_id: 'I1-adj-audited-impairment', remark: '0' },
      { item_id: 'I1-listed-movement', remark: '{}' },
      { item_id: 'I1-listed-note-impairment', remark: '' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

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

    const root = page.locator('.i1-disc-listed')
    await expect(root).toBeVisible({ timeout: 20_000 })
    const pullBtn = root.getByRole('button', { name: /从 I1-2\/检查表取数/ })
    await expect(pullBtn).toBeVisible({ timeout: 10_000 })
    await pullBtn.click()
    await page.waitForTimeout(2_500)

    await expect(page.getByText(/带入|取数|I1-2/).first()).toBeVisible({ timeout: 8_000 })

    const bodyText = ((await root.textContent()) || '').replace(/,/g, '')
    expect(bodyText).toMatch(/80000|100000/)

    let note = ''
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(1_000)
      const noteItem = await getChecklistItem(request, apiToken, wpId, 'I1-listed-note-impairment')
      note = String(noteItem?.remark ?? '')
      if (note.includes('I1-12') || note.includes('补提')) break
    }
    expect(note).toMatch(/I1-12|补提|减值/)

    const movItem = await getChecklistItem(request, apiToken, wpId, 'I1-listed-movement')
    const movRaw = movItem?.remark ?? '{}'
    expect(String(movRaw)).toMatch(/software|80000|cost_begin/)

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'I1-2-rows', remark: '[]' },
      { item_id: 'I1-12-rows', remark: '[]' },
      { item_id: 'I1-listed-movement', remark: '{}' },
      { item_id: 'I1-listed-note-impairment', remark: '' },
    ])
  })
})
