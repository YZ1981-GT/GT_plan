/**
 * g-cycle-g14-credit-impairment-loss.spec.ts — G14 信用减值损失 E2E 冒烟
 *
 * 覆盖：
 * - render-config componentType 注册
 * - G14A / G14-1 / G14-2 / G14-3 HTML 页面加载 + 双模式
 * - G14-2 / G14-3 导入 export-template round-trip（API）
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
const COMPONENT_TYPE = 'g14-credit-impairment-loss'

type SmokeCase = {
  wpCode: string
  bodyHint: RegExp
}

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'G14A', bodyHint: /程序|信用减值|6702/ },
  { wpCode: 'G14-1', bodyHint: /审定|信用减值|变动率/ },
  { wpCode: 'G14-2', bodyHint: /明细|减值准备|计入损益/ },
  { wpCode: 'G14-3', bodyHint: /调整|借贷|同步至明细/ },
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

test.describe('G14 信用减值损失 — render-config', () => {
  test('G14 bundle 含 g14-credit-impairment-loss componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('G14 信用减值损失 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
      test.skip(!wpResult.exists, 'G14 底稿不存在')

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
      page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

      await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
      await page.waitForTimeout(4_000)
      await clickWorkpaperSheetTab(page, c.wpCode)
      await page.waitForTimeout(2_500)

      const criticalErrors = consoleErrors.filter((e) =>
        /Cannot access|before initialization|ReferenceError|TypeError.*undefined|TypeError.*null/.test(e),
      )
      expect(criticalErrors, `严重错误:\n${criticalErrors.join('\n')}`).toHaveLength(0)

      await expectHtmlDualModeOrContent(page, c.bodyHint)
    })
  }
})

test.describe('G14 导入 round-trip（API）', () => {
  for (const sheet of ['G14-2', 'G14-3'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
      test.skip(!wpResult.exists, 'G14 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/g14/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status(), `${sheet} export-template`).toBe(200)
      const buf = await tplResp.body()
      expect(buf.byteLength).toBeGreaterThan(100)

      const tmpPath = path.join(os.tmpdir(), `${sheet}-e2e-${Date.now()}.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const impResp = await request.post(
        `/api/workpapers/${wpId}/g14/import-data?sheet=${sheet}`,
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

    test(`${sheet} — export-data 返回 xlsx`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
      test.skip(!wpResult.exists, 'G14 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }
      const resp = await request.post(
        `/api/workpapers/${wpId}/g14/export-data?sheet=${sheet}`,
        { headers },
      )
      expect(resp.status(), `${sheet} export-data`).toBe(200)
      expect(resp.headers()['content-type'] || '').toMatch(/spreadsheet/)
      const buf = await resp.body()
      expect(buf.byteLength).toBeGreaterThan(100)
    })
  }
})

test.describe('G14 — 底稿目录与审定状态条', () => {
  test('底稿目录显示编制进度与 10 类减值来源提示', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, '底稿目录')
    await expect(page.getByTestId('g14-directory')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/编制进度/)).toBeVisible()
    await expect(page.getByText(/10 类减值来源/)).toBeVisible()
  })

  test('G14-1 显示状态条与试算勾稽区', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G14-1')
    await expect(page.getByTestId('g14-adj-status-strip')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('g14-adj-recon')).toBeVisible()
    await expect(page.getByTestId('g14-adj-publish')).toBeVisible()
  })
})

  test('上市 10+合计=11 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'listed')
    await expectDisclosureTableRows(page, 'g14-disclosure-listed-table', 11)
  })

  test('国企 4+合计=5 行', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'soe')
    await expectDisclosureTableRows(page, 'g14-disclosure-soe-table', 5)
    await expect(page.getByText('坏账损失')).toBeVisible()
  })
})

test.describe('G14-2 明细全表勾稽', () => {
  test('固定 10 行 + 合计；全表 / 分 Tab 列头', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'G14', PROJECT_ID)
    test.skip(!wpResult.exists, 'G14 底稿不存在')
    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'G14-2')
    await expectDisclosureTableRows(page, 'g14-detail-table', 11)
    // 默认全表：损益侧 + 准备滚动同屏
    await expectDetailColumnHeaders(page, 'g14-detail-table', [
      '项目', '未审数', '调整数', '审定数', '对应科目',
      '期初余额', '本期计提', '本期转回', '本期转销', '其他变动', '期末余额', '试算期末', '计入损益', '核对',
    ])
    await expect(page.getByText('合同资产减值损失')).toBeVisible()
    await expect(page.getByTestId('g14-oci-tag').first()).toBeVisible()
    await clickDetailSegmentTab(page, 'g14-detail-tab', '本期数')
    await expectDetailColumnHeaders(page, 'g14-detail-table', [
      '项目', '未审数', '调整数', '审定数', '对应科目', 'ECL来源', '索引号',
    ])
    await clickDetailSegmentTab(page, 'g14-detail-tab', '减值准备')
    await expectDetailColumnHeaders(page, 'g14-detail-table', [
      '期初余额', '本期计提', '本期转回', '本期转销', '其他变动', '期末余额', '试算期末', '计入损益', '核对',
    ])
  })
})
