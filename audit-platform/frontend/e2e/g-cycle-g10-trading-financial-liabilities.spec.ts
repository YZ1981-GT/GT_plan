/**
 * g-cycle-g10-trading-financial-liabilities.spec.ts — G10 交易性金融负债 E2E 冒烟
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import {
  TEST_PROJECT_ID,
  findWorkpaper,
  fetchRenderConfig,
  sheetComponentTypes,
  clickWorkpaperSheetTab,
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'g10-trading-financial-liabilities'

type SmokeCase = { wpCode: string; bodyHint: RegExp; testId?: string }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G10A', bodyHint: /程序|交易性金融负债|2101/ },
  { wpCode: 'G10-1', bodyHint: /审定|贷方|变动率/, testId: 'g10-adjudication' },
  { wpCode: 'G10-2', bodyHint: /明细|负债|公允价值/, testId: 'g10-detail-table' },
  { wpCode: 'G10-3', bodyHint: /调整|借贷|AJE/, testId: 'g10-adjustment' },
  { wpCode: 'G10-4', bodyHint: /分类|合规|CAS22/, testId: 'g10-classification-check' },
  { wpCode: 'G10-5', bodyHint: /公允价值|Level|估值/, testId: 'g10-fv-test' },
  { wpCode: 'G10-6', bodyHint: /第三层次|新增|终止/, testId: 'g10-l3-reconciliation' },
  { wpCode: 'G10-7', bodyHint: /凭证|核对|抽凭/, testId: 'g10-voucher-check' },
  { wpCode: 'G10-8', bodyHint: /衍生|五要素|合规/, testId: 'g10-derivative-check' },
]

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

test.describe('G10 交易性金融负债 — render-config', () => {
  test('G10 bundle 含 g10-trading-financial-liabilities componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
    test.skip(!wpResult.exists, 'G10 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G10 交易性金融负债 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
      test.skip(!wpResult.exists, 'G10 底稿不存在')

      const consoleErrors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          const text = msg.text()
          if (/\/ai\//.test(text) && /405/.test(text)) return
          if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
          if (/onlyoffice|DocsAPI/.test(text)) return
          consoleErrors.push(text)
        }
      })

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_500)

      const criticalErrors = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined/.test(e),
      )
      expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)

      await expectHtmlDualModeOrContent(page, c.bodyHint)
      if (c.testId) {
        await expect(page.locator(`[data-testid="${c.testId}"]`)).toBeVisible({ timeout: 8_000 })
      }
    })
  }
})

test.describe('G10 导入 round-trip（API）', () => {
  for (const sheet of ['G10-2', 'G10-3', 'G10-5', 'G10-6', 'G10-7'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
      test.skip(!wpResult.exists, 'G10 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g10/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `g10-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/g10/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `g10-${sheet}.xlsx`,
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              buffer: buf,
            },
          },
        },
      )
      expect(importResp.status()).toBe(200)
      const body = await importResp.json()
      const data = body.data ?? body
      expect(data.ok).toBe(true)
      fs.unlinkSync(tmpPath)
    })
  }
})

test.describe('G10 AI 端点注册', () => {
  for (const section of [
    'adjudication-analysis',
    'classification-conclusion',
    'fair-value-conclusion',
    'derivative-conclusion',
    'voucher-conclusion',
  ] as const) {
    test(`POST /g10/ai/${section} 路由存在`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
      test.skip(!wpResult.exists, 'G10 底稿不存在')

      const resp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g10/ai/${section}`,
        {
          headers: { Authorization: `Bearer ${token}` },
          data: { existingContent: '', rows: [] },
        },
      )
      expect([200, 500, 504]).toContain(resp.status())
      expect(resp.status()).not.toBe(404)
    })
  }
})

test.describe('G10 G10-5 tabs + G10-7 conclusion', () => {
  test('G10-5 区段 Tab 切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
    test.skip(!wpResult.exists, 'G10 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G10-5')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g10-fv-test"]')).toBeVisible()
    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=估值详情').click()
      await page.waitForTimeout(500)
    }
  })

  test('G10-7 结论区可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
    test.skip(!wpResult.exists, 'G10 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G10-7')
    await page.waitForTimeout(2_000)

    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=结论').click()
      await page.waitForTimeout(500)
    }
    await expect(page.locator('[data-testid="g10-voucher-conclusion"]')).toBeVisible({ timeout: 8_000 })
  })
})

test.describe('G10 validate-formulas API', () => {
  test('POST /g10/validate-formulas 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G10', PROJECT_ID)
    test.skip(!wpResult.exists, 'G10 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g10/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [],
          adjustment_debits: [],
          adjustment_credits: [],
        },
      },
    )
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    const data = body.data ?? body
    expect(data.ok).toBe(true)
  })
})
