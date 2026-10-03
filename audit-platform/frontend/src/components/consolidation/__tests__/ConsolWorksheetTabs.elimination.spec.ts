/**
 * 合并工作底稿 → 合并抵消分录明细表的接线（spec consol-elimination-single-source-push 任务 10.2 / 需求 1.1、2、9.2）
 *
 * - 明细表拿到的是项目 / 年度 + 三类来源的待生成分组（已保存的内部往来 / 内部交易行被恢复并参与计算）；
 * - 只声明「有已保存数据或本次算出分组」的来源；保存某张表后它变为负责来源；
 * - 不再恢复旧版 elimination JSON、不再逐行同步到分录表（不调任何分录写接口）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { saved, apiProxy, wsApi } = vi.hoisted(() => ({
  saved: { value: {} as Record<string, any> },
  apiProxy: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  wsApi: { saveWorksheetData: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p-g' }, query: { year: '2025' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: apiProxy, apiProxy, default: apiProxy }))
vi.mock('@/services/consolidationApi', () => ({
  getConsolScope: vi.fn().mockResolvedValue([
    { company_code: 'A', company_name: '甲公司', is_included: true, ownership_ratio: 100 },
  ]),
  getWorksheetTree: vi.fn().mockResolvedValue({
    tree: { company_code: 'G', company_name: '某集团', children: [] }, mode: 'subsidiary', diagnostics: [], year: 2025,
  }),
}))
vi.mock('@/services/consolWorksheetDataApi', () => ({
  loadAllWorksheetData: vi.fn(() => Promise.resolve(saved.value)),
  saveWorksheetData: (...a: any[]) => wsApi.saveWorksheetData(...a),
  loadWorksheetData: vi.fn().mockResolvedValue({}),
  previewG7Linkage: vi.fn(),
  importG7Linkage: vi.fn(),
}))
vi.mock('@/components/workpaper/composables/g7ConsolLinkageEntry', async () => {
  const { ref } = await import('vue')
  return { useG7ConsolLinkageEntry: () => ({ stale: ref(false), staleSheets: ref([]), refreshStale: vi.fn() }) }
})
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), onFileSelected: vi.fn() }),
}))

import ConsolWorksheetTabs from '../worksheets/ConsolWorksheetTabs.vue'

/** 明细表替身：记下拿到的 props（按来源分组与负责来源） */
const ElimStub = defineComponent({
  name: 'EliminationSheet',
  props: ['projectId', 'year', 'sourceGroups', 'sourceOrigins'],
  setup() { return () => h('div', { 'data-testid': 'elim-stub' }) },
})
/** 内部往来表替身：可以触发保存与行变化 */
const ArApStub = defineComponent({
  name: 'InternalArApSheet',
  props: ['companies', 'initialRows'],
  emits: ['save', 'rows-changed', 'open-formula'],
  setup() { return () => h('div', { 'data-testid': 'arap-stub' }) },
})
const Pass = defineComponent({ setup(_, { slots }) { return () => h('div', [slots.default?.(), slots.title?.()]) } })

function mountTabs() {
  return mount(ConsolWorksheetTabs, {
    global: {
      stubs: {
        EliminationSheet: ElimStub, InternalArApSheet: ArApStub,
        SubsidiaryInfoSheet: true, InvestmentCostSheet: true, InvestmentEquitySheet: true, NetAssetSheet: true,
        EquitySimSheet: true, CapitalReserveSheet: true, ShareChangeSheet: true, PostElimInvestSheet: true,
        PostElimIncomeSheet: true, MinorityInterestSheet: true, InternalTradeSheet: true, InternalCashFlowSheet: true,
        G7SuggestionDraftSheet: true,
        'el-alert': Pass, 'el-tooltip': Pass, 'el-tag': Pass, 'el-icon': Pass, 'el-button': Pass, 'el-dropdown': Pass,
        'el-dropdown-menu': Pass, 'el-dropdown-item': Pass, 'el-dialog': true, 'el-descriptions': true,
        'el-descriptions-item': true, 'el-table': true, 'el-table-column': true, 'el-select': true, 'el-option': true,
        'el-checkbox': true, 'el-checkbox-group': true, 'el-switch': true,
      },
    },
  })
}

