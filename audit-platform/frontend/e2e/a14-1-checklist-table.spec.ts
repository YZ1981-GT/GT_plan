/**
 * a14-1-checklist-table.spec.ts — A14-1 内部控制缺陷汇总表 E2E 验证
 *
 * 锚定 spec a14-control-deficiency Task 33–34
 * 验证 A14-1 checklist-table 渲染 + 持久化链路：
 * 1. render-config 返回 checklist-table componentType
 * 2. checklist-responses 端点可写可读（grid 模式：A14-1-row-{nnn}）
 * 3. 多行写入 + 全部读回
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'
const BASE_API = `/api/projects/${PROJECT_ID}`
const WP_CODE = 'A14-1'

async function getToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  const body = await resp.json()
  return body.data?.access_token ?? body.access_token
}

test.describe('A14-1 checklist-table 内部控制缺陷汇总表', () => {
  test('render-config 返回 checklist-table componentType', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A14-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a14_1Wp = wpList.find((w: any) => w.wp_code === WP_CODE)
    test.skip(!a14_1Wp, 'A14-1 底稿不存在，跳过')

    // 验证 render-config 返回正确的 componentType
    const rcResp = await request.get(`/api/workpapers/${a14_1Wp!.id}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    const sheets = rcData?.sheets || []

    // 至少一个 sheet 应为 checklist-table（主 sheet）
    const hasChecklist = sheets.some((s: any) => s.componentType === 'checklist-table')
    expect(hasChecklist, 'A14-1 应有 checklist-table sheet').toBe(true)
  })

  test('checklist-responses 写入 grid 行 → 读取验证', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A14-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a14_1Wp = wpList.find((w: any) => w.wp_code === WP_CODE)
    test.skip(!a14_1Wp, 'A14-1 底稿不存在，跳过')

    const wpId = a14_1Wp!.id

    // 写入一个 grid 行（A14-1 使用 A14-1-row-{nnn} item_id 模式）
    const testItemId = 'A14-1-row-001'
    const testConclusion = '重要缺陷'
    const testRemark = JSON.stringify({
      defect_no: 'DC-001',
      business_unit: '总部',
      process: '财务报告流程',
      description: 'E2E 测试缺陷描述',
      defect_type: '设计',
      affected_accounts: '应收账款',
    })

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

    // 重新读取验证持久化
    const readResp = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(readResp.status()).toBe(200)
    const readBody = await readResp.json()
    const items = Array.isArray(readBody) ? readBody : readBody?.data || []

    // 验证写入的 grid 行存在且值正确
    const saved = items.find((i: any) => i.item_id === testItemId)
    expect(saved, `checklist response ${testItemId} 应存在`).toBeDefined()
    expect(saved?.conclusion).toBe(testConclusion)
    expect(saved?.remark).toBe(testRemark)
  })

  test('checklist-responses 多行写入 + 全部读回', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A14-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a14_1Wp = wpList.find((w: any) => w.wp_code === WP_CODE)
    test.skip(!a14_1Wp, 'A14-1 底稿不存在，跳过')

    const wpId = a14_1Wp!.id
    const rows = [
      { item_id: 'A14-1-row-002', conclusion: '一般缺陷', remark: '{"defect_no":"DC-002"}' },
      { item_id: 'A14-1-row-003', conclusion: '重大缺陷', remark: '{"defect_no":"DC-003"}' },
    ]

    const saveResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: rows,
      },
    })
    expect(saveResp.status()).toBe(200)

    // 读取所有 responses 验证多行持久化
    const readResp = await request.get(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(readResp.status()).toBe(200)
    const readBody = await readResp.json()
    const items = Array.isArray(readBody) ? readBody : readBody?.data || []

    for (const row of rows) {
      const found = items.find((i: any) => i.item_id === row.item_id)
      expect(found, `${row.item_id} 应存在`).toBeDefined()
      expect(found?.conclusion).toBe(row.conclusion)
    }
  })

  test('render-config sheets 含示例 sheet 不为 checklist-table', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    // 查找 A14-1 底稿
    const wpListResp = await request.get(`${BASE_API}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const wpBody = await wpListResp.json()
    const wpList = wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
    const a14_1Wp = wpList.find((w: any) => w.wp_code === WP_CODE)
    test.skip(!a14_1Wp, 'A14-1 底稿不存在，跳过')

    const rcResp = await request.get(`/api/workpapers/${a14_1Wp!.id}/render-config`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(rcResp.status()).toBe(200)
    const rcBody = await rcResp.json()
    const rcData = rcBody?.data || rcBody
    const sheets = rcData?.sheets || []

    // 主 sheet 为 checklist-table
    const mainSheet = sheets.find((s: any) => s.componentType === 'checklist-table')
    expect(mainSheet).toBeDefined()

    // 如果示例 sheet 存在，不应为 checklist-table
    const exampleSheet = sheets.find(
      (s: any) => s.name?.includes('示例') || s.componentType === 'skip' || s.componentType === 'example-skip',
    )
    if (exampleSheet) {
      expect(exampleSheet.componentType).not.toBe('checklist-table')
    }
  })
})
