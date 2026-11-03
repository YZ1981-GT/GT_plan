/**
 * QC 风险热力图另列未执行 / 检查异常 / 不适用（spec formula-hub-integrity-closure 第 2 轮评审第 2 条，需求 16.5）。
 *
 * 后端热力图的严重级格子只数「失败」（ADR-FHIC-14 第 5 点展示行），其余三种非通过状态记在每行的 status_counts；
 * 原先界面只画三列严重级，检查没跑的项目显示空表与「0 阻断 / 0 警告 / 0 提示」。
 * 数据取后端端点用例 test_consistency_display_snapshots.py 写下的真实响应快照 qc_vr_heatmap.json：
 * 经 QCDashboard 挂载一次（接口打桩成同一份快照，证明页面把响应的 matrix 原样交给热力图），再直接挂载 VRHeatmap。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO = resolve(__dirname, '../../../../../..')
const HEATMAP = JSON.parse(
  readFileSync(resolve(REPO, 'backend/tests/formula_hub/_snapshots/qc_vr_heatmap.json'), 'utf-8'),
)

const { httpGet, stub } = vi.hoisted(() => ({
  httpGet: vi.fn(),
  stub: (name: string) => ({ default: { name, render: () => null } }),
}))
vi.mock('@/utils/http', () => ({ default: { get: httpGet } }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/qcDashboardApi', () => ({
  getQCOverview: vi.fn(async () => null),
  getStaffProgress: vi.fn(async () => ({ staff_progress: [] })),
  getOpenIssues: vi.fn(async () => ({ issues: [], total_open: 0 })),
  getArchiveReadiness: vi.fn(async () => null),
  runArchiveReadinessCheck: vi.fn(async () => null),
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/components/common/GtPageHeader.vue', () => stub('GtPageHeader'))
vi.mock('@/components/qc/VRCoverageTab.vue', () => stub('VRCoverageTab'))

import VRHeatmap from '@/components/qc/VRHeatmap.vue'
import QCDashboard from '@/views/QCDashboard.vue'

const LABEL: Record<string, string> = { not_executed: '未执行（数据缺失）', error: '检查异常', not_applicable: '不适用' }

/** 合计行照旧只数失败；另一行按标签列出三种非通过状态的条数（= 后端顶层 status_counts） */
function assertStatusTotals(w: VueWrapper<any>) {
  expect(w.find('.gt-heatmap-total').text()).toContain(`${HEATMAP.total.blocking} 阻断`)
  const line = w.find('.gt-heatmap-status-total')
  expect(line.exists(), '没有列出未执行 / 检查异常 / 不适用的条数').toBe(true)
  let shown = 0
  for (const [status, label] of Object.entries(LABEL)) {
    const n = HEATMAP.status_counts[status]
    if (n > 0) {
      expect(line.text()).toContain(`${label} ${n} 项`)
      shown += 1
    }
  }
  expect(shown, '快照里没有「失败」以外的非通过项（夹具空转）').toBeGreaterThan(0)
  expect(w.text()).not.toContain('通过')
}

describe('QC 风险热力图：未执行 / 检查异常 / 不适用另计（后端真实响应快照）', () => {
  beforeEach(() => {
    httpGet.mockReset()
  })

  it('质控看板把响应的 matrix 原样交给热力图，热力图列出三种状态的条数', async () => {
    httpGet.mockResolvedValue({ data: HEATMAP })
    const w = mount(QCDashboard, { global: { plugins: [ElementPlus], directives: { permission: {} } } })
    await flushPromises()
    expect(httpGet).toHaveBeenCalledWith('/api/projects/p1/qc/vr-heatmap')
    const heatmap = w.findComponent(VRHeatmap)
    expect(heatmap.exists(), '质控看板没有挂 VRHeatmap').toBe(true)
    assertStatusTotals(heatmap)
    w.unmount()
  })

  it('直接挂载：props 与页面传的一样（响应的 matrix / total）', () => {
    const w = mount(VRHeatmap, {
      props: { matrix: HEATMAP.matrix, total: HEATMAP.total },
      global: { plugins: [ElementPlus] },
    })
    assertStatusTotals(w)
  })

  it('每行都没有非通过的其余三态时不显示该行', () => {
    const matrix = HEATMAP.matrix.map((row: any) => ({
      ...row, status_counts: { ...row.status_counts, not_executed: 0, error: 0, not_applicable: 0 },
    }))
    const w = mount(VRHeatmap, { props: { matrix, total: HEATMAP.total }, global: { plugins: [ElementPlus] } })
    expect(w.find('.gt-heatmap-status-total').exists()).toBe(false)
  })
})
