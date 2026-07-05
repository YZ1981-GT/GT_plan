/**
 * h-cycle-h10-asset-disposal-income.spec.ts — H10 资产处置损益 E2E 冒烟
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
  clickWorkpaperDirectoryTab,
  clickDisclosureSheetTab,
  expectHtmlDualModeOrContent,
} from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID
const COMPONENT_TYPE = 'h10-asset-disposal-income'

type SmokeCase = { wpCode: string; bodyHint: RegExp; testId?: string }

const SMOKE_CASES: SmokeCase[] = [
  { wpCode: 'H10A', bodyHint: /程序|资产处置|6115/ },
  { wpCode: 'H10-1', bodyHint: /审定|AJE|6115/, testId: 'h10-adjudication' },
  { wpCode: 'H10-2', bodyHint: /明细|处置|损益/, testId: 'h10-detail-table' },
  { wpCode: 'H10-3', bodyHint: /调整|借贷|AJE/, testId: 'h10-adjustment' },
  { wpCode: 'H10-4', bodyHint: /检查|合规|核对/, testId: 'h10-check' },
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

test.describe('H10 资产处置损益 — render-config', () => {
  test('H10 bundle 含 h10-asset-disposal-income componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在')

    const rcData = await fetchRenderConfig(request, token, wpResult.wpId!)
    expect(sheetComponentTypes(rcData)).toContain(COMPONENT_TYPE)
  })
})

test.describe('H10 资产处置损益 — HTML 页面冒烟', () => {
  for (const c of SMOKE_CASES) {
    test(`${c.wpCode} 页面加载`, async ({ page, request }) => {
      test.setTimeout(90_000)
      await loginAs(page)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
      test.skip(!wpResult.exists, 'H10 底稿不存在')

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

test.describe('H10 导入 round-trip（API）', () => {
  for (const sheet of ['H10-2', 'H10-3'] as const) {
    test(`${sheet} — export-template → import-data`, async ({ request }) => {
      test.setTimeout(60_000)
      const token = await getToken(request)
      const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
      test.skip(!wpResult.exists, 'H10 底稿不存在')

      const wpId = wpResult.wpId!
      const headers = { Authorization: `Bearer ${token}` }

      const tplResp = await request.post(
        `/api/workpapers/${wpId}/h10/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(tplResp.status()).toBe(200)
      const buf = await tplResp.body()
      const tmpPath = path.join(os.tmpdir(), `h10-${sheet}-template.xlsx`)
      fs.writeFileSync(tmpPath, buf)

      const importResp = await request.post(
        `/api/workpapers/${wpId}/h10/import-data?sheet=${sheet}`,
        {
          headers,
          multipart: {
            file: {
              name: `h10-${sheet}.xlsx`,
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

test.describe('H10 validate-formulas API', () => {
  test('POST /h10/validate-formulas 路由存在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在')

    const resp = await request.post(
      `/api/workpapers/${wpResult.wpId}/h10/validate-formulas`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          adjudication_rows: [],
          detail_rows: [],
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

  test('H10-1 审定表 validate 按钮可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperSheetTab(page, 'H10-1')
    await page.waitForTimeout(2_000)

    await expect(page.locator('[data-testid="h10-adjudication"]')).toBeVisible({ timeout: 8_000 })
    await expect(page.locator('[data-testid="h10-validate-btn"]')).toBeVisible()
    await expect(page.locator('[data-testid="h10-fine-checks"]')).toBeVisible()
    await expect(page.locator('[data-testid="h10-fine-checks"]')).toContainText('H10-CHK-03')
    await expect(page.locator('[data-testid="h10-fine-checks"]')).toContainText('H10-CHK-04')
  })
})

test.describe('H10 底稿目录与附注', () => {
  test('底稿目录 — 追溯链表格可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickWorkpaperDirectoryTab(page)

    await expect(page.locator('[data-testid="h10-directory"]')).toBeVisible({ timeout: 8_000 })
    await expect(page.getByText('来源追溯链状态')).toBeVisible()
  })

  test('附注上市 — disclosure 表格可见', async ({ page, request }) => {
    test.setTimeout(90_000)
    await loginAs(page)
    const token = await getToken(request)
    const wpResult = await findWorkpaper(request, token, 'H10', PROJECT_ID)
    test.skip(!wpResult.exists, 'H10 底稿不存在')

    await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpResult.wpId}/edit`)
    await page.waitForTimeout(4_000)
    await clickDisclosureSheetTab(page, 'listed')

    await expect(page.locator('[data-testid="h10-disclosure-listed"]')).toBeVisible({ timeout: 8_000 })
    await expect(page.locator('[data-testid="h10-disclosure-ai-btn"]')).toBeVisible()
  })
})
