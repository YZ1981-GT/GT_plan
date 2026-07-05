/**
 * g-cycle-g6-other-bond-investment-main.spec.ts — G6 其他债权投资(main组) E2E 冒烟
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
const COMPONENT_TYPE = 'g6-other-bond-investment-main'

type SmokeCase = { wpCode: string; bodyHint: RegExp }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G6A', bodyHint: /程序|其他债权|1503/ },
  { wpCode: 'G6-1', bodyHint: /审定|FVOCI|1503/ },
  { wpCode: 'G6-2', bodyHint: /明细|投资项目|期初小计/ },
  { wpCode: 'G6-3', bodyHint: /坏账|ECL|损失率/ },
  { wpCode: 'G6-4', bodyHint: /调整|借贷|AJE/ },
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

test.describe('G6 其他债权投资(main) — render-config', () => {
  test('G6 bundle 含 g6-other-bond-investment-main componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G6', PROJECT_ID)
    test.skip(!wpResult.exists, 'G6 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G6 其他债权投资(main) — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G6', PROJECT_ID)
      test.skip(!wpResult.exists, 'G6 底稿不存在')

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
    })
  }
})

test.describe('G6 导入 round-trip（API）', () => {
  for (const sheet of ['G6-2', 'G6-3', 'G6-4'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G6', PROJECT_ID)
      test.skip(!wpResult.exists, 'G6 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g6-main/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `g6-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/g6-main/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `g6-${sheet}.xlsx`,
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

test.describe('G6 AI 端点注册', () => {
  for (const section of ['adjudication-analysis', 'disclosure-text'] as const) {
    test(`POST /g6-main/ai/${section} 路由存在`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G6', PROJECT_ID)
      test.skip(!wpResult.exists, 'G6 底稿不存在')

      const resp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g6-main/ai/${section}`,
        {
          headers: { Authorization: `Bearer ${token}` },
          data: { existingContent: '', relatedContext: {} },
        },
      )
      expect([200, 500, 504]).toContain(resp.status())
      expect(resp.status()).not.toBe(404)
    })
  }
})
