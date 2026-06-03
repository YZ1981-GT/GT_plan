/**
 * custom-workpaper-formula-binding — Playwright UAT（任务 10.3 + 11.5）
 *
 * 前置：后端 9980 + 前端 3030（playwright.config 可 reuseExistingServer 拉起 dev）
 * 数据：辽宁卫生 2025 项目 + 可自动 create-custom 自建底稿
 *
 * 运行：
 *   cd audit-platform/frontend
 *   npx playwright test e2e/custom-workpaper-formula-binding.spec.ts
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
const API_BASE = process.env.PW_API_BASE || 'http://localhost:9980'

const ENV_SKIP_MSG =
  'E2E 需 PostgreSQL + 后端 9980 + 前端 3030。请先 docker compose up -d（或启动 audit-postgres），再运行 start-dev.bat，然后执行 npm run test:e2e:custom-wp'

let envReady = false
let envSkipReason = ENV_SKIP_MSG

async function probeE2eEnv(request: APIRequestContext): Promise<boolean> {
  try {
    const login = await request.post(`${API_BASE}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
      timeout: 30_000,
    })
    if (login.ok()) return true

    const txt = await login.text().catch(() => '')
    let healthHint = ''
    try {
      const health = await request.get(`${API_BASE}/api/health`, { timeout: 15_000 })
      const hb = await health.json().catch(() => ({}))
      const data = (hb as { data?: Record<string, unknown> }).data ?? hb
      const svc = (data as { services?: Record<string, string> }).services
      if (svc) healthHint = ` | health services=${JSON.stringify(svc)}`
    } catch {
      healthHint = ' | health 不可达'
    }
    envSkipReason = `登录失败 ${login.status()}: ${txt.slice(0, 120)}${healthHint}`
    return false
  } catch (e) {
    envSkipReason = `无法连接 ${API_BASE}: ${(e as Error).message}`
    return false
  }
}

async function loginAs(page: Page, request: APIRequestContext, username = 'admin', password = 'admin123') {
  const resp = await request.post(`${API_BASE}/api/auth/login`, {
    data: { username, password },
  })
  expect(resp.ok(), await resp.text()).toBeTruthy()
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

/** 优先 D2/B 类 HTML 底稿（走 GtWpRenderer + 编制信息表头） */
async function findHtmlRendererWp(
  request: APIRequestContext,
  token: string,
): Promise<{ id: string; wpCode: string } | null> {
  const resp = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
    headers: authHeaders(token),
  })
  if (!resp.ok()) return null
  const body = await resp.json()
  const list = body?.data?.items || body?.items || body?.data || []
  const prefer = ['D2', 'B1', 'E1', 'C1', 'A1']
  for (const code of prefer) {
    const wp = list.find((w: { wp_code?: string }) => (w.wp_code || '').toUpperCase() === code)
    if (!wp?.id) continue
    const cls = await request.get('/api/wp-classifications', {
      headers: authHeaders(token),
      params: { wp_code: wp.wp_code, project_id: PROJECT_ID },
    })
    if (!cls.ok()) continue
    const cbody = await cls.json()
    const items = cbody?.data?.classifications ?? cbody?.classifications ?? []
    const ct = items[0]?.componentType ?? ''
    if (ct && ct !== 'univer' && ct !== 'skip') {
      return { id: wp.id, wpCode: wp.wp_code }
    }
  }
  return null
}

async function createCustomWpWithCells(
  request: APIRequestContext,
  token: string,
): Promise<{ wpId: string; wpCode: string; sheetName: string }> {
  const wpName = 'Playwright自定义底稿'
  let wpCode = ''
  let wpId = ''
  let createResp: Awaited<ReturnType<APIRequestContext['post']>> | null = null

  for (let attempt = 0; attempt < 3; attempt++) {
    wpCode = `PW${Date.now().toString(36).slice(-6).toUpperCase()}${attempt}`
    createResp = await request.post(
      `${API_BASE}/api/projects/${PROJECT_ID}/working-papers/create-custom`,
      {
        headers: authHeaders(token),
        data: {
          wp_code: wpCode,
          wp_name: wpName,
          audit_cycle: 'A',
          year: 2025,
        },
      },
    )
    if (createResp.ok()) {
      const created = await createResp.json()
      wpId = created?.data?.wp_id ?? created?.wp_id
      if (wpId) break
    }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)))
  }
  expect(createResp?.ok(), await createResp?.text()).toBeTruthy()
  expect(wpId).toBeTruthy()
  const sheetName = wpCode

  const saveResp = await request.post(`${API_BASE}/api/workpapers/${wpId}/save`, {
    headers: authHeaders(token),
    data: {
      sheet_name: sheetName,
      schema_version: 'v2025-R5',
      html_data: {
        cells: {
          A5: '货币资金',
          B5: 1000,
        },
      },
      force_overwrite: true,
    },
  })
  expect(saveResp.ok(), await saveResp.text()).toBeTruthy()

  await request.post(`${API_BASE}/api/address-registry/invalidate`, {
    headers: authHeaders(token),
    data: { project_id: PROJECT_ID, domain: 'wp' },
  })

  return { wpId, wpCode, sheetName }
}

