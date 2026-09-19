/**
 * g-cycle-g11-investment-income.spec.ts — G11 投资收益 E2E 冒烟
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
const COMPONENT_TYPE = 'g11-investment-income'

type SmokeCase = { wpCode: string; bodyHint: RegExp; testId?: string }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G11A', bodyHint: /程序|投资收益|6111/ },
  { wpCode: 'G11-1', bodyHint: /审定|投资收益|变动率/, testId: 'g11-adjudication' },
  { wpCode: 'G11-2', bodyHint: /明细|被投资单位|本期/, testId: 'g11-detail-table' },
  { wpCode: 'G11-3', bodyHint: /调整|借贷|账项调整|调整事项说明/, testId: 'g11-adjustment' },
  { wpCode: 'G11-4', bodyHint: /收益率|平均投资|期初/, testId: 'g11-return-rate-table' },
  { wpCode: 'G11-5', bodyHint: /凭证|核对|抽凭/ },
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

test.describe('G11 投资收益 — render-config', () => {
  test('G11 bundle 含 g11-investment-income componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G11 投资收益 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
      test.skip(!wpResult.exists, 'G11 底稿不存在')

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

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`, { waitUntil: 'domcontentloaded' })
      await page.locator('.gt-wp-renderer, .workpaper-editor, [data-component-type]').first().waitFor({ state: 'visible', timeout: 30_000 })
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

test.describe('G11 导入 round-trip（API）', () => {
  for (const sheet of ['G11-1', 'G11-2', 'G11-3', 'G11-4', 'G11-5'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
      test.skip(!wpResult.exists, 'G11 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g11/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `g11-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/g11/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `${sheet}_template.xlsx`,
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

test.describe('G11 深度 — 列结构与指引', () => {
  test('G11-2 含 13 列关键表头', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-2')
    await page.waitForTimeout(2_000)
    const table = page.locator('[data-testid="g11-detail-table"]')
    await expect(table).toBeVisible()
    for (const h of ['本期', '上期', '变动额', '变动率', '被投资单位']) {
      await expect(table.getByText(h, { exact: false }).first()).toBeVisible()
    }
  })

  test('G11-2 含 G7-14 带入入口', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-2')
    await page.waitForTimeout(2_000)
    await expect(page.getByRole('button', { name: '从 G7-14 带入' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'G7-14 差异→G11-3' })).toBeVisible()
    await expect(page.getByRole('button', { name: '从 TB/序时账预填' })).toBeVisible()
  })

  test('G11-3 含 Excel 对齐列与集中模块同步', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-3')
    await page.waitForTimeout(2_000)
    const panel = page.locator('[data-testid="g11-adjustment"]')
    await expect(panel).toBeVisible()
    const table = panel.locator('.el-table')
    await expect(table).toBeVisible()
    for (const h of ['调整事项说明', '类别', '回写行', '借方调整金额']) {
      await expect(table.getByRole('columnheader', { name: h })).toBeVisible()
    }
    await expect(panel.getByRole('button', { name: '从调整分录模块同步' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '确认调整' })).toBeVisible()
  })

  test('G11-4 期初/期末余额列可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-4')
    await page.waitForTimeout(2_000)
    const table = page.locator('[data-testid="g11-return-rate-table"]')
    await expect(table.getByText('期初余额').first()).toBeVisible()
    await expect(table.getByText('期末余额').first()).toBeVisible()
    await expect(table.getByText('平均投资').first()).toBeVisible()
  })

  test('G11-1 审计程序指引区可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-1')
    await page.waitForTimeout(2_000)
    await expect(page.getByText(/审计程序指引/)).toBeVisible()
    await expect(page.getByText(/61 行/)).toBeVisible()
  })
})

test.describe('G11 AI 端点注册', () => {
  for (const section of ['adjudication-analysis', 'return-rate-conclusion', 'voucher-conclusion'] as const) {
    test(`POST /g11/ai/${section} 路由存在`, async ({ request }) => {
      test.setTimeout(30_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
      test.skip(!wpResult.exists, 'G11 底稿不存在')

      const resp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g11/ai/${section}`,
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

test.describe('G11 深度 — G11-5 与校验 API', () => {
  test('G11-5 分段 Tab 与抽查结论区', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-5')
    await page.waitForTimeout(2_000)
    await expect(page.getByText('凭证基础').first()).toBeVisible()
    await page.getByText('结论').first().click()
    await page.waitForTimeout(500)
    await expect(page.locator('[data-testid="g11-voucher-conclusion"]')).toBeVisible()
    await expect(page.getByText('抽查结论').first()).toBeVisible()
  })

  test('G11-1 fine-rule 勾稽标签可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G11-1')
    await page.waitForTimeout(2_000)
    const checks = page.locator('[data-testid="g11-fine-checks"]')
    await expect(checks).toBeVisible()
    await expect(checks.getByText(/G11-CHK-01/)).toBeVisible()
    await expect(checks.getByText(/G11-CHK-02/)).toBeVisible()
  })

  test('POST validate-formulas 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G11', PROJECT_ID)
    test.skip(!wpResult.exists, 'G11 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g11/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [
            {
              rowKey: 'other',
              currentUnadjusted: 0,
              currentAdjustment: 0,
              currentAudited: 0,
              priorUnadjusted: 0,
              priorAdjustment: 0,
              priorAudited: 0,
            },
          ],
          detail_rows: [],
        },
      },
    )
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    const data = body.data ?? body
    expect(data.ok).toBe(true)
  })
})
