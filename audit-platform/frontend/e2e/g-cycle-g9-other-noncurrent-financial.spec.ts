/**
 * g-cycle-g9-other-noncurrent-financial.spec.ts — G9 其他非流动金融资产 E2E 冒烟
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
const COMPONENT_TYPE = 'g9-other-noncurrent-financial'

type SmokeCase = { wpCode: string; bodyHint: RegExp; testId?: string }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G9A', bodyHint: /程序|其他非流动|1504/ },
  { wpCode: 'G9-1', bodyHint: /审定|变动率|1504/, testId: 'g9-adjudication' },
  { wpCode: 'G9-2', bodyHint: /明细|分类|公允价值/, testId: 'g9-detail-table' },
  { wpCode: 'G9-3', bodyHint: /调整|借贷|AJE/, testId: 'g9-adjustment' },
  { wpCode: 'G9-4', bodyHint: /公允价值|Level|估值/, testId: 'g9-fv-test' },
  { wpCode: 'G9-5', bodyHint: /第三层次|L3|购入/, testId: 'g9-l3-reconciliation' },
  { wpCode: 'G9-6', bodyHint: /凭证|核对|抽凭/, testId: 'g9-voucher-check' },
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

test.describe('G9 其他非流动金融资产 — render-config', () => {
  test('G9 bundle 含 g9-other-noncurrent-financial componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G9 其他非流动金融资产 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
      test.skip(!wpResult.exists, 'G9 底稿不存在')

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

test.describe('G9 导入 round-trip（API）', () => {
  for (const sheet of ['G9-2', 'G9-3', 'G9-4', 'G9-5', 'G9-6'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
      test.skip(!wpResult.exists, 'G9 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g9/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `g9-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/g9/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `g9-${sheet}.xlsx`,
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

test.describe('G9 AI 端点注册', () => {
  for (const section of [
    'adjudication-analysis',
    'fair-value-conclusion',
    'l3-reconciliation-conclusion',
    'voucher-conclusion',
    'disclosure-section',
  ] as const) {
    test(`POST /g9/ai/${section} 路由存在`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
      test.skip(!wpResult.exists, 'G9 底稿不存在')

      const resp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g9/ai/${section}`,
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

test.describe('G9 G9-2/G9-4 tabs + G9-1 校验', () => {
  test('G9-2 区段 Tab 切换', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G9-2')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g9-detail-table"]')).toBeVisible()
    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=期末+公允价值').click()
      await page.waitForTimeout(500)
    }
  })

  test('G9-4 估值详情 Tab', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G9-4')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g9-fv-test"]')).toBeVisible()
    const seg = page.locator('.el-segmented')
    if (await seg.count()) {
      await seg.locator('text=估值详情').click()
      await page.waitForTimeout(500)
    }
  })

  test('G9-1 虚拟滚动工具栏可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G9-1')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g9-adj-virtual-toolbar"]')).toBeVisible({ timeout: 8_000 })
    await expect(page.locator('[data-testid="g9-adj-virtual-table"]')).toBeVisible()
    await expect(page.locator('[data-testid="g9-validate-btn"]')).toBeVisible()
    await expect(page.locator('[data-testid="g9-fine-checks"]')).toBeVisible()
    await expect(page.locator('[data-testid="g9-publish-adj"]')).toBeVisible()
  })

  test('G9A 截止测试面板可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G9A')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g-cycle-cutoff-panel"]')).toBeVisible({ timeout: 8_000 })
  })

  test('G9-5 L3 调节表可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G9-5')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g9-l3-reconciliation"]')).toBeVisible({ timeout: 8_000 })
  })

  test('附注上市 schema 行标签', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, '附注上市')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="g9-disclosure-listed"]')).toBeVisible()
    await expect(page.getByText('债务工具投资')).toBeVisible()
    await expect(page.getByText('权益工具投资')).toBeVisible()
  })
})

test.describe('G9 validate-formulas API', () => {
  test('POST /g9/validate-formulas 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g9/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [],
          l3_rows: [],
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

  test('POST /g9/validate-formulas 检出不平衡', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g9/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [{
            rowKey: 'test',
            openingUnadjusted: 100,
            openingAJE: 0,
            openingRJE: 0,
            openingAdjusted: 50,
            closingUnadjusted: 0,
            closingAJE: 0,
            closingRJE: 0,
            closingAdjusted: 0,
          }],
          l3_rows: [],
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

test.describe('G9 contract-ocr 端点', () => {
  test('POST /g9/contract-ocr 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G9', PROJECT_ID)
    test.skip(!wpResult.exists, 'G9 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g9/contract-ocr`,
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
