/**
 * a1731-consultation-execution-e2e.spec.ts — A17-3-1 业务咨询结果执行 E2E 验证
 *
 * Spec: .kiro/specs/a17-3-1-consultation-execution/
 * Task: 5.2
 *
 * 验证项目：
 * 1. 加载 A17-3-1 底稿 → render-config 返回正确结构
 * 2. A17-3 引用数据加载
 * 3. 填写各节 → 保存 → 刷新验证
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

async function findA1731Workpaper(request: APIRequestContext, token: string) {
  const wpResp = await request.get(`${BASE_API}/working-papers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const wpBody = await wpResp.json()
  const wpList =
    wpBody?.data?.items || wpBody?.items || wpBody?.data || (Array.isArray(wpBody) ? wpBody : [])
  return wpList.find((w: any) => w.wp_code === 'A17-3-1')
}

// ─── API 层面验证：render-config 返回正确结构 ────────────────────────────────
test.describe('A17-3-1 E2E: render-config API 验证', () => {
  test('render-config 返回 meta_info + sections + a173_reference + project_context', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wp = await findA1731Workpaper(request, token)
    test.skip(!wp, 'A17-3-1 底稿不存在，跳过')

    const rcResp = await request.get(
      `/api/workpapers/${wp!.id}/render-config?force_component_type=a17-3-1-consultation-execution`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status(), 'render-config 应返回 200').toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    expect(htmlData.meta_info, '应包含 meta_info').toBeTruthy()
    expect(htmlData.sections, '应包含 sections').toBeTruthy()
    expect(htmlData.a173_reference, '应包含 a173_reference').toBeTruthy()
    expect(htmlData.project_context, '应包含 project_context').toBeTruthy()

    // meta_info 包含 4 字段
    const meta = htmlData.meta_info
    expect('executor' in meta, 'meta 应有 executor').toBe(true)
    expect('execution_date' in meta, 'meta 应有 execution_date').toBe(true)
    expect('review_date' in meta, 'meta 应有 review_date').toBe(true)
    expect('reviewer' in meta, 'meta 应有 reviewer').toBe(true)

    // sections 包含 4 章
    const sections = htmlData.sections
    expect(sections['1'], 'section 1 应存在').toBeTruthy()
    expect(sections['2'], 'section 2 应存在').toBeTruthy()
    expect(sections['3'], 'section 3 应存在').toBeTruthy()
    expect(sections['4'], 'section 4 应存在').toBeTruthy()

    // a173_reference 包含 overview + background
    const ref = htmlData.a173_reference
    expect('overview' in ref, 'a173_reference 应有 overview').toBe(true)
    expect('background' in ref, 'a173_reference 应有 background').toBe(true)
  })
})

// ─── 数据持久化验证：写入 → 读回 ────────────────────────────────────────────
test.describe('A17-3-1 E2E: checklist_responses 持久化', () => {
  test('写入各节 + meta → 读回验证 round-trip', async ({ request }) => {
    test.setTimeout(45_000)
    const token = await getToken(request)

    const wp = await findA1731Workpaper(request, token)
    test.skip(!wp, 'A17-3-1 底稿不存在，跳过')

    const wpId = wp!.id

    // 写入 checklist_responses
    const putResp = await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a1731-meta-executor', conclusion: '张三', remark: null },
          { item_id: 'a1731-meta-execution_date', conclusion: '2026-06-20', remark: null },
          { item_id: 'a1731-meta-review_date', conclusion: '2026-06-25', remark: null },
          { item_id: 'a1731-meta-reviewer', conclusion: '李四', remark: null },
          { item_id: 'a1731-sec1-supplementary', conclusion: null, remark: '已参考A17-3原始事项' },
          { item_id: 'a1731-sec2-execution_details', conclusion: null, remark: '按技术部意见调整收入确认' },
          { item_id: 'a1731-sec3-results', conclusion: null, remark: '调整分录已编制' },
          { item_id: 'a1731-sec4-follow_up', conclusion: null, remark: '下期继续关注' },
        ],
      },
    })
    expect(putResp.status(), '写入 checklist 应返回 200').toBe(200)

    // 读回验证
    const rcResp = await request.get(
      `/api/workpapers/${wpId}/render-config?force_component_type=a17-3-1-consultation-execution`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    // 验证 meta round-trip
    expect(htmlData.meta_info.executor).toBe('张三')
    expect(htmlData.meta_info.execution_date).toBe('2026-06-20')
    expect(htmlData.meta_info.review_date).toBe('2026-06-25')
    expect(htmlData.meta_info.reviewer).toBe('李四')

    // 验证各章节 round-trip
    expect(htmlData.sections['1'].supplementary).toBe('已参考A17-3原始事项')
    expect(htmlData.sections['2'].execution_details).toBe('按技术部意见调整收入确认')
    expect(htmlData.sections['3'].results).toBe('调整分录已编制')
    expect(htmlData.sections['4'].follow_up).toBe('下期继续关注')
  })

  test('A17-3 引用数据正确加载', async ({ request }) => {
    test.setTimeout(30_000)
    const token = await getToken(request)

    const wp = await findA1731Workpaper(request, token)
    test.skip(!wp, 'A17-3-1 底稿不存在，跳过')

    const wpId = wp!.id

    // 先写入 A17-3 section 1 数据（模拟已有 A17-3 内容）
    await request.put(`/api/workpapers/${wpId}/checklist-responses`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: PROJECT_ID,
        items: [
          { item_id: 'a173-sec1-overview', conclusion: null, remark: '客户从事软件开发' },
          { item_id: 'a173-sec1-background', conclusion: null, remark: '关于软件收入时点确认' },
        ],
      },
    })

    // 读 A17-3-1 render-config → 应含 a173_reference
    const rcResp = await request.get(
      `/api/workpapers/${wpId}/render-config?force_component_type=a17-3-1-consultation-execution`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(rcResp.status()).toBe(200)

    const rcBody = await rcResp.json()
    const data = rcBody?.data || rcBody
    const htmlData = data?.sheets?.[0]?.html_data || data

    expect(htmlData.a173_reference.overview).toBe('客户从事软件开发')
    expect(htmlData.a173_reference.background).toBe('关于软件收入时点确认')
  })
})
