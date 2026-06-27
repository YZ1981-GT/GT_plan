/**
 * a173-consultation-record-e2e.spec.ts — A17-3 业务咨询记录 E2E 验证
 *
 * Spec: .kiro/specs/a17-3-consultation-record/
 * Task: 5.2
 *
 * 验证项目：
 * 1. 加载 A17-3 底稿 → render-config 返回正确结构
 * 2. 4 章节数据完整
 * 3. 添加文件 tag → round-trip 验证
 * 4. 设置咨询类型 → round-trip 验证
 * 5. 填写各章节 → 保存 → 刷新验证
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

async function findA173Workpaper(request: APIRequestContext, token: string) {
  const wpResp = await request.get(`${BASE_API}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const wpBody = await wpResp.json()
  const wpList =
    wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
  return wpList.find((w: any) => w.wp_code === 'A17-3')
}

// ─── API 层面验证：render-config 返回正确结构 ────────────────────────────────
test.describe('A17-3 E2E: render-config API 验证', () => {
  test('render-config 返回 meta_info + sections + project_context', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const a173Wp = await findA173Workpaper(request, token)
    test.skip(!a173Wp, 'A17-3 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${a173Wp!.id}/render-config?force_component_type=a17-3-consultation-record`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status(), 'render-config 应返回 200').toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    expect(htmlData.meta_info, '应包含 meta_info').toBeTruthy()
    expect(htmlData.sections, '应包含 sections').toBeTruthy()
    expect(htmlData.project_context, '应包含 project_context').toBeTruthy()

    // meta_info 包含 4 字段
    const meta = htmlData.meta_info
    expect('department' in meta, 'meta 应有 department').toBe(true)
    expect('client_name' in meta, 'meta 应有 client_name').toBe(true)
    expect('consult_type' in meta, 'meta 应有 consult_type').toBe(true)
    expect('period' in meta, 'meta 应有 period').toBe(true)

    // sections 包含 4 章
    const sections = htmlData.sections
    expect(sections['1'], 'section 1 应存在').toBeTruthy()
    expect(sections['2'], 'section 2 应存在').toBeTruthy()
    expect(sections['3'], 'section 3 应存在').toBeTruthy()
    expect(sections['4'], 'section 4 应存在').toBeTruthy()

    // section 1 files is array
    expect(Array.isArray(sections['1'].files), 'section 1 files 应为数组').toBe(true)
  })
})

// ─── 数据持久化验证：写入 → 读回 ────────────────────────────────────────────
test.describe('A17-3 E2E: checklist_responses 持久化', () => {
  test('写入文件 tag + 咨询类型 + 各章节 → 读回验证 round-trip', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)

    const a173Wp = await findA173Workpaper(request, token)
    test.skip(!a173Wp, 'A17-3 底稿不存在，跳过')

    const wpId = a173Wp!.id

    // 写入 checklist_responses
    const putResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a173-meta-department', conclusion: '审计一部', remark: null },
          { item_id: 'a173-meta-consult_type', conclusion: '会计处理', remark: null },
          { item_id: 'a173-sec1-overview', conclusion: null, remark: '客户从事制造业' },
          { item_id: 'a173-sec1-background', conclusion: null, remark: '收入确认时点问题' },
          { item_id: 'a173-sec1-files', conclusion: '2', remark: '["合同.pdf","邮件记录.eml"]' },
          { item_id: 'a173-sec2-opinion', conclusion: null, remark: '项目组认为应按时点确认' },
          { item_id: 'a173-sec3-standards', conclusion: null, remark: 'CAS 14第10条' },
          { item_id: 'a173-sec3-reply', conclusion: null, remark: '同意项目组意见' },
          { item_id: 'a173-sec4-opinion', conclusion: null, remark: '技术委员会批准' },
        ],
      },
    })
    expect(putResp.status(), '写入 checklist 应返回 200').toBe(200)

    // 读回验证
    const rcResp = await request.get(
      `/api/workpapers/${wpId}/render-config?force_component_type=a17-3-consultation-record`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证 meta round-trip
    expect(htmlData.meta_info.department).toBe('审计一部')
    expect(htmlData.meta_info.consult_type).toBe('会计处理')

    // 验证文件 tag round-trip
    expect(htmlData.sections['1'].files).toEqual(['合同.pdf', '邮件记录.eml'])

    // 验证各章节
    expect(htmlData.sections['1'].overview).toBe('客户从事制造业')
    expect(htmlData.sections['1'].background).toBe('收入确认时点问题')
    expect(htmlData.sections['2'].opinion).toBe('项目组认为应按时点确认')
    expect(htmlData.sections['3'].standards).toBe('CAS 14第10条')
    expect(htmlData.sections['3'].reply).toBe('同意项目组意见')
    expect(htmlData.sections['4'].opinion).toBe('技术委员会批准')
  })
})
