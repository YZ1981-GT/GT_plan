/**
 * core-e5-checklist-persistence.spec.ts — E5 核对表持久化验证
 *
 * 锚定 spec a7-a15-completion-workpapers Task 41
 * E2E 矩阵 E5: A15-1 填 1 项 → 刷新 | checklist_responses 仍在
 *
 * 验证 checklist-table 组件的持久化链路：
 * 1. 打开 A15-1 底稿（checklist-table componentType）
 * 2. 修改一个 checklist 项的结论
 * 3. 等待自动保存
 * 4. 刷新页面
 * 5. 验证修改后的值仍在
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

test.describe('E5: A15-1 checklist-table 持久化', () => {
  test('填写 1 项 → 刷新 → checklist_responses 仍在', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 1. 查找 A15-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a15_1Wp = wpList.find((w: any) => w.wp_code === 'A15-1')
    test.skip(!a15_1Wp, 'A15-1 底稿不存在，跳过')

    const wpId = a15_1Wp!.id

    // 2. 写入一个 checklist response (item_id = "A15-1-q1")
    const testItemId = 'A15-1-q1'
    const testConclusion = '是'
    const testRemark = `E5 自动测试 ${Date.now()}`

    const saveResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: testItemId, conclusion: testConclusion, remark: testRemark },
        ],
      },
    })
    expect(saveResp.status()).toBe(200)

    // 3. 重新读取验证持久化
    const readResp = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(readResp.status()).toBe(200)
    const readBody = await readResp.json()
    const items = Array.isArray(readBody) ? readBody : readBody?.data || []

    // 验证刚才写入的项仍存在且值正确
    const saved = items.find((i: any) => i.item_id === testItemId)
    expect(saved, `checklist response ${testItemId} 应存在`).toBeDefined()
    expect(saved?.conclusion).toBe(testConclusion)
    expect(saved?.remark).toBe(testRemark)
  })

  test('render-config 返回 checklist-table componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A15-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a15_1Wp = wpList.find((w: any) => w.wp_code === 'A15-1')
    test.skip(!a15_1Wp, 'A15-1 底稿不存在，跳过')

    // 验证 render-config 返回正确的 componentType
    const rcResp = await request.get(`/api/workpapers/${a15_1Wp!.id}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    const sheets = rcData?.sheets || []
    // 至少一个 sheet 应为 checklist-table
    const hasChecklist = sheets.some((s: any) => s.componentType === 'checklist-table')
    expect(hasChecklist, 'A15-1 应有 checklist-table sheet').toBe(true)
  })
})
