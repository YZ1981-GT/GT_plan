/**
 * G7-13 投资成本测试 Round-Trip（API）
 * 登录 → 解析 G7 wp → PUT 扁平 rows → GET 回显 → 导出模板 200 → 清理
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = process.env.E2E_PROJECT_ID || '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'
const ROWS_KEY = 'G7-13-rows'
const CONCLUSION_KEY = 'G7-13-conclusion'
const MARKER = `G713-RT-${Date.now()}`

test.setTimeout(90_000)

async function login(page: Page): Promise<string> {
  let response
  for (let attempt = 0; attempt < 3; attempt += 1) {
    response = await page.request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (response.ok()) break
    await new Promise(r => setTimeout(r, 1000))
  }
  expect(response?.ok(), `登录应成功 status=${response?.status()}`).toBeTruthy()
  const body = await response!.json()
  const token = body.data?.access_token ?? body.access_token
  expect(token, '应返回 access_token').toBeTruthy()
  await page.addInitScript((value: string) => {
    sessionStorage.setItem('token', value)
    localStorage.setItem('token', value)
  }, token)
  return token as string
}

async function resolveG7MethodWpId(request: APIRequestContext, token: string): Promise<string> {
  const envWp = process.env.E2E_G7_METHOD_WP_ID || process.env.E2E_G7_WP_ID
  if (envWp) return envWp

  for (let page = 1; page <= 20; page += 1) {
    const res = await request.get(`/api/projects/${PROJECT_ID}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { page, page_size: 100 },
    })
    expect(res.ok(), `working-papers page=${page} 应成功`).toBeTruthy()
    const body = await res.json()
    const data = body?.data ?? body
    const list: any[] = Array.isArray(data) ? data : (data?.items ?? [])
    if (!list.length) break
    const hit = list.find((w: any) => {
      const code = String(w.wp_code || '')
      const name = String(w.wp_name || w.name || '')
      const ctype = String(w.component_type || w.componentType || '').toLowerCase()
      return code === 'G7'
        || code.startsWith('G7-')
        || name.includes('权益法')
        || ctype.includes('equity-method')
    })
    if (hit) return String(hit.wp_id ?? hit.id)
  }

  for (const code of ['G7', 'G7-13', 'G7-14']) {
    const hit = await findWorkpaper(request, token, code, PROJECT_ID)
    if (hit.exists && hit.wpId) return hit.wpId
  }
  throw new Error(`未找到 G7/权益法底稿 project=${PROJECT_ID}`)
}

async function checklistItem(
  request: APIRequestContext,
  token: string,
  wpId: string,
  itemId: string,
): Promise<any | undefined> {
  const response = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok(), 'checklist GET 应成功').toBeTruthy()
  const body = await response.json()
  const data = body?.data ?? body
  const items = Array.isArray(data) ? data : (data?.items ?? [])
  return items.find((item: any) => item.item_id === itemId)
}

function parseRows(item: any): any[] {
  const raw = item?.conclusion ?? item?.remark
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
  } catch { /* ignore */ }
  return []
}

test.describe('G7-13 投资成本测试 Round-Trip', () => {
  test('扁平 rows 落库+回显+导出模板', async ({ page, request }) => {
    const token = await login(page)
    let wpId: string
    try {
      wpId = await resolveG7MethodWpId(request, token)
    } catch (e) {
      test.skip(true, `跳过：${String(e)}`)
      return
    }

    const before = await checklistItem(request, token, wpId, ROWS_KEY)
    const beforeRows = parseRows(before)
    const sampleRow = {
      id: `g713-${MARKER}`,
      seq: 1,
      investeeName: MARKER,
      investeeId: 'e2e-g713',
      investDate: '2024-01-01',
      mergeType: '非合并',
      consideration: 800,
      directCosts: 50,
      initialCost: 850,
      netAssetFairValue: 4000,
      shareOfNetAssets: 1200,
      difference: -350,
      differenceNature: '营业外收入',
      accountingTreatment: '',
      fvAdjustmentDetail: '',
      adjustedNetAssets: 0,
      adjustedShareOfNetAssets: 0,
      investmentRatio: 0.3,
      auditConclusion: '无差异',
      indexRef: 'G7-13',
    }
    const flat = JSON.stringify([sampleRow])
    const envelope = JSON.stringify({ rows: [sampleRow], conclusion: `E2E ${MARKER}` })

    const putRes = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: ROWS_KEY, conclusion: flat, remark: envelope },
          { item_id: CONCLUSION_KEY, conclusion: `E2E ${MARKER}`, remark: null },
        ],
      },
    })
    expect(putRes.ok(), `PUT 应成功 status=${putRes.status()}`).toBeTruthy()

    const after = await checklistItem(request, token, wpId, ROWS_KEY)
    const afterRows = parseRows(after)
    const hit = afterRows.find((r: any) => r.investeeName === MARKER || r.id === sampleRow.id)
    expect(hit, '应回显 G7-13 测试行').toBeTruthy()
    expect(Number(hit.difference)).toBe(-350)
    expect(Number(hit.investmentRatio)).toBe(0.3)

    const exportRes = await request.post(
      `/api/workpapers/${wpId}/g7-equity-method/export-template?sheet=G7-13`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(exportRes.status(), '导出模板应 200').toBe(200)

    // 清理：恢复写入前内容（无则清空标记行）
    const restore = beforeRows.filter((r: any) => r.investeeName !== MARKER && r.id !== sampleRow.id)
    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [{
          item_id: ROWS_KEY,
          conclusion: JSON.stringify(restore),
          remark: before?.remark ?? null,
        }],
      },
    })
  })
})
