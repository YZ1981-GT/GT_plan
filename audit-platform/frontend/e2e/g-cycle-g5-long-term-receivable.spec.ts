/**
 * g-cycle-g5-long-term-receivable.spec.ts — G5 长期应收款 E2E 冒烟
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
const COMPONENT_TYPE = 'g5-long-term-receivable'

const SMOKE_CASES = [
  { wpCode: 'G5A', bodyHint: /程序|长期应收|1531/ },
  { wpCode: 'G5-1', bodyHint: /审定|长期应收|变动率/ },
  { wpCode: 'G5-5', bodyHint: /内含利率|融资租赁/ },
  { wpCode: 'G5-6', bodyHint: /实际利率|分期销售/ },
  { wpCode: 'G5-7', bodyHint: /保理|终止确认/ },
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

test.describe('G5 长期应收款 — render-config', () => {
  test('G5 bundle 含 g5-long-term-receivable componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G5', PROJECT_ID)
    test.skip(!wpResult.exists, 'G5 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G5 长期应收款 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G5', PROJECT_ID)
      test.skip(!wpResult.exists, 'G5 底稿不存在')

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

test.describe('G5 导入导出 API', () => {
  test('G5-7 export-template 往返', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G5', PROJECT_ID)
    test.skip(!wpResult.exists, 'G5 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/g5/export-template?sheet=G5-7`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(resp.ok()).toBeTruthy()
    const buf = await resp.body()
    expect(buf.byteLength).toBeGreaterThan(100)

    const tmpPath = path.join(os.tmpdir(), `g5-7-template-${Date.now()}.xlsx`)
    fs.writeFileSync(tmpPath, buf)
    try {
      const importResp = await request.post(
        `/api/workpapers/${wpResult.wpId}/g5/import-data?sheet=G5-7`,
        {
          headers: { Authorization: `Bearer ${token}` },
          multipart: { file: fs.createReadStream(tmpPath) },
        },
      )
      expect(importResp.ok()).toBeTruthy()
    } finally {
      fs.unlinkSync(tmpPath)
    }
  })
})

test.describe('G5-9/10 暂缓', () => {
  test('G5-9 显示暂缓提示', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G5', PROJECT_ID)
    test.skip(!wpResult.exists, 'G5 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G5-9')
    await page.waitForTimeout(2_000)
    await expect(page.locator('body')).toContainText(/暂缓|G4-9/)
  })
})
