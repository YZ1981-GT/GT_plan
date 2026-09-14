/**
 * a177-independence-declaration-e2e.spec.ts — A17-7 独立性声明书 E2E 验证
 *
 * Spec: .kiro/specs/a17-7-independence-declaration/
 * Task: 5.2
 *
 * 验证项目：
 * 1. 加载 A17-7 → render-config 返回正确结构 (9 top-level keys)
 * 2. 验证 variant='team' + team pre-fill
 * 3. 添加签字行 → round-trip 验证
 * 4. 填写期间日期 → round-trip 验证
 * 5. 设置合伙人确认 Y → round-trip 验证
 * 6. 添加威胁记录行 → round-trip 验证
 * 7. 切换到 A17-7A → 验证 variant='committee' + 不同前缀
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

async function findWorkpaperByCode(request: APIRequestContext, token: string, wpCode: string) {
  const wpResp = await request.get(`${BASE_API}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const wpBody = await wpResp.json()
  const wpList =
    wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
  return wpList.find((w: any) => w.wp_code === wpCode)
}

// ─── API 层面验证：A17-7 render-config 返回正确结构 ──────────────────────────
test.describe('A17-7 E2E: render-config API 验证', () => {
  test('render-config 返回 9 top-level keys (team variant)', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wp = await findWorkpaperByCode(request, token, 'A17-7')
    test.skip(!wp, 'A17-7 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${wp!.id}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status(), 'render-config 应返回 200').toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证 9 top-level keys
    expect(htmlData.variant, '应包含 variant').toBeDefined()
    expect(htmlData.meta_info, '应包含 meta_info').toBeTruthy()
    expect(htmlData.declaration_text, '应包含 declaration_text').toBeTruthy()
    expect(htmlData.period_data, '应包含 period_data').toBeTruthy()
    expect(htmlData.team_sign_table, '应包含 team_sign_table').toBeDefined()
    expect(htmlData.partner_section, '应包含 partner_section').toBeTruthy()
    expect(htmlData.threat_records, '应包含 threat_records').toBeTruthy()
    expect(htmlData.guidance_notes, '应包含 guidance_notes').toBeTruthy()
    expect(htmlData.project_context, '应包含 project_context').toBeTruthy()

    // variant = team (A17-7)
    expect(htmlData.variant).toBe('team')

    // team_sign_table 应为数组
    expect(Array.isArray(htmlData.team_sign_table)).toBe(true)

    // guidance_notes 5 条
    expect(htmlData.guidance_notes).toHaveLength(5)

    // threat_records 有 3 个 key
    expect(Object.keys(htmlData.threat_records)).toEqual(
      expect.arrayContaining(['economic_interest', 'loan_guarantee', 'business_relation']),
    )
  })

  test('team pre-fill: team_sign_table 从 project assignments 预填', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wp = await findWorkpaperByCode(request, token, 'A17-7')
    test.skip(!wp, 'A17-7 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${wp!.id}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // project_context.team_members 应有成员
    const members = htmlData.project_context?.team_members || []
    // If pre-fill happened, sign table should match members count
    if (members.length > 0) {
      expect(htmlData.team_sign_table.length).toBeGreaterThanOrEqual(members.length)
    }
  })
})

// ─── 数据持久化验证：写入 → 读回 ────────────────────────────────────────────
test.describe('A17-7 E2E: checklist_responses 持久化', () => {
  test('写入期间 + 签字 + 合伙人 + 威胁 → 读回验证 round-trip', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)

    const wp = await findWorkpaperByCode(request, token, 'A17-7')
    test.skip(!wp, 'A17-7 底稿不存在，跳过')

    const wpId = wp!.id

    // 写入 checklist_responses
    const putResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a177-period-business-start', conclusion: null, remark: '2025-01-01' },
          { item_id: 'a177-period-business-end', conclusion: null, remark: '2025-12-31' },
          { item_id: 'a177-period-report-start', conclusion: null, remark: '2025-01-01' },
          { item_id: 'a177-period-report-end', conclusion: null, remark: '2025-12-31' },
          { item_id: 'a177-sign-1', conclusion: null, remark: JSON.stringify({ name: '张三', signed: true, date: '2025-06-01' }) },
          { item_id: 'a177-sign-2', conclusion: null, remark: JSON.stringify({ name: '李四', signed: false, date: null }) },
          { item_id: 'a177-partner-confirmed', conclusion: 'Y', remark: null },
          { item_id: 'a177-partner-sign', conclusion: null, remark: JSON.stringify({ name: '王五', date: '2025-06-15' }) },
          { item_id: 'a177-manager-sign', conclusion: null, remark: JSON.stringify({ name: '赵六', date: '2025-06-15' }) },
          { item_id: 'a177-threat-economic-1', conclusion: null, remark: JSON.stringify({ member: '张三', type: '股票', amount: '10万', measure: '已处置' }) },
        ],
      },
    })
    expect(putResp.status(), '写入 checklist 应返回 200').toBe(200)

    // 读回验证
    const rcResp = await request.get(
      `/api/workpapers/${wpId}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证期间 round-trip
    expect(htmlData.period_data.business_start).toBe('2025-01-01')
    expect(htmlData.period_data.business_end).toBe('2025-12-31')
    expect(htmlData.period_data.report_start).toBe('2025-01-01')
    expect(htmlData.period_data.report_end).toBe('2025-12-31')

    // 验证签字表 round-trip
    expect(htmlData.team_sign_table.length).toBeGreaterThanOrEqual(2)
    const sign1 = htmlData.team_sign_table.find((r: any) => r.name === '张三')
    expect(sign1).toBeTruthy()
    expect(sign1!.signed).toBe(true)

    // 验证合伙人 round-trip
    expect(htmlData.partner_section.confirmed).toBe(true)
    expect(htmlData.partner_section.partner_sign.name).toBe('王五')
    expect(htmlData.partner_section.manager_sign.name).toBe('赵六')

    // 验证威胁记录 round-trip
    expect(htmlData.threat_records.economic_interest.length).toBeGreaterThanOrEqual(1)
    expect(htmlData.threat_records.economic_interest[0].member).toBe('张三')
    expect(htmlData.threat_records.economic_interest[0].measure).toBe('已处置')
  })
})

// ─── A17-7A variant 验证 ─────────────────────────────────────────────────────
test.describe('A17-7A E2E: committee variant', () => {
  test('A17-7A 返回 variant=committee + a177a- prefix 隔离', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wp = await findWorkpaperByCode(request, token, 'A17-7A')
    test.skip(!wp, 'A17-7A 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${wp!.id}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证 committee variant
    expect(htmlData.variant).toBe('committee')

    // 验证声明正文不同于 team
    expect(htmlData.declaration_text).toContain('专业技术委员会')
  })

  test('A17-7A 写入 a177a- prefix → 不影响 A17-7 的 a177- 数据', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)

    const wp7a = await findWorkpaperByCode(request, token, 'A17-7A')
    test.skip(!wp7a, 'A17-7A 底稿不存在，跳过')

    const wp7 = await findWorkpaperByCode(request, token, 'A17-7')
    test.skip(!wp7, 'A17-7 底稿不存在，跳过')

    // 向 A17-7A 写入 a177a- 前缀数据
    const putResp = await request.put(`/api/workpapers/${wp7a!.id}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a177a-period-business-start', conclusion: null, remark: '2025-03-01' },
        ],
      },
    })
    expect(putResp.status()).toBe(200)

    // 读回 A17-7A → 验证 a177a- 数据
    const rcResp7a = await request.get(
      `/api/workpapers/${wp7a!.id}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const rcBody7a = await rcResp7a.json()
    const data7a = rcBody7a?.data || rcBody7a
    const html7a = data7a?.sheets?.[0]?.html_data || data7a
    expect(html7a.period_data.business_start).toBe('2025-03-01')

    // 读回 A17-7 → 验证 a177- 数据不受影响
    const rcResp7 = await request.get(
      `/api/workpapers/${wp7!.id}/render-config?force_component_type=a17-7-independence-declaration`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const rcBody7 = await rcResp7.json()
    const data7 = rcBody7?.data || rcBody7
    const html7 = data7?.sheets?.[0]?.html_data || data7
    // A17-7 的 period 不应是 2025-03-01（隔离验证）
    if (html7.period_data.business_start) {
      expect(html7.period_data.business_start).not.toBe('2025-03-01')
    }
  })
})