async function openSheet(wrapper: ReturnType<typeof mountTabs>, key: string) {
  ;(wrapper.vm as any).$.setupState.activeSheet = key
  await flushPromises()
}

const ARAP_ROWS = [{
  localCompany: '甲公司', localSubject: '应收账款', localAmounts: [10], localImpairments: [],
  remoteCompany: '母公司', remoteSubject: '应付账款', remoteAmounts: [10], remoteImpairments: [],
}]

describe('ConsolWorksheetTabs → 合并抵消分录明细表', () => {
  beforeEach(() => {
    Object.values(apiProxy).forEach((f) => f.mockReset())
    wsApi.saveWorksheetData.mockReset().mockResolvedValue(true)
    saved.value = {}
  })

  it('已保存的内部往来行被恢复：明细表拿到其分组，且只声明有数据的来源；旧版 elimination JSON 不再恢复', async () => {
    saved.value = {
      internal_arap: { rows: ARAP_ROWS },
      elimination: { rows: [{ _custom: true, source: '', direction: '借', subject: '应付账款', amount: 99 }] },
    }
    const wrapper = mountTabs()
    await flushPromises()
    await openSheet(wrapper, 'elimination')
    const elim = wrapper.findComponent(ElimStub)
    expect(elim.props('projectId')).toBe('p-g')
    expect(elim.props('year')).toBe(2025)
    expect(elim.props('sourceGroups').map((g: any) => g.origin_key)).toEqual(['internal_arap:pair:应收账款|应付账款'])
    expect(elim.props('sourceGroups')[0].related_company_codes).toEqual(['A', 'G'])
    // elimination 有已保存数据但不是来源表；没保存过的模拟权益法 / 内部交易不声明负责
    expect(elim.props('sourceOrigins')).toEqual(['ws_internal_arap'])
    // 恢复的行也交给内部往来表
    await openSheet(wrapper, 'internal_arap')
    expect(wrapper.findComponent(ArApStub).props('initialRows')).toEqual(ARAP_ROWS)
    // 不走任何分录写接口（旧 _syncEliminationEntries 已删除）
    expect(apiProxy.post).not.toHaveBeenCalled()
    expect(apiProxy.delete).not.toHaveBeenCalled()
  })

  it('编辑内部往来表 ⇒ 待生成分组随之变化；表被清空后，只有保存过才声明负责（才会删旧草稿）', async () => {
    const wrapper = mountTabs()
    await flushPromises()
    await openSheet(wrapper, 'internal_arap')
    wrapper.findComponent(ArApStub).vm.$emit('rows-changed', ARAP_ROWS)
    await flushPromises()
    await openSheet(wrapper, 'elimination')
    let elim = wrapper.findComponent(ElimStub)
    expect(elim.props('sourceGroups')).toHaveLength(1)
    expect(elim.props('sourceOrigins')).toEqual(['ws_internal_arap'])

    // 清空表格但未保存：数据未知 ⇒ 不声明（不能据此删掉它以前生成的草稿）
    await openSheet(wrapper, 'internal_arap')
    wrapper.findComponent(ArApStub).vm.$emit('rows-changed', [])
    await flushPromises()
    await openSheet(wrapper, 'elimination')
    expect(wrapper.findComponent(ElimStub).props('sourceOrigins')).toEqual([])

    // 保存空表：该表数据已知且为空 ⇒ 声明负责，后端据此删除其草稿
    await openSheet(wrapper, 'internal_arap')
    wrapper.findComponent(ArApStub).vm.$emit('save', [])
    await flushPromises()
    expect(wsApi.saveWorksheetData).toHaveBeenCalledWith('p-g', 2025, 'internal_arap', { rows: [] })
    await openSheet(wrapper, 'elimination')
    elim = wrapper.findComponent(ElimStub)
    expect(elim.props('sourceGroups')).toEqual([])
    expect(elim.props('sourceOrigins')).toEqual(['ws_internal_arap'])
    expect(apiProxy.post).not.toHaveBeenCalled()
  })
})