function unwrapData<T = Record<string, unknown>>(body: T & { data?: T }): T {
  return (body as { data?: T }).data ?? body
}

async function getB5FromRenderConfig(
  request: APIRequestContext,
  token: string,
  wpId: string,
  sheetName: string,
): Promise<unknown> {
  const resp = await request.get(`${API_BASE}/api/workpapers/${wpId}/render-config`, {
    headers: authHeaders(token),
  })
  expect(resp.ok(), await resp.text()).toBeTruthy()
  const data = unwrapData(await resp.json())
  const sheets = (data as { sheets?: Array<Record<string, unknown>> }).sheets ?? []
  const sheet =
    sheets.find(
      (s) => s.sheet_name === sheetName || s.name === sheetName || s.sheet_key === sheetName,
    ) ?? sheets[0]
  const cells = (sheet?.html_data as { cells?: Record<string, unknown> })?.cells ?? {}
  const raw = cells.B5 ?? cells.b5
  if (raw && typeof raw === 'object') {
    const o = raw as { value?: unknown; v?: unknown }
    return o.value ?? o.v
  }
  return raw
}

async function putFormula(
  request: APIRequestContext,
  token: string,
  wpId: string,
  sheetName: string,
  targetCell: string,
  expression: string,
) {
  return request.put(`${API_BASE}/api/workpapers/${wpId}/formulas`, {
    headers: authHeaders(token),
    data: {
      sheet_name: sheetName,
      target_cell: targetCell,
      expression,
      year: 2025,
      template_type: 'soe',
      category: 'auto_calc',
    },
  })
}

async function openWorkpaperEditor(page: Page, wpId: string) {
  await page.goto(`/projects/${PROJECT_ID}/workpapers/${wpId}/edit`)
  await page.waitForSelector('.gt-wp-renderer, .gt-wp-editor, .gt-wp-editor-loading', {
    timeout: 30_000,
  })
}

