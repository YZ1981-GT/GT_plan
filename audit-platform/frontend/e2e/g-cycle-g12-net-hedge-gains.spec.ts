/**
 * g-cycle-g12-net-hedge-gains.spec.ts — G12 净敞口套期收益 E2E 冒烟
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
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'g12-net-hedge-gains'

const SMOKE_CASES = [
  { wpCode: 'G12A', bodyHint: /程序|套期|6103/ },
  { wpCode: 'G12-1', bodyHint: /审定|净敞口/ },
  { wpCode: 'G12-2', bodyHint: /套期关系|无效|套期明细/ },
  { wpCode: 'G12-3', bodyHint: /调整|同步至审定/ },
  { wpCode: 'G12-4', bodyHint: /公允价值|套期/ },
  { wpCode: 'G12-5', bodyHint: /净敞口|CAS24/ },
  { wpCode: 'G12-6', bodyHint: /凭证|借贷/ },
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
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('G12 — render-config', () => {
  test('G12 bundle 含 g12-net-hedge-gains', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
    test.skip(!wpResult.exists, 'G12 底稿不存在')
    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G12 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
      test.skip(!wpResult.exists, 'G12 底稿不存在')
      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_500)
      await expectHtmlDualModeOrContent(page, c.bodyHint)
    })
  }
})

test.describe('G12 — 附注披露行数', () => {
  test('上市 12+合计=13 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
    test.skip(!wpResult.exists, 'G12 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'listed')
    await expectDisclosureTableRows(page, 'g12-disclosure-listed-table', 13)
  })

  test('国企 11+合计=12 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
    test.skip(!wpResult.exists, 'G12 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'soe')
    await expectDisclosureTableRows(page, 'g12-disclosure-soe-table', 12)
  })
})

test.describe('G12 导入 round-trip（API）', () => {
  for (const sheet of ['G12-2', 'G12-3', 'G12-4', 'G12-6'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G12', PROJECT_ID)
      test.skip(!wpResult.exists, 'G12 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g12/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status(), `${sheet} export-template`).toBe(200)
      const buf = await tplResp.body()
      expect(buf.byteLength).toBeGreaterThan(100)

      const tmpPath = path.join(os.tmpdir(), `${sheet}-e2e-${Date.now()}.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const impResp = await request.post(
        `/api/workpapers/${wpId}/g12/import-data?sheet=${sheet}`,
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
