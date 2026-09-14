/**
 * I2 上市披露 ← I2-2 / I2-6 / I2-7 取数 Round-Trip
 *
 * 1. API 写入 I2-2-rows + I2-6-rows + I2-7-rows
 * 2. 打开「附注上市」→「从底稿取数」
 * 3. 可见课题滚动 / 资本化时点
 * 4. GET 确认 I2-disc-listed-movement 落库
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `I2DISC-${Date.now()}`

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

test.describe('I2 披露 ← I2-2/I2-6/I2-7 取数', () => {
  test('种子明细+资本化时点→附注上市带入→落库', async ({ page, request }) => {
    test.setTimeout(180_000)

    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wpResult = await findWorkpaper(request, apiToken, 'I2', PROJECT_ID)
    test.skip(!wpResult.exists, 'I2 底稿不存在于测试项目')
    const wpId = wpResult.wpId!

    const projectName = `课题-${MARKER}`
    const detail = [
      {
        rowId: `d-${MARKER}`,
        projectName,
        capBeginAmount: 10000,
        capIncrease: 5000,
        transferToI1: 2000,
        auditedEnd: 13000,
        unadjOpening: 10000,
        unadjIncrease: 5000,
        unadjDecToIA: 2000,
        auditedEnding: 13000,
      },
    ]
    const i26 = [
      {
        rowId: `cap-${MARKER}`,
        projectName,
        capStartDate: '2024-03-01',
        capBasis: `五条件-${MARKER}`,
        progress: '60%',
      },
    ]
    const i27 = [
      {
        rowId: `p-${MARKER}`,
        projectName,
        increase: {
          material: 3000,
          labor: 1500,
          depreciation: 500,
          energy: 0,
          outsource: 0,
          other: 0,
          capitalized: 5000,
          expensed: 0,
        },
      },
    ]

    await putChecklist(request, apiToken, wpId, [
      { item_id: 'I2-2-rows', remark: JSON.stringify(detail) },
      { item_id: 'I2-6-rows', remark: JSON.stringify(i26) },
      { item_id: 'I2-7-rows', remark: JSON.stringify(i27) },
      { item_id: 'I2-disc-listed-movement', remark: '[]' },
      { item_id: 'I2-disc-listed-nature', remark: '[]' },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(4_000)

    let switched = false
    for (const label of ['附注上市', '附注披露信息（上市公司）', '上市公司', '附注披露']) {
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

    const root = page.locator('[data-testid="i2-disclosure-listed"]')
    await expect(root).toBeVisible({ timeout: 20_000 })

    await root.getByTestId('i2-listed-autofill').click()
    await page.waitForTimeout(1_500)

    await expect(root.getByText(projectName).first()).toBeVisible({ timeout: 10_000 })
    await expect(root.getByText('2024-03-01').first()).toBeVisible({ timeout: 10_000 })

    // 触发 persist（部分 UI 在 autofill 后自动保存；否则点保存）
    const saveBtn = root.getByRole('button', { name: /保存/ })
    if (await saveBtn.count()) {
      await saveBtn.first().click()
      await page.waitForTimeout(1_500)
    }

    const movItem = await getChecklistItem(request, apiToken, wpId, 'I2-disc-listed-movement')
    expect(movItem, '应落库 I2-disc-listed-movement').toBeTruthy()
    const raw = movItem?.remark ?? ''
    expect(String(raw)).toContain(MARKER)
  })
})
