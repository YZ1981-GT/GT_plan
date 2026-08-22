/** K1 导入导出 — export-template → import-data API 往返 */
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

async function roundTripSheet(
  request: import('@playwright/test').APIRequestContext,
  wpId: string,
  token: string,
  sheet: string,
): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` }

  const tpl = await request.post(
    `/api/workpapers/${wpId}/k1/export-template?sheet=${sheet}`,
    { headers },
  )
  expect(tpl.status(), `${sheet} export-template`).toBe(200)
  const buf = await tpl.body()
  expect(buf.byteLength, `${sheet} template size`).toBeGreaterThan(100)

  const tmpPath = path.join(os.tmpdir(), `K1-${sheet}-e2e-${Date.now()}.xlsx`)
  fs.writeFileSync(tmpPath, buf)

  const imp = await request.post(
    `/api/workpapers/${wpId}/k1/import-data?sheet=${sheet}`,
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

  expect(imp.status(), `${sheet} import-data`).toBe(200)
  const body = await imp.json()
  const data = body?.data ?? body
  expect(data.success ?? data.ok ?? true, `${sheet} import ok`).toBeTruthy()
}

test.describe('K1 导入导出 API 往返', () => {
  test('K1-1 / K1-3 / K1-9 export-template → import-data', async ({ request }) => {
    test.setTimeout(120_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'K1', PROJECT_ID)
    test.skip(!wp.exists, 'K1 底稿不存在')

    for (const sheet of ['K1-1', 'K1-3', 'K1-9'] as const) {
      await roundTripSheet(request, wp.wpId!, token, sheet)
    }
  })

  test('K1-6 / K1-8 模板可导出', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'K1', PROJECT_ID)
    test.skip(!wp.exists, 'K1 底稿不存在')

    const headers = { Authorization: `Bearer ${token}` }
    for (const sheet of ['K1-6', 'K1-8'] as const) {
      const resp = await request.post(
        `/api/workpapers/${wp.wpId}/k1/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(resp.status(), sheet).toBe(200)
    }
  })
})
