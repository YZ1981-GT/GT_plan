/**
 * 浏览器检查 ⑤ — 删除公式的并发校验与提示
 *
 * 底稿公式删除强制带版本（ADR-FHIC-11）：不带 428、版本不对 409（中文提示）、对上了才删；删完再删 404。
 * 原用例对不存在的 `DELETE /formula-settings/{id}` 接受 400/403/404/405/409/422 任一 ⇒ 恒绿。
 */
import { test, expect } from '@playwright/test'
import { api, apiToken, requireIsolatedDb, runTag, seedYear } from './helpers'
import { loadManifest } from './manifest'

test.describe('删除冲突提示', () => {
  test('不带版本 428、版本不对 409、对上才删、删完 404', async ({ request }) => {
    const token = await apiToken(request)
    await requireIsolatedDb(request, token)
    const wpId = loadManifest().standalone.wp_ids['D2-1']
    expect(wpId, '种子缺 D2-1 底稿').toBeTruthy()
    const saved = await api(request, token, 'PUT', `/api/workpapers/${wpId}/formulas`, {
      data: { sheet_name: `E2E-${runTag()}`, target_cell: 'C3', expression: '1+1', year: seedYear() },
    })
    expect(saved.status, JSON.stringify(saved.error)).toBe(200)
    const { id, definition_version: version } = saved.data.saved
    expect(Number.isInteger(version)).toBe(true)
    const url = `/api/workpapers/${wpId}/formulas/${id}`

    const noVersion = await api(request, token, 'DELETE', url)
    expect(noVersion.status).toBe(428)
    expect(noVersion.error.error_code).toBe('FORMULA_VERSION_REQUIRED')
    const wrong = await api(request, token, 'DELETE', url, { params: { expected_version: version + 5 } })
    expect(wrong.status).toBe(409)
    expect(wrong.error.error_code).toBe('FORMULA_VERSION_CONFLICT')
    expect(wrong.error.message).toContain('请刷新后重试')

    const ok = await api(request, token, 'DELETE', url, { params: { expected_version: version } })
    expect(ok.status, JSON.stringify(ok.error)).toBe(200)
    expect(ok.data.deleted).toBe(id)
    const gone = await api(request, token, 'DELETE', url, { params: { expected_version: version } })
    expect(gone.status).toBe(404)
  })
})
