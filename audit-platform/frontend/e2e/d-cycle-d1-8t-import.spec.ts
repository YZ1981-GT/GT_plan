/**
 * d-cycle-d1-8t-import.spec.ts — D1-8T 背书段导入 API 回归
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

test.describe('D1-8T 背书段导入', () => {
  test('export-template → import-data round-trip', async ({ request }) => {
    test.setTimeout(60_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D1', PROJECT_ID)
    test.skip(!wp.exists, 'D1 底稿不存在')

    const headers = { Authorization: `Bearer ${token}` }
    const sheet = 'D1-8T'

    const tpl = await request.post(
      `/api/workpapers/${wp.wpId}/d1/export-template?sheet=${sheet}`,
      { headers },
    )
    expect(tpl.status()).toBe(200)
    const buf = await tpl.body()
    expect(buf.byteLength).toBeGreaterThan(100)

    const tmpPath = path.join(os.tmpdir(), `D1-8T-e2e-${Date.now()}.xlsx`)
    fs.writeFileSync(tmpPath, buf)

    const imp = await request.post(
      `/api/workpapers/${wp.wpId}/d1/import-data?sheet=${sheet}`,
      {
        headers,
        multipart: {
          file: {
            name: 'D1-8T.xlsx',
            mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            buffer: fs.readFileSync(tmpPath),
          },
        },
      },
    )
    fs.unlinkSync(tmpPath)

    expect(imp.status()).toBe(200)
    const body = await imp.json()
    const data = body?.data ?? body
    expect(data.success ?? data.ok ?? true).toBeTruthy()
  })

  test('D1-8 与 D1-8T 模板均可导出', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)
    const wp = await findWorkpaper(request, token, 'D1', PROJECT_ID)
    test.skip(!wp.exists, 'D1 底稿不存在')

    const headers = { Authorization: `Bearer ${token}` }
    for (const sheet of ['D1-8', 'D1-8T'] as const) {
      const resp = await request.post(
        `/api/workpapers/${wp.wpId}/d1/export-template?sheet=${sheet}`,
        { headers },
      )
      expect(resp.status(), sheet).toBe(200)
    }
  })
})