test.describe('custom-workpaper-formula-binding UAT', () => {
  test.beforeAll(async ({ request }) => {
    envReady = await probeE2eEnv(request)
  })

  test.beforeEach(() => {
    test.skip(!envReady, envSkipReason)
  })

  test.describe('10.3 编制信息表头 GtWpPreparationHeader', () => {
    test('表头在内容区上方、GT 紫样式、无会计期间、可折叠', async ({ page, request }) => {
      test.setTimeout(90_000)
      const token = await loginAs(page, request)
      const wp = await findHtmlRendererWp(request, token)
      test.skip(!wp, '项目内无 HTML 类底稿（D2/B1 等）')

      await openWorkpaperEditor(page, wp!.id)

      const prep = page.locator('.gt-wp-prep')
      await expect(prep).toBeVisible({ timeout: 20_000 })

      const content = page.locator('.gt-wp-renderer__content')
      await expect(content).toBeVisible()

      const prepBox = await prep.boundingBox()
      const contentBox = await content.boundingBox()
      expect(prepBox && contentBox).toBeTruthy()
      if (prepBox && contentBox) {
        expect(prepBox.y).toBeLessThan(contentBox.y)
      }

      await expect(prep).not.toContainText('会计期间')

      const titleColor = await prep.locator('.gt-wp-prep__title').evaluate(
        (el) => getComputedStyle(el).color,
      )
      expect(titleColor.toLowerCase()).toMatch(/rgb\(75,\s*45,\s*119\)|#4b2d77/)

      const toggleBtn = prep.locator('.gt-wp-prep__toggle')
      await toggleBtn.click()
      await expect(prep).toHaveClass(/is-collapsed/)
      await expect(toggleBtn).toBeVisible()
      await expect(prep.locator('.gt-wp-prep__body')).toBeHidden()

      await toggleBtn.click()
      await expect(prep.locator('.gt-wp-prep__body')).toBeVisible()
    })

    test('切换 sheet 后表头仍可见且编制信息字段不变', async ({ page, request }) => {
      test.setTimeout(90_000)
      const token = await loginAs(page, request)
      const wp = await findHtmlRendererWp(request, token)
      test.skip(!wp, '项目内无 HTML 类底稿')

      await openWorkpaperEditor(page, wp!.id)
      await expect(page.locator('.gt-wp-prep')).toBeVisible({ timeout: 20_000 })

      const entityBefore = await page
        .locator('.gt-wp-prep__desc')
        .getByText(/被审计单位|—/)
        .first()
        .textContent()
        .catch(() => '')

      const tabs = page.locator('.gt-wp-renderer__sheet-tabs .el-tabs__item')
      const tabCount = await tabs.count()
      test.skip(tabCount < 2, '当前底稿仅单 sheet，跳过切 tab 用例')

      await tabs.nth(1).click()
      await page.waitForTimeout(800)

      await expect(page.locator('.gt-wp-prep')).toBeVisible()
      const entityAfter = await page
        .locator('.gt-wp-prep__desc')
        .getByText(/被审计单位|—/)
        .first()
        .textContent()
        .catch(() => '')
      expect(entityAfter).toBe(entityBefore)
    })
  })

  test.describe('11.5 自定义底稿公式编辑器 GtCustomWpEditor', () => {
    test('custom 视图打开公式弹窗、WP 注册表选址、保存公式', async ({ page, request }) => {
      test.setTimeout(120_000)
      const token = await loginAs(page, request)
      const custom = await createCustomWpWithCells(request, token)

      const clsResp = await request.get('/api/wp-classifications', {
        headers: authHeaders(token),
        params: { wp_code: custom.wpCode, project_id: PROJECT_ID },
      })
      expect(clsResp.ok()).toBeTruthy()
      const clsBody = await clsResp.json()
      const ct =
        clsBody?.data?.classifications?.[0]?.componentType ??
        clsBody?.classifications?.[0]?.componentType
      expect(ct).toBe('custom')

      await openWorkpaperEditor(page, custom.wpId)
      await expect(page.locator('.gt-custom-wp')).toBeVisible({ timeout: 25_000 })

      const formulaBtn = page.locator('.gt-custom-wp__toolbar button:has-text("公式")')
      await expect(formulaBtn).toBeEnabled()
      await formulaBtn.click()

      const dialog = page.locator('.el-dialog').filter({ hasText: /公式/ }).last()
      await expect(dialog).toBeVisible({ timeout: 10_000 })

      await dialog.locator('button:has-text("点击定位")').first().click()
      const targetDlg = page.locator('.el-dialog').filter({ hasText: /定位写入目标/ }).last()
      await expect(targetDlg).toBeVisible({ timeout: 10_000 })
      const b5Row = targetDlg.locator('.el-table__row').filter({ hasText: 'B5' })
      if (await b5Row.count()) {
        await b5Row.first().click()
        await expect(targetDlg.locator('button:has-text("确认定位")')).toBeEnabled({ timeout: 5_000 })
        await targetDlg.locator('button:has-text("确认定位")').click()
      } else {
        await targetDlg.locator('button:has-text("取消")').click()
        await dialog.locator('.gt-fe-target-bar input').first().fill('B5')
      }

      const wpPickBtn = dialog.locator('button').filter({ hasText: /^WP$/ }).first()
      await wpPickBtn.click()
      const browser = page.locator('.el-dialog').filter({ hasText: /底稿/ }).last()
      await expect(browser).toBeVisible({ timeout: 10_000 })
      const regRow = browser.locator('tbody tr').filter({ hasText: custom.wpCode }).first()
      if (await regRow.count()) {
        await regRow.click()
      } else {
        await browser.locator('tbody tr').first().click()
      }
      const exprVal = await dialog.locator('textarea').first().inputValue()
      expect(exprVal).toMatch(/WP\(/)

      if (!exprVal.includes('B5')) {
        await dialog.locator('textarea').first().fill(`WP('${custom.wpCode}','B5')`)
      }

      await dialog.locator('button:has-text("保存公式")').click()

      await expect(page.locator('.el-message--success')).toBeVisible({ timeout: 15_000 })

      const listResp = await request.get(
        `${API_BASE}/api/workpapers/${custom.wpId}/formulas`,
        { headers: authHeaders(token) },
      )
      expect(listResp.ok()).toBeTruthy()
      const formulas = await listResp.json()
      const items = formulas?.data ?? formulas ?? []
      const arr = Array.isArray(items) ? items : items?.items ?? []
      expect(arr.some((f: { target_cell?: string }) => f.target_cell === 'B5')).toBeTruthy()
    })

    test('自定义网格只读（data-readonly + 无 contenteditable）', async ({ page, request }) => {
      test.setTimeout(90_000)
      const token = await loginAs(page, request)
      const custom = await createCustomWpWithCells(request, token)
      await openWorkpaperEditor(page, custom.wpId)
      await expect(page.locator('.gt-custom-wp')).toBeVisible({ timeout: 25_000 })
      const grid = page.locator('.gt-grid-sheet')
      if (await grid.count()) {
        await expect(grid.first()).toHaveAttribute('data-readonly', 'true')
        await expect(grid.locator('[contenteditable="true"]')).toHaveCount(0)
      }
      await expect(page.locator('.gt-custom-wp input[type="text"]')).toHaveCount(0)
    })

    test('保存公式 API 写回 evaluated_value 与 parsed_data B5', async ({ request }) => {
      test.setTimeout(90_000)
      const login = await request.post(`${API_BASE}/api/auth/login`, {
        data: { username: 'admin', password: 'admin123' },
      })
      expect(login.ok()).toBeTruthy()
      const loginBody = await login.json()
      const token = loginBody.data?.access_token ?? loginBody.access_token

      const custom = await createCustomWpWithCells(request, token)
      const putResp = await putFormula(
        request,
        token,
        custom.wpId,
        custom.sheetName,
        'B5',
        '8888',
      )
      expect(putResp.ok(), await putResp.text()).toBeTruthy()
      const putBody = unwrapData(await putResp.json())
      expect(String(putBody.evaluated_value)).toBe('8888')

      const b5 = await getB5FromRenderConfig(
        request,
        token,
        custom.wpId,
        custom.sheetName,
      )
      expect(b5 === 8888 || b5 === '8888').toBeTruthy()
    })

    test('跨底稿公式保存后 linkage 标记引用方 stale', async ({ request }) => {
      test.setTimeout(120_000)
      const login = await request.post(`${API_BASE}/api/auth/login`, {
        data: { username: 'admin', password: 'admin123' },
      })
      expect(login.ok()).toBeTruthy()
      const loginBody = await login.json()
      const token = loginBody.data?.access_token ?? loginBody.access_token

      const src = await createCustomWpWithCells(request, token)
      const dep = await createCustomWpWithCells(request, token)

      const regResp = await request.get(`${API_BASE}/api/address-registry`, {
        headers: authHeaders(token),
        params: {
          project_id: PROJECT_ID,
          year: 2025,
          domain: 'wp',
          keyword: src.wpCode,
          limit: 200,
        },
      })
      expect(regResp.ok()).toBeTruthy()
      const regBody = await regResp.json()
      const regEntries = (regBody.items ??
        (unwrapData(regBody) as { items?: Array<{ wp_code?: string; cell?: string }> }).items ??
        []) as Array<{ wp_code?: string; cell?: string }>
      const hasSrcB5 = regEntries.some(
        (e) => e.wp_code === src.wpCode && String(e.cell || '').toUpperCase() === 'B5',
      )
      test.skip(!hasSrcB5, '地址注册表尚未包含源底稿 B5，跳过联动用例')

      const depFormula = await putFormula(
        request,
        token,
        dep.wpId,
        dep.sheetName,
        'C10',
        `WP('${src.wpCode}','B5')+1`,
      )
      expect(depFormula.ok(), await depFormula.text()).toBeTruthy()

      const srcPut = await putFormula(
        request,
        token,
        src.wpId,
        src.sheetName,
        'B5',
        '2000',
      )
      expect(srcPut.ok(), await srcPut.text()).toBeTruthy()
      const srcBody = unwrapData(await srcPut.json())
      const linkage = srcBody.linkage as { dynamic_dependents?: string[] } | undefined
      expect(linkage?.dynamic_dependents?.length).toBeGreaterThan(0)

      const staleResp = await request.get(
        `${API_BASE}/api/projects/${PROJECT_ID}/stale-summary`,
        { headers: authHeaders(token) },
      )
      expect(staleResp.ok()).toBeTruthy()
      const staleItems = (unwrapData(await staleResp.json()) as { items?: Array<{ id?: string }> })
        .items ?? []
      expect(staleItems.some((w) => w.id === dep.wpId)).toBeTruthy()
    })
  })
})
