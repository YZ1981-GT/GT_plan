/**
 * a174-disagreement-record-e2e.spec.ts — A17-4 重大专业分歧事项记录 E2E 验证
 *
 * Spec: .kiro/specs/a17-4-disagreement-record/
 * Task: 5.2
 *
 * 验证项目：
 * 1. render-config 返回正确结构 (personnel + sections + signature_data + project_context)
 * 2. 添加人员 → round-trip 验证
 * 3. 填写 6 章节 → 保存 → 刷新验证
 * 4. 签字区 → round-trip 验证
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

async function findA174Workpaper(request: APIRequestContext, token: string) {
  const wpResp = await request.get(`${BASE_API}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const wpBody = await wpResp.json()
  const wpList =
    wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
  return wpList.find((w: any) => w.wp_code === 'A17-4')
}

// ─── API 层面验证：render-config 返回正确结构 ────────────────────────────────
test.describe('A17-4 E2E: render-config API 验证', () => {
  test('render-config 返回 personnel + sections + signature_data + project_context', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const a174Wp = await findA174Workpaper(request, token)
    test.skip(!a174Wp, 'A17-4 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${a174Wp!.id}/render-config?force_component_type=a17-4-disagreement-record`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status(), 'render-config 应返回 200').toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // Structure validation
    expect(htmlData.personnel, '应包含 personnel').toBeDefined()
    expect(Array.isArray(htmlData.personnel), 'personnel 应为数组').toBe(true)
    expect(htmlData.sections, '应包含 sections').toBeTruthy()
    expect(htmlData.signature_data, '应包含 signature_data').toBeTruthy()
    expect(htmlData.project_context, '应包含 project_context').toBeTruthy()

    // sections 包含 6 章
    const sections = htmlData.sections
    for (const num of ['1', '2', '3', '4', '5', '6']) {
      expect(sections[num], `section ${num} 应存在`).toBeTruthy()
    }

    // signature_data 包含 3 字段
    const sig = htmlData.signature_data
    expect('preparer' in sig, 'signature 应有 preparer').toBe(true)
    expect('reviewer' in sig, 'signature 应有 reviewer').toBe(true)
    expect('date' in sig, 'signature 应有 date').toBe(true)
  })
})

// ─── 数据持久化验证：写入 → 读回 ────────────────────────────────────────────
test.describe('A17-4 E2E: checklist_responses 持久化', () => {
  test('写入人员 + 6 章节 + 签字 → 读回验证 round-trip', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)

    const a174Wp = await findA174Workpaper(request, token)
    test.skip(!a174Wp, 'A17-4 底稿不存在，跳过')

    const wpId = a174Wp!.id

    // 写入 checklist_responses
    const personnel = [
      { name: '张三', position: '审计经理', role: '项目负责人' },
      { name: '李四', position: '高级审计师', role: '现场负责人' },
    ]

    const putResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a174-personnel', conclusion: '2', remark: JSON.stringify(personnel) },
          { item_id: 'a174-sec1-parties', conclusion: null, remark: '张三与李四对收入确认方式存在分歧' },
          { item_id: 'a174-sec2-cause', conclusion: null, remark: '合同修改后收入确认时点问题' },
          { item_id: 'a174-sec3-procedures', conclusion: null, remark: '已完成函证和截止测试' },
          { item_id: 'a174-sec4-opinions', conclusion: null, remark: '监管部门未发表意见' },
          { item_id: 'a174-sec5-considerations', conclusion: null, remark: '合伙人倾向按时段确认' },
          { item_id: 'a174-sec6-conclusion', conclusion: null, remark: '最终决定按时点确认' },
          { item_id: 'a174-signature-preparer', conclusion: '编制人A', remark: null },
          { item_id: 'a174-signature-reviewer', conclusion: '复核人B', remark: null },
          { item_id: 'a174-signature-date', conclusion: '2026-06-25', remark: null },
        ],
      },
    })
    expect(putResp.status(), '写入 checklist 应返回 200').toBe(200)

    // 读回验证
    const rcResp = await request.get(
      `/api/workpapers/${wpId}/render-config?force_component_type=a17-4-disagreement-record`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证人员 round-trip
    expect(htmlData.personnel).toHaveLength(2)
    expect(htmlData.personnel[0].name).toBe('张三')
    expect(htmlData.personnel[0].position).toBe('审计经理')
    expect(htmlData.personnel[1].name).toBe('李四')
    expect(htmlData.personnel[1].role).toBe('现场负责人')

    // 验证 6 章节 round-trip
    expect(htmlData.sections['1'].parties).toBe('张三与李四对收入确认方式存在分歧')
    expect(htmlData.sections['2'].cause).toBe('合同修改后收入确认时点问题')
    expect(htmlData.sections['3'].procedures).toBe('已完成函证和截止测试')
    expect(htmlData.sections['4'].opinions).toBe('监管部门未发表意见')
    expect(htmlData.sections['5'].considerations).toBe('合伙人倾向按时段确认')
    expect(htmlData.sections['6'].conclusion).toBe('最终决定按时点确认')

    // 验证签字 round-trip
    expect(htmlData.signature_data.preparer).toBe('编制人A')
    expect(htmlData.signature_data.reviewer).toBe('复核人B')
    expect(htmlData.signature_data.date).toBe('2026-06-25')
  })
})
