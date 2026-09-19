/**
 * f2-stocktake-html.spec.ts — F2-21~26 监盘 HTML 文本模块 + 混合表 E2E
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

type StocktakeCase = {
  wpCode: string
  bodyHint: RegExp
  /** 纯文本 Tab 不应有 f2-st 导入导出 API */
  textOnly?: boolean
}

const STOCKTAKE_CASES: StocktakeCase[] = [
  { wpCode: 'F2-21', bodyHint: /盘点|监盘|问卷|地点|仓库/, textOnly: true },
  { wpCode: 'F2-22', bodyHint: /监盘|计划|程序/, textOnly: true },
  { wpCode: 'F2-23', bodyHint: /监盘|小结|结论/, textOnly: true },
  { wpCode: 'F2-24', bodyHint: /核对|账面|ERP/ },
]

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token
}

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('F2 监盘 HTML — render-config 契约', () => {
  test('F2-21~F2-26 全部为 f2-stocktake-bundle', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)
    for (const code of ['F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26']) {
      const wp = await findWorkpaper(request, token, code, PROJECT_ID)
      if (!wp.exists) continue
      const data = await fetchRenderConfig(request, token, wp.wpId!)
      expect(sheetComponentTypes(data), code).toContain('f2-stocktake-bundle')
    }
  })

  test('F2-21 拒绝 f2-st export-template（文本问卷无 Excel）', async ({ request }) => {
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'F2-21', PROJECT_ID)
    test.skip(!wp.exists, 'F2-21 不存在')
    const resp = await request.post(
      `/api/workpapers/${wp.wpId}/f2-st/export-template?sheet=F2-21`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(resp.status()).toBe(400)
  })
})

test.describe('F2 监盘 HTML — 页面内容与双模式', () => {
  for (const c of STOCKTAKE_CASES) {
    test(`${c.wpCode} — HTML 加载 + 文本/表格内容`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const token = await getToken(request)
      const wp = await findWorkpaper(request, token, c.wpCode, PROJECT_ID)
      test.skip(!wp.exists, `${c.wpCode} 不存在`)

      const consoleErrors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          const text = msg.text()
          if (/\/ai\//.test(text) && /405/.test(text)) return
          if (/net::ERR_|Failed to fetch|NetworkError/.test(text)) return
          if (/Failed to load resource.*500/.test(text)) return
          if (/onlyoffice|DocsAPI/.test(text)) return
          consoleErrors.push(text)
        }
      })
      page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wp.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_000)

      const critical = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
      )
      expect(critical, critical.join('\n')).toHaveLength(0)

      await expectHtmlDualModeOrContent(page, c.bodyHint)
    })
  }
})

test.describe('F2 监盘 — F2-24/25 import round-trip', () => {
  for (const sheet of ['F2-24', 'F2-25'] as const) {
    test(`${sheet} export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wp = await findWorkpaper(request, token, sheet, PROJECT_ID)
      test.skip(!wp.exists, `${sheet} 不存在`)

      const headers = { Authorization: `Bearer ${token}` }
      const tpl = await request.post(
        `/api/workpapers/${wp.wpId}/f2-st/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tpl.status()).toBe(200)
      const buf = await tpl.body()
      const tmpPath = path.join(os.tmpdir(), `${sheet}-e2e-${Date.now()}.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const imp = await request.post(
        `/api/workpapers/${wp.wpId}/f2-st/import-data?sheet=${sheet}`,
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
      fs.unlinkSync(tmpPath)
      expect(imp.status()).toBe(200)
      const body = await imp.json()
      const data = body?.data ?? body
      expect(data.ok).toBeTruthy()
    })
  }
})
