/**
 * 合伙人项目看板「Blocking VR 汇总」卡片按五态显示（spec formula-hub-integrity-closure 第 2 轮评审第 1 条，需求 16.5）。
 *
 * 数据一律取后端端点用例 test_consistency_display_snapshots.py 写下的真实响应快照，不手写 props：
 * - dashboard_vr_summary.json：五态各一项（with_year）、项目未设置审计年度（without_year）
 * - dashboard_vr_summary_no_failure.json：「0 失败」的四种组合（只有未执行 / 检查异常 / 不适用，以及每项都通过）
 * 卡片用真实 Element Plus 挂载；另经 PartnerProjectDashboard（真实 useDashboardData，接口打桩成同一份快照）挂载一次，
 * 证明页面把接口返回的 vr_summary 原样交给卡片。
 * 判据：未执行 / 检查异常 / 不适用各有标签、条数与原因；只要有一项不是「通过」就不显示「全部通过」；
 * 没运行时写明原因；每项都通过时才显示「全部通过」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO = resolve(__dirname, '../../../../../..')
function snapshot(name: string): any {
  return JSON.parse(readFileSync(resolve(REPO, `backend/tests/formula_hub/_snapshots/${name}.json`), 'utf-8'))
}
const FIVE = snapshot('dashboard_vr_summary')
const NO_FAILURE = snapshot('dashboard_vr_summary_no_failure')

const { get, stub } = vi.hoisted(() => ({
  get: vi.fn(),
  stub: (name: string) => ({ default: { name, render: () => null } }),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'partner' } }) }))
vi.mock('@/components/dashboard/QuickEntryPanel.vue', () => stub('QuickEntryPanel'))
vi.mock('@/components/dashboard/TrimmingOverview.vue', () => stub('TrimmingOverview'))
vi.mock('@/components/dashboard/CycleProgressRing.vue', () => stub('CycleProgressRing'))
vi.mock('@/components/dashboard/ReviewOpinionList.vue', () => stub('ReviewOpinionList'))
vi.mock('@/components/dashboard/ProjectTimeline.vue', () => stub('ProjectTimeline'))

import VRSummaryCard from '@/components/dashboard/VRSummaryCard.vue'
import PartnerProjectDashboard from '@/views/PartnerProjectDashboard.vue'

const LABEL: Record<string, string> = { not_executed: '未执行（数据缺失）', error: '检查异常', not_applicable: '不适用' }

function card(vrSummary: unknown) {
  return mount(VRSummaryCard, { props: { vrSummary: vrSummary as any, error: null }, global: { plugins: [ElementPlus] } })
}

/** 「失败」以外的非通过项逐项带标签、检查名与原因，条数取 status_counts；不显示「全部通过」 */
function assertOtherStates(w: VueWrapper<any>, vr: any) {
  const items = vr.not_passed_checks.filter((c: any) => c.status !== 'failed')
  expect(items.length, '快照里没有「失败」以外的非通过项（夹具空转）').toBeGreaterThan(0)
  const rows = w.findAll('.vr-status-item')
  expect(rows).toHaveLength(items.length)
  items.forEach((c: any, i: number) => {
    expect(rows[i].find('.el-tag').text()).toBe(LABEL[c.status])
    expect(rows[i].text()).toContain(c.check_name)
    expect(c.reason).toBeTruthy()
    expect(rows[i].find('.vr-rule-details').text()).toBe(c.reason)
  })
  const counts = w.find('.vr-status-counts').text()
  for (const [status, label] of Object.entries(LABEL)) {
    const n = vr.status_counts[status]
    if (n > 0) expect(counts).toContain(`${label} ${n} 项`)
    else expect(counts).not.toContain(label)
  }
  expect(w.find('.vr-pass-badge').exists()).toBe(false)
  expect(w.text()).not.toContain('全部通过')
}

describe('看板一致性卡片：五态（后端真实响应快照）', () => {
  it.each(['not_executed', 'error', 'not_applicable'])('0 失败 + %s：不显示「全部通过」，该项带标签、条数与原因', (status) => {
    const vr = NO_FAILURE[status]
    expect([vr.all_passed, vr.blocking_failed, vr.status_counts[status]]).toEqual([false, 0, 1])
    assertOtherStates(card(vr), vr)
  })

  it('五态各一项：失败按循环列出，其余三态各有标签与原因', () => {
    const vr = FIVE.with_year
    const w = card(vr)
    assertOtherStates(w, vr)
    expect(w.find('.vr-cycle-list').text()).toContain('D4勾稽:营业收入合计=主营+其他')
  })

  it('项目未设置审计年度：写明原因，不显示「全部通过」', () => {
    const vr = FIVE.without_year
    expect(vr.unavailable).toBe(true)
    const w = card(vr)
    expect(w.find('.vr-unavailable-reason').text()).toBe('项目未设置审计年度，未运行一致性检查')
    expect(w.text()).not.toContain('全部通过')
  })

  it('每项都通过：才显示「全部通过」', () => {
    const vr = NO_FAILURE.all_passed
    expect(vr.all_passed).toBe(true)
    const w = card(vr)
    expect(w.find('.vr-pass-badge').text()).toBe('全部通过')
    expect(w.find('.vr-status-section').exists()).toBe(false)
  })
})

describe('合伙人项目看板 → 卡片（页面挂载链）', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('页面把接口返回的 vr_summary 原样交给卡片：0 失败 + 未执行不显示「全部通过」', async () => {
    const vr = NO_FAILURE.not_executed
    get.mockResolvedValue({
      project_name: '【测试】看板五态', audit_year: 2025, last_updated: '2026-10-31T06:00:00', cycle_progress: [],
      vr_summary: vr, open_reviews: null, timeline: null, trimming_overview: null, errors: null,
    })
    const w = mount(PartnerProjectDashboard, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/dashboard/summary')
    const c = w.findComponent(VRSummaryCard)
    expect(c.exists(), '页面没有挂 VRSummaryCard').toBe(true)
    assertOtherStates(c, vr)
    w.unmount()
  })
})
