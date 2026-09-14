/**
 * plus-e15-export-word.spec.ts — E15 export-word 质量验证
 *
 * 锚定 spec a7-a15-completion-workpapers Task 51
 * E2E 矩阵 E15: A8-1 export-word | PRE-2 质量
 *
 * 验证 docx export-word 端点的质量：
 * 1. 导出成功（200 + docx content-type）
 * 2. check-incomplete 端点可用
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
const BASE_API = `/api/projects/${PROJECT_ID}`

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('E15: A8-1 export-word PRE-2 质量', () => {
  test('export-word 端点返回有效 docx', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A8-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a8_1Wp = wpList.find((w: any) => w.wp_code === 'A8-1')
    test.skip(!a8_1Wp, 'A8-1 底稿不存在，跳过')

    // export-word 端点
    const exportResp = await request.get(
      `${BASE_API}/working-papers/${a8_1Wp!.id}/export-word`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(exportResp.status()).toBe(200)
    const ct = exportResp.headers()['content-type'] || ''
    expect(ct).toContain('wordprocessingml.document')
    const body = await exportResp.body()
    expect(body.length).toBeGreaterThan(1000)
  })

  test('check-incomplete 端点可调用', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a8_1Wp = wpList.find((w: any) => w.wp_code === 'A8-1')
    test.skip(!a8_1Wp, 'A8-1 底稿不存在，跳过')

    // check-incomplete 端点
    const checkResp = await request.get(
      `${BASE_API}/working-papers/${a8_1Wp!.id}/export-word/check-incomplete`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(checkResp.status()).toBe(200)
    const checkBody = await checkResp.json()
    const checkData = checkBody?.data || checkBody
    // 应返回 incomplete 数组和 count
    expect(checkData).toHaveProperty('incomplete')
    expect(checkData).toHaveProperty('count')
    expect(Array.isArray(checkData.incomplete)).toBe(true)
  })
})
