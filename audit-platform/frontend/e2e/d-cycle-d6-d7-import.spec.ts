/**
 * d-cycle-d6-d7-import.spec.ts — D6-2 / D7-2 / D7-7 导入 API 回归
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
  prefix: 'd6' | 'd7',
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
  expect(data.success ?? data.ok ?? true).toBeTruthy()
}

test.describe('D6/D7 导入 round-trip', () => {
  test('D6-2 export-template → import-data', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D6', PROJECT_ID)
    test.skip(!wp.exists, 'D6 底稿不存在')
    await roundTripImport(request, wp.wpId, token, 'd6', 'D6-2')
  })

  test('D7-2 export-template → import-data', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D7', PROJECT_ID)
    test.skip(!wp.exists, 'D7 底稿不存在')
    await roundTripImport(request, wp.wpId, token, 'd7', 'D7-2')
  })

  test('D7-7-period export-template → import-data', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D7', PROJECT_ID)
    test.skip(!wp.exists, 'D7 底稿不存在')
    await roundTripImport(request, wp.wpId, token, 'd7', 'D7-7-period')
  })
})
