/**
 * 一致性门禁面板的挂载链（spec formula-hub-integrity-closure 第 2 轮 D-3，需求 16.5）。
 *
 * 唯一宿主链：WorkpaperEditor → WorkpaperSidePanel → CrossCheckPanel → ConsistencyGatePanel。
 * 编辑器把 `projectYear` 传给侧栏由 workpaperSidePanelYear.spec.ts 的源码断言守；本文件挂载真实的
 * WorkpaperSidePanel（其余页签打桩）+ 真实 CrossCheckPanel + 真实 ConsistencyGatePanel，断言门禁面板确实被挂上、
 * 拿到侧栏的 projectId / year，并按它们请求一致性检查展示端点、渲染五态标签。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: () => ({ fmt: String, fmtDateTime: String }) }))
vi.mock('@/composables/useCrossCheck', async () => {
  const { ref, computed } = await import('vue')
  return {
    useCrossCheck: () => ({
      results: ref([]), rules: ref([]), loading: ref(false), executing: ref(false),
      summary: computed(() => ({ total: 0, passed: 0, failed: 0, skipped: 0 })),
      passRate: computed(() => 0), hasBlockingFailures: computed(() => false),
      execute: vi.fn(), fetchResults: vi.fn().mockResolvedValue(undefined), fetchRules: vi.fn().mockResolvedValue(undefined),
    }),
  }
})
function stub(name: string) {
  return { default: defineComponent({ name, props: ['projectId', 'wpId', 'year'], template: '<div />' }) }
}
vi.mock('@/components/workpaper/FormulaStatusPanel.vue', () => stub('FormulaStatusPanel'))
vi.mock('@/components/workpaper/AttachmentTabPanel.vue', () => stub('AttachmentTabPanel'))
vi.mock('@/components/workpaper/ProgramRequirementsSidebar.vue', () => stub('ProgramRequirementsSidebar'))
vi.mock('@/components/workpaper/ProcedurePanel.vue', () => stub('ProcedurePanel'))
vi.mock('@/components/workpaper/DependencyGraph.vue', () => stub('DependencyGraph'))
vi.mock('@/components/workpaper/CellAnnotationPanel.vue', () => stub('CellAnnotationPanel'))
vi.mock('@/components/workpaper/EvidenceLinkPanel.vue', () => stub('EvidenceLinkPanel'))
vi.mock('@/components/workpaper/PbcCollectionTab.vue', () => stub('PbcCollectionTab'))
vi.mock('@/components/workpaper/SnapshotCompare.vue', () => stub('SnapshotCompare'))
vi.mock('@/components/workpaper/WpVersionHistoryPanel.vue', () => stub('WpVersionHistoryPanel'))
vi.mock('@/components/workpaper/QualityScoreBadge.vue', () => stub('QualityScoreBadge'))
vi.mock('@/components/workpaper/WpDecisionTracePanel.vue', () => stub('WpDecisionTracePanel'))

import WorkpaperSidePanel from '@/components/workpaper/WorkpaperSidePanel.vue'
import CrossCheckPanel from '@/components/workpaper/CrossCheckPanel.vue'
import ConsistencyGatePanel from '@/components/workpaper/ConsistencyGatePanel.vue'

// 页签全部直接渲染（真实 el-tabs 懒加载，只渲染当前页签）；与 workpaperSidePanelYear.spec.ts 同一桩
const passthrough = { template: '<div><slot name="label" /><slot /></div>' }
const STUBS = {
  ElTabs: passthrough, ElTabPane: passthrough, ElBadge: true, ElButton: true,
  ElRadioGroup: passthrough, ElRadioButton: true, ElTag: true,
}

describe('ConsistencyGatePanel 挂载链：底稿侧栏 → 跨科目校验 → 一致性门禁', () => {
  it('门禁面板挂在侧栏里，拿到侧栏的项目与年度，按它们请求展示端点并显示五态', async () => {
    get.mockImplementation(async (url: string) => (url.endsWith('/workflow/consistency-check')
      ? { checks: [{ check_name: 'D4勾稽:营业收入合计=主营+其他', passed: false, status: 'not_executed',
        reason: '数据不完整，跳过检查', severity: 'blocking', details: '' }] }
      : {}))
    const wrapper = mount(WorkpaperSidePanel, {
      props: { projectId: 'p-chain', wpId: 'wp1', wpCode: 'D2', year: 2025 },
      global: { stubs: STUBS, directives: { loading: {} } },
    })
    await flushPromises()
    const cross = wrapper.findComponent(CrossCheckPanel)
    expect(cross.exists(), '侧栏里没有挂跨科目校验面板').toBe(true)
    const gate = cross.findComponent(ConsistencyGatePanel)
    expect(gate.exists(), '跨科目校验面板里没有挂一致性门禁面板').toBe(true)
    expect(gate.props('projectId')).toBe('p-chain')
    expect(gate.props('year')).toBe(2025)
    expect(get).toHaveBeenCalledWith('/api/projects/p-chain/workflow/consistency-check', { params: { year: 2025 } })
    expect(gate.findAll('[data-testid="gate-status-label"]').map(n => n.text())[0]).toBe('未执行（数据缺失）')
    expect(gate.text()).toContain('数据不完整，跳过检查')
    wrapper.unmount()
  })
})
