/**
 * f2-html-smoke.spec.ts — F2 存货 HTML 冒烟：审定表 / 跌价 / 履约成本 / IPO + 模式切换 + 导入 round-trip
 *
 * 代表 sheet：
 *   F2-1  审定表 → f2-inventory-main
 *   F2-47 跌价准备 → f2-inventory-valuation-impairment
 *   F2-55 合同履约成本 → f2-inventory-special
 *   F2-70 IPO 披露 → f2-inventory-special
 *   F2-21 监盘问卷 → f2-stocktake-bundle
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { TEST_PROJECT_ID, findWorkpaper, fetchRenderConfig, sheetComponentTypes, clickWorkpaperSheetTab, expectHtmlDualModeOrContent } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

type SmokeCase = {
  wpCode: string
  componentType: string
  sheet?: string
  apiPrefix?: string
  bodyHint?: RegExp
}

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'F2-1', componentType: 'f2-inventory-main', bodyHint: /审定|存货|期初/ },
  // F2-14 是 F2-1 包内 sheet，无独立 wp_index；冒烟用 F2-1 打开后切 tab（见下方专用用例）
  { wpCode: 'F2-29', componentType: 'f2-inventory-main', bodyHint: /截止|入库|凭证/ },
  { wpCode: 'F2-47', componentType: 'f2-inventory-valuation-impairment', bodyHint: /跌价|准备|可变现/ },
  { wpCode: 'F2-55', componentType: 'f2-inventory-special', bodyHint: /履约|合同|成本/ },
  { wpCode: 'F2-70', componentType: 'f2-inventory-special', bodyHint: /披露|IPO|存货/ },
  { wpCode: 'F2-21', componentType: 'f2-stocktake-bundle', bodyHint: /盘点|监盘|问卷/ },
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

async function getRenderConfig(
  request: APIRequestContext,
  token: string,
  wpId: string,
) {
  return fetchRenderConfig(request, token, wpId)
}

test.describe('F2 HTML 冒烟 — render-config + 页面加载 + 双模式', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} — componentType 为 ${c.componentType}`, async ({ request }) => {
      test.setTimeout(30_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, c.wpCode, PROJECT_ID)
      test.skip(!wpResult.exists, `${c.wpCode} 底稿不存在`)

      const rcData = await getRenderConfig(request, token, wpResult.wpId!)
      expect(sheetComponentTypes(rcData)).toContain(c.componentType)
    })

    test(`${c.wpCode} — HTML 页面加载 + el-segmented 双模式`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page, 'admin', 'admin123')
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, c.wpCode, PROJECT_ID)
      test.skip(!wpResult.exists, `${c.wpCode} 底稿不存在`)

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

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_000)

      const criticalErrors = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
      )
      expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)

      const segmented = page.locator('.el-segmented')
      if (c.bodyHint) {
        await expectHtmlDualModeOrContent(page, c.bodyHint)
      } else {
        await expect(segmented.first()).toBeVisible({ timeout: 15_000 })
      }
    })
  }
})

test.describe('F2 HTML 导入 round-trip（API）', () => {
  test('F2-24 — export-template → import-data round-trip', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'F2-24', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-24 不存在')

    const wpId = wpResult.wpId!
    const headers = { Authorization: `Bearer ${token}` }

    const tplResp = await request.post(
      `/api/workpapers/${wpId}/f2-st/export-template?sheet=F2-24`,
      { headers },
    )
    expect(tplResp.status()).toBe(200)
    const buf = await tplResp.body()
    const tmpPath = path.join(os.tmpdir(), `f2-24-smoke-${Date.now()}.xlsx`)
    fs.writeFileSync(tmpPath, buf)

    const importResp = await request.post(
      `/api/workpapers/${wpId}/f2-st/import-data?sheet=F2-24`,
      {
        headers,
        multipart: {
          file: {
            name: 'F2-24.xlsx',
            mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            buffer: fs.readFileSync(tmpPath),
          },
        },
      },
    )
    fs.unlinkSync(tmpPath)
    expect(importResp.status()).toBe(200)
    const body = await importResp.json()
    const data = body?.data ?? body
    expect(data.ok).toBeTruthy()
  })

  test('F2-1 — f2 export-template 可下载（sheet F2-8）', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'F2-1', PROJECT_ID)
    test.skip(!wpResult.exists, 'F2-1 不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/f2/export-template?sheet=F2-8`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(resp.status()).toBe(200)
    expect(resp.headers()['content-type']).toContain('spreadsheet')
  })
})
