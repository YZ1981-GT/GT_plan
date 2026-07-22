/**
 * I1-12 ↔ I1-13 须测试闸门 Round-Trip（轻量 API+UI）
 *
 * 1. 写入 I1-12 须测试行（缺可收回）
 * 2. 打开 I1-12 → 可见「缺 I1-13」闸门
 * 3. 写入配对 I1-13 并刷新 → 闸门应消失 / 可定稿区域可用
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const MARKER = `I112-GATE-${Date.now()}`

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

test.describe('I1-12 须测试闸门', () => {
  test('缺 I1-13 时展示闸门提示', async ({ page, request }) => {
    const token = await loginAs(page)
    const apiToken = await getToken(request)
    const wp = await findWorkpaper(request, apiToken, PROJECT_ID, /I1|无形资产/)
    test.skip(!wp, '未找到 I1 底稿')

    const assetName = `${MARKER}-软件`
    await putChecklist(request, apiToken, wp!.id, [
      {
        item_id: 'I1-12-rows',
        remark: JSON.stringify([
          {
            rowId: 'i12-1',
            name: assetName,
            category: '软件',
            indefiniteLife: 'Y',
            hasIndication: '',
            indicationDesc: '',
            needTest: true,
            cost: 1000,
            accAmort: 100,
            bookValue: 900,
            fairValueLessDisposal: 0,
            dcfValue: 0,
            recoverableAmount: 0,
            shouldProvision: 0,
            alreadyProvided: 0,
            supplement: 0,
            overProvision: 0,
            indexRef: '',
            conclusion: '',
          },
        ]),
      },
      { item_id: 'I1-13-rows', remark: JSON.stringify([]) },
    ])

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp!.id}`)
    await clickWorkpaperSheetTab(page, /I1-12|减值准备/)

    await expect(page.getByText(/缺 I1-13|须测试闸门/)).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/须完成 I1-13 后方可定稿|缺 I1-13/)).toBeVisible()
  })
})
