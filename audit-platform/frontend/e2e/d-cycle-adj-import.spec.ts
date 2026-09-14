/**
 * d-cycle-adj-import.spec.ts — D2-1/D3/D4/D5/D6 审定表与调整分录导入 API 回归
 */
import { test, expect } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { TEST_PROJECT_ID, findWorkpaper } from './fixtures/ensure-test-project'

const PROJECT_ID = TEST_PROJECT_ID

async function getToken(request: import('@playwright/test').APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

async function roundTripImport(
  request: import('@playwright/test').APIRequestContext,
  wpId: string,
  token: string,
  prefix: 'd2' | 'd3' | 'd4' | 'd5' | 'd6',
  sheet: string,
): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` }
  const tpl = await request.post(
    `/api/workpapers/${wpId}/${prefix}/export-template?sheet=${sheet}`,
    { headers },
  )
  expect(tpl.status(), `${prefix} ${sheet} export-template`).toBe(200)
  const buf = await tpl.body()
  expect(buf.byteLength).toBeGreaterThan(100)

  const tmpPath = path.join(os.tmpdir(), `${sheet}-e2e-${Date.now()}.xlsx`)
  fs.writeFileSync(tmpPath, buf)

  const imp = await request.post(
    `/api/workpapers/${wpId}/${prefix}/import-data?sheet=${sheet}`,
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

  expect(imp.status(), `${prefix} ${sheet} import-data`).toBe(200)
  const body = await imp.json()
  const data = body?.data ?? body
  expect(data.success ?? data.ok ?? data.code === 200).toBeTruthy()
}

test.describe('D-cycle 审定表/调整分录 导入 round-trip', () => {
  test('D2-1 审定表', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D2', PROJECT_ID)
    test.skip(!wp.exists, 'D2 底稿不存在')
    await roundTripImport(request, wp.wpId!, token, 'd2', 'D2-1')
  })

  test('D3-1 审定表 + D3-3 调整分录', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D3', PROJECT_ID)
    test.skip(!wp.exists, 'D3 底稿不存在')
    await roundTripImport(request, wp.wpId!, token, 'd3', 'D3-1')
    await roundTripImport(request, wp.wpId!, token, 'd3', 'D3-3')
    await roundTripImport(request, wp.wpId!, token, 'd3', 'D3-4-debit')
  })

  test('D4-1 审定表', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D4', PROJECT_ID)
    test.skip(!wp.exists, 'D4 底稿不存在')
    await roundTripImport(request, wp.wpId!, token, 'd4', 'D4-1')
  })

  test('D5-1 审定表 + D5-3 调整分录', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D5', PROJECT_ID)
    test.skip(!wp.exists, 'D5 底稿不存在')
    await roundTripImport(request, wp.wpId!, token, 'd5', 'D5-1')
    await roundTripImport(request, wp.wpId!, token, 'd5', 'D5-3')
  })

  test('D6-5 关联方 + D6-8 ECL', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D6', PROJECT_ID)
    test.skip(!wp.exists, 'D6 底稿不存在')
    await roundTripImport(request, wp.wpId!, token, 'd6', 'D6-5')
    await roundTripImport(request, wp.wpId!, token, 'd6', 'D6-8')
  })
})
