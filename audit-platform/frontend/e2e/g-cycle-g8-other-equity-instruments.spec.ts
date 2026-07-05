/**
 * g-cycle-g8-other-equity-instruments.spec.ts — G8 其他权益工具投资 E2E 冒烟
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
const COMPONENT_TYPE = 'g8-other-equity-instruments'

type SmokeCase = { wpCode: string; bodyHint: RegExp; testId?: string }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G8A', bodyHint: /程序|其他权益|1503/ },
  { wpCode: 'G8-1', bodyHint: /审定|变动率|1503/, testId: 'g8-adjudication' },
  { wpCode: 'G8-2', bodyHint: /明细|OCI|公允价值/, testId: 'g8-detail-table' },
  { wpCode: 'G8-3', bodyHint: /调整|借贷|AJE/, testId: 'g8-adjustment' },
  { wpCode: 'G8-4', bodyHint: /公允价值|Level|估值/, testId: 'g8-fv-test' },
  { wpCode: 'G8-5', bodyHint: /适当性|CAS22|指定/, testId: 'g8-designation-check' },
  { wpCode: 'G8-6', bodyHint: /凭证|核对|抽凭/, testId: 'g8-voucher-check' },
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

test.describe('G8 其他权益工具投资 — render-config', () => {
  test('G8 bundle 含 g8-other-equity-instruments componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G8 其他权益工具投资 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
      test.skip(!wpResult.exists, 'G8 底稿不存在')

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

test.describe('G8 导入 round-trip（API）', () => {
  for (const sheet of ['G8-2', 'G8-3', 'G8-4', 'G8-6'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
      test.skip(!wpResult.exists, 'G8 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g8/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `g8-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/g8/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `g8-${sheet}.xlsx`,
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

test.describe('G8 AI 端点注册', () => {
  for (const section of [
    'adjudication-analysis',
    'fair-value-conclusion',
    'designation-conclusion',
    'voucher-conclusion',
    'disclosure-section',
  ] as const) {
    test(`POST /g8/ai/${section} 路由存在`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
      test.skip(!wpResult.exists, 'G8 底稿不存在')

      const resp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g8/ai/${section}`,
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

test.describe('G8 G8-2/G8-4 tabs + G8-1 审定表', () => {
  test('G8-2 区段 Tab 切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G8-2')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g8-detail-table"]')).toBeVisible()
    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=公允价值+OCI').click()
      await page.waitForTimeout(500)
    }
  })

  test('G8-4 估值详情 Tab', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G8-4')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g8-fv-test"]')).toBeVisible()
    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=估值详情').click()
      await page.waitForTimeout(500)
    }
  })

  test('G8-1 审定表可见（10行无虚拟滚动）', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G8-1')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g8-adjudication"]')).toBeVisible({ timeout: 8_000 })
    await expect(page.locator('[data-testid="g8-validate-btn"]')).toBeVisible()
    await expect(page.locator('[data-testid="g8-fine-checks"]')).toBeVisible()
    await expect(page.locator('[data-testid="g9-adj-virtual-toolbar"]')).toHaveCount(0)
  })

  test('G8A 截止测试面板可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G8A')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g-cycle-cutoff-panel"]')).toBeVisible({ timeout: 8_000 })
  })

  test('G8-5 适当性检查问卷可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G8-5')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g8-designation-check"]')).toBeVisible({ timeout: 8_000 })
  })

  test('附注上市 schema 行标签', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, '附注上市')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g8-disclosure-listed"]')).toBeVisible()
    await expect(page.getByText('权益工具投资（FVOCI）')).toBeVisible()
  })
})

test.describe('G8 validate-formulas API', () => {
  test('POST /g8/validate-formulas 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g8/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [],
          detail_rows: [],
          fair_value_rows: [],
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

  test('POST /g8/validate-formulas 检出不平衡', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g8/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [{
            rowKey: 'test',
            openingUnadjusted: 100,
            openingAdjustment: 10,
            openingAdjusted: 50,
            closingUnadjusted: 200,
            closingAdjustment: 0,
            closingAdjusted: 0,
          }],
          detail_rows: [],
          fair_value_rows: [],
          adjustment_debits: [100],
          adjustment_credits: [50],
        },
      },
    )
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    const data = body.data ?? body
    expect(data.ok).toBe(false)
    expect(data.errors.length).toBeGreaterThan(0)
  })
})

test.describe('G8 contract-ocr 端点', () => {
  test('POST /g8/contract-ocr 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G8', PROJECT_ID)
    test.skip(!wpResult.exists, 'G8 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g8/contract-ocr`,
      {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: {
            name: 'empty.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('test'),
          },
        },
      },
    )
    expect(resp.status()).not.toBe(404)
  })
})
