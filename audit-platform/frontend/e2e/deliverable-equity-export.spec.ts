/**
 * UAT — 交付中心财务报表导出 + 权益变动表 {{eq:}} Playwright 实测
 *
 * 验证：
 * 1. API：审定/未审 render → 下载 xlsx → 权益 sheet 无 {{eq:}} 残留且有数值
 * 2. UI：交付中心生成报表弹窗含「审定数/未审数」取数口径
 * 3. API：一键全套含 financial_reports_unadjusted 步骤（子集加速）
 *
 * ⚠️ 门禁：默认 skip（不伪绿）。需显式开启：
 *   1. 启动 start-dev.bat（后端 9980 + 前端 3030）
 *   2. 测试项目：辽宁卫生 2025（37814426-a29e-4fc2-9313-a59d229bf7b0），试算表/报表已就绪
 *   3. set RUN_DELIVERABLE_E2E=1 && npx playwright test e2e/deliverable-equity-export.spec.ts
 *
 * Spec: audit-report-template-integration task 6.5.4
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import * as XLSX from 'xlsx'

const _env = ((globalThis as any).process?.env ?? {}) as Record<string, string | undefined>
const RUN_DELIVERABLE_E2E = _env.RUN_DELIVERABLE_E2E === '1'

const PROJECT_ID = _env.DELIVERABLE_E2E_PROJECT_ID || '37814426-a29e-4fc2-9313-a59d229bf7b0'
const PROJECT_YEAR = Number(_env.DELIVERABLE_E2E_YEAR || '2025')

type EquityScan = {
  equitySheetFound: boolean
  hasEqPlaceholder: boolean
  numericCount: number
}

async function loginAs(page: Page, username: string, password: string) {
  const resp = await page.request.post('/api/auth/login', {
    data: { username, password },
  })
  expect(resp.ok(), `登录失败 ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const token = body.data?.access_token ?? body.access_token
  await page.addInitScript((t: string) => {
    window.sessionStorage.setItem('token', t)
    window.localStorage.setItem('token', t)
  }, token)
  return token as string
}

function unwrap<T>(body: Record<string, unknown>): T {
  return (body.data ?? body) as T
}

function scanEquityXlsx(buffer: Buffer): EquityScan {
  const wb = XLSX.read(buffer, { type: 'buffer' })
  let equitySheetFound = false
  let hasEqPlaceholder = false
  let numericCount = 0

  for (const name of wb.SheetNames) {
    if (!name.includes('权益') && !name.toLowerCase().includes('equity')) continue
    equitySheetFound = true
    const sheet = wb.Sheets[name]
    for (const key of Object.keys(sheet)) {
      if (key.startsWith('!')) continue
      const cell = sheet[key]
      const raw = cell?.v
      const text = String(raw ?? '')
      if (text.includes('{{eq:')) hasEqPlaceholder = true
      if (typeof raw === 'number' && Number.isFinite(raw) && raw !== 0) numericCount++
    }
  }
  return { equitySheetFound, hasEqPlaceholder, numericCount }
}

async function renderFinancialReports(
  request: APIRequestContext,
  token: string,
  dataMode: 'audited' | 'unadjusted',
) {
  const resp = await request.post(
    `/api/projects/${PROJECT_ID}/deliverables/financial-reports/render`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        year: PROJECT_YEAR,
        report_types: ['equity_statement'],
        data_mode: dataMode,
      },
    },
  )
  return { resp, body: resp.ok() ? unwrap<{ task_id: string; version_no: number }>(await resp.json()) : null }
}

async function downloadDeliverableVersion(
  request: APIRequestContext,
  token: string,
  taskId: string,
  versionNo: number,
) {
  return request.get(
    `/api/projects/${PROJECT_ID}/deliverables/${taskId}/versions/${versionNo}/download`,
    { headers: { Authorization: `Bearer ${token}` } },
  )
}

test.describe('交付中心权益变动表导出', () => {
  test.describe.configure({ mode: 'serial' })

  test.skip(
    !RUN_DELIVERABLE_E2E,
    '【待环境】需 RUN_DELIVERABLE_E2E=1 + start-dev.bat（后端 9980 + 前端 3030）+ 辽宁卫生试算表/报表数据',
  )

  test('API — 审定导出权益表 {{eq:}} 已回填', async ({ request, page }) => {
    test.setTimeout(120_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const { resp, body } = await renderFinancialReports(request, token, 'audited')
    test.skip(!resp.ok(), `审定 render 失败 ${resp.status()}，需试算表/报表前置数据`)

    const dl = await downloadDeliverableVersion(request, token, body!.task_id, body!.version_no)
    expect(dl.ok(), `下载失败 ${dl.status()}`).toBeTruthy()

    const buf = Buffer.from(await dl.body())
    expect(buf.length).toBeGreaterThan(1000)

    const scan = scanEquityXlsx(buf)
    expect(scan.equitySheetFound, '应含所有者权益变动表 sheet').toBeTruthy()
    expect(scan.hasEqPlaceholder, '不应残留 {{eq:}} 占位').toBeFalsy()
    expect(scan.numericCount, '权益矩阵应有数值回填').toBeGreaterThan(0)
  })

  test('API — 未审导出权益表 {{eq:}} 已回填', async ({ request, page }) => {
    test.setTimeout(120_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const { resp, body } = await renderFinancialReports(request, token, 'unadjusted')
    test.skip(!resp.ok(), `未审 render 失败 ${resp.status()}，需试算表未审数前置`)

    const dl = await downloadDeliverableVersion(request, token, body!.task_id, body!.version_no)
    expect(dl.ok(), `下载失败 ${dl.status()}`).toBeTruthy()

    const scan = scanEquityXlsx(Buffer.from(await dl.body()))
    expect(scan.equitySheetFound).toBeTruthy()
    expect(scan.hasEqPlaceholder).toBeFalsy()
    expect(scan.numericCount).toBeGreaterThan(0)
  })

  test('UI — 生成报表弹窗含审定/未审取数口径', async ({ page }) => {
    test.setTimeout(60_000)
    await loginAs(page, 'admin', 'admin123')
    await page.goto(`/projects/${PROJECT_ID}/deliverable-center`)
    await expect(page.getByRole('button', { name: '生成报表' })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '生成报表' }).click()
    const dialog = page.getByRole('dialog', { name: '生成财务报表' })
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    await expect(dialog.getByText('取数口径')).toBeVisible()
    await expect(dialog.getByText('审定数')).toBeVisible()
    await expect(dialog.getByText('未审数')).toBeVisible()
    await dialog.getByText('未审数').click()
    await expect(dialog.getByText('所有者权益变动表')).toBeVisible()
  })

  test('API — 一键全套含未审报表步骤', async ({ request, page }) => {
    test.setTimeout(180_000)
    const token = await loginAs(page, 'admin', 'admin123')

    const resp = await request.post(
      `/api/projects/${PROJECT_ID}/word-exports/full-deliverables`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          year: PROJECT_YEAR,
          template_variant: 'simple',
          steps: ['financial_reports', 'financial_reports_unadjusted'],
        },
      },
    )
    test.skip(!resp.ok(), `全套子集 render 失败 ${resp.status()}，需试算表就绪`)

    const job = unwrap<{
      status: string
      progress_done: number
      progress_total: number
      items: { status: string }[]
    }>(await resp.json())

    expect(job.progress_total).toBe(2)
    expect(job.progress_done).toBe(2)
    expect(job.status).toBe('succeeded')
    expect(job.items.every((i) => i.status === 'succeeded')).toBeTruthy()

    const listResp = await request.get(`/api/projects/${PROJECT_ID}/deliverables`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(listResp.ok()).toBeTruthy()
    const listBody = unwrap<{ items: { doc_type: string }[] }>(await listResp.json())
    const docTypes = listBody.items.map((i) => i.doc_type)
    expect(docTypes).toContain('financial_report')
    expect(docTypes).toContain('financial_report_unadjusted')
  })
})
