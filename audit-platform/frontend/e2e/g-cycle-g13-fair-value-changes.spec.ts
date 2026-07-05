/**
 * g-cycle-g13-fair-value-changes.spec.ts — G13 公允价值变动 E2E 冒烟
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
  clickDisclosureSheetTab,
  expectDisclosureTableRows,
  expectDetailColumnHeaders,
  clickDetailSegmentTab,
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'g13-fair-value-changes'

const SMOKE_CASES = [
  { wpCode: 'G13A', bodyHint: /程序|公允价值|6101/ },
  { wpCode: 'G13-1', bodyHint: /审定|变动率/ },
  { wpCode: 'G13-2', bodyHint: /明细|FV变动/ },
  { wpCode: 'G13-3', bodyHint: /调整|借贷/ },
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

test.describe('G13 — render-config', () => {
  test('G13 bundle 含 g13-fair-value-changes', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
    test.skip(!wpResult.exists, 'G13 底稿不存在')
    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G13 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
      test.skip(!wpResult.exists, 'G13 底稿不存在')
      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_500)
      await expectHtmlDualModeOrContent(page, c.bodyHint)
    })
  }
})

test.describe('G13 — 附注披露行数', () => {
  test('上市 9+合计=10 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
    test.skip(!wpResult.exists, 'G13 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'listed')
    await expectDisclosureTableRows(page, 'g13-disclosure-listed-table', 10)
    await expect(page.getByText('合  计')).toBeVisible()
  })

  test('国企 7+合计=8 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
    test.skip(!wpResult.exists, 'G13 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'soe')
    await expectDisclosureTableRows(page, 'g13-disclosure-soe-table', 8)
  })
})

test.describe('G13-2 明细 12 列', () => {
  test('两 Tab 列头完整', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
    test.skip(!wpResult.exists, 'G13 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G13-2')
    await expectDetailColumnHeaders(page, 'g13-detail-table', [
      '序号', '金融工具名称', '所属科目', '金融工具类型', '源科目索引', '备注',
    ])
    await clickDetailSegmentTab(page, 'g13-detail-tab', 'FV与审定')
    await expectDetailColumnHeaders(page, 'g13-detail-table', [
      '期初FV', '期末FV', 'FV变动', '本期未审', '调整数', '审定数', '交叉验证',
    ])
  })
})

test.describe('G13 导入 round-trip（API）', () => {
  for (const sheet of ['G13-2', 'G13-3'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G13', PROJECT_ID)
      test.skip(!wpResult.exists, 'G13 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g13/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status(), `${sheet} export-template`).toBe(200)
      const buf = await tplResp.body()
      expect(buf.byteLength).toBeGreaterThan(100)

      const tmpPath = path.join(os.tmpdir(), `${sheet}-e2e-${Date.now()}.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const impResp = await request.post(
        `/api/workpapers/${wpId}/g13/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `${sheet}.xlsx`,
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              buffer: fs.readFileSync(tmpPath),
            },
          },
        },
      )
      expect(impResp.status(), `${sheet} import-data`).toBe(200)
      const body = await impResp.json()
      const data = body.data ?? body
      expect(data.ok, `${sheet} import errors: ${JSON.stringify(data.errors)}`).toBe(true)
    })
  }
})
