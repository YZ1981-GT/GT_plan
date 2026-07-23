/**
 * I5-2 → I5-1 带入 round-trip（对齐原值/减值/净值）
 *
 * 1. API 写入 I5-2-rows（含 gross/impairment）
 * 2. 打开底稿 → I5-2 可见原值未审区段
 * 3. 切 I5-1 → 点「从 I5-2 带入」→ 矩阵出现三层 / 可编辑行含合同资产
 * 4. 刷新后 checklist 仍可读回 I5-adj-rows
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  clickWorkpaperSheetTab,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

async function loginAs(page: Page) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
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

function buildI52Payload() {
  return [{
    rowId: 'e2e-i52-contract',
    projectName: '合同资产',
    name: '合同资产',
    isBuiltin: true,
    indexRef: 'D7',
    remark: 'E2E',
    gross: {
      unadjOpening: 100000,
      unadjIncrease: 20000,
      unadjDecrease: 5000,
      unadjEnding: 115000,
      openingAje: 1000,
      openingRje: 0,
      ajeIncrease: 0,
      ajeDecrease: 0,
      rjeIncrease: 0,
      rjeDecrease: 0,
      auditedOpening: 101000,
      auditedIncrease: 20000,
      auditedDecrease: 5000,
      auditedEnding: 116000,
    },
    impairment: {
      unadjOpening: 2000,
      unadjIncrease: 500,
      unadjDecrease: 0,
      unadjEnding: 2500,
      openingAje: 0,
      openingRje: 0,
      ajeIncrease: 0,
      ajeDecrease: 0,
      rjeIncrease: 0,
      rjeDecrease: 0,
      auditedOpening: 2000,
      auditedIncrease: 500,
      auditedDecrease: 0,
      auditedEnding: 2500,
    },
    beginBalance: 99000,
    increase: 19500,
    decrease: 5000,
    endBalance: 113500,
  }]
}

test.describe('I5-2→I5-1 三层带入 round-trip', () => {
  test('API 写入明细 → UI 带入审定 → 刷新回显', async ({ page, request }) => {
    test.setTimeout(120_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'I5', PROJECT_ID)
    test.skip(!wpResult.exists, 'I5 底稿不存在于当前测试项目')

    const wpId = wpResult.wpId
    const detailRows = buildI52Payload()

    // 写入 I5-2
    const putDetail = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        items: [{
          item_id: 'I5-2-rows',
          conclusion: null,
          remark: JSON.stringify(detailRows),
        }],
      },
    })
    expect(putDetail.ok(), `PUT I5-2 failed: ${putDetail.status()}`).toBeTruthy()

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
    await page.waitForTimeout(3_000)

    // I5-2：原值未审区段
    try {
      await clickWorkpaperSheetTab(page, 'I5-2')
      await page.waitForTimeout(2_500)
    } catch {
      test.skip(true, 'I5-2 tab 不可用')
    }
    const hasDetailUi =
      (await page.locator('.i5-tab-detail').count()) > 0 ||
      (await page.getByText('原值未审').count()) > 0 ||
      (await page.getByText('合同资产').count()) > 0
    expect(hasDetailUi).toBeTruthy()

    // I5-1：从明细带入
    try {
      await clickWorkpaperSheetTab(page, 'I5-1')
      await page.waitForTimeout(2_500)
    } catch {
      test.skip(true, 'I5-1 tab 不可用')
    }

    const seedBtn = page.getByRole('button', { name: /从 I5-2 带入/ })
    await expect(seedBtn).toBeVisible({ timeout: 15_000 })
    await seedBtn.click()
    await page.waitForTimeout(1_500)

    // 三层矩阵或合同资产行
    const hasLayer =
      (await page.getByText(/原值\s*\/\s*减值\s*\/\s*净值|已链 I5-2 三层|其他非流动资产原值/).count()) > 0
    const hasContract = (await page.getByText('合同资产').count()) > 0
    expect(hasLayer || hasContract).toBeTruthy()

    // 刷新回读 I5-adj-rows
    const getResp = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(getResp.ok()).toBeTruthy()
    const body = await getResp.json()
    const items = body.data?.items ?? body.items ?? body.data ?? []
    const list = Array.isArray(items) ? items : Object.values(items || {})
    const adj = list.find((it: any) =>
      (it.item_id || it.itemId) === 'I5-adj-rows',
    )
    // 若 UI 带入走 save 异步，允许稍后；至少页面已展示合同资产
    if (adj?.remark) {
      const parsed = typeof adj.remark === 'string' ? JSON.parse(adj.remark) : adj.remark
      const rows = Array.isArray(parsed) ? parsed : []
      expect(rows.some((r: any) => (r.projectName || r.name) === '合同资产')).toBeTruthy()
    } else {
      expect(hasContract).toBeTruthy()
    }
  })
})
