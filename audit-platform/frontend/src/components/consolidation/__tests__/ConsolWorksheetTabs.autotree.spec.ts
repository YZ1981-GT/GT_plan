/**
 * 合并工作底稿：基本信息表按企业树带出 + 分录汇总表接线（spec consol-autotree-linkage-closure 任务 17 / 19）
 *
 * - 企业树成员在前、已保存行按企业代码保留填写值、不在树中的留在表尾；三码锁定（向表格传企业树代码）；
 * - 企业列只认企业树，持股比例取基本信息表；企业树读取失败保持手工维护；
 * - 工具栏导入基本信息表：锁定时按企业代码只更新可编辑字段，匹配不上的提示；
 * - 分录汇总表进「合并抵消」分组；暴露 reloadEntrySummary；推送后 reload 时重读。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { worksheetApi, treeApi, message, excelRows } = vi.hoisted(() => ({
  worksheetApi: {
    loadAllWorksheetData: vi.fn(), loadWorksheetData: vi.fn(), saveWorksheetData: vi.fn(),
    previewG7Linkage: vi.fn(), importG7Linkage: vi.fn(),
  },
  treeApi: { getWorksheetTree: vi.fn() },
  message: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
  excelRows: { value: [] as Record<string, unknown>[] },
}))

vi.mock('@/services/consolWorksheetDataApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/consolWorksheetDataApi')>()
  return {
    ...actual,
    loadAllWorksheetData: (...a: unknown[]) => worksheetApi.loadAllWorksheetData(...a),
    loadWorksheetData: (...a: unknown[]) => worksheetApi.loadWorksheetData(...a),
    saveWorksheetData: (...a: unknown[]) => worksheetApi.saveWorksheetData(...a),
    previewG7Linkage: (...a: unknown[]) => worksheetApi.previewG7Linkage(...a),
    importG7Linkage: (...a: unknown[]) => worksheetApi.importG7Linkage(...a),
  }
})
vi.mock('@/services/consolidationApi', () => ({ getWorksheetTree: (...a: unknown[]) => treeApi.getWorksheetTree(...a) }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({
    exportTemplate: vi.fn(), exportData: vi.fn(),
    onFileSelected: async (_e: unknown, cb: (r: { rows: Record<string, unknown>[] }) => Promise<void>) => cb({ rows: excelRows.value }),
  }),
}))
vi.mock('@/components/workpaper/composables/g7ConsolLinkageEntry', () => ({
  useG7ConsolLinkageEntry: () => ({ stale: ref(false), staleSheets: ref([]), refreshStale: vi.fn() }),
}))
vi.mock('element-plus', () => ({ ElMessage: message }))

import ConsolWorksheetTabs from '../worksheets/ConsolWorksheetTabs.vue'

const Pass = defineComponent({ setup(_, { slots }) { return () => h('div', [slots.default?.(), slots.title?.()]) } })
const InfoStub = defineComponent({
  name: 'SubsidiaryInfoSheet',
  props: ['modelValue', 'treeCodes'],
  setup() { return () => h('div', { 'data-testid': 'info-stub' }) },
})
const summaryLoad = vi.fn()
const SummaryStub = defineComponent({
  name: 'EntrySummarySheet',
  props: ['projectId', 'year'],
  setup(_, { expose }) { expose({ load: summaryLoad }); return () => h('div', { 'data-testid': 'summary-stub' }) },
})

function tree(children: Array<Record<string, unknown>>) {
  return {
    mode: 'subsidiary',
    tree: {
      company_code: 'G', company_name: '某集团', role: 'consol', ultimate_company_code: 'G',
      children: children.map((c) => ({ role: 'subsidiary', parent_company_code: 'G', ultimate_company_code: 'G', via: [], children: [], ...c })),
    },
  }
}
const MEMBERS = tree([{ company_code: 'A', company_name: '甲公司' }, { company_code: 'B', company_name: '乙公司' }])
const SAVED_INFO = [
  { company_code: 'A', company_name: '旧名甲', account_subject: '长期股权投资', non_common_ratio: 60, holding_type: '直接', indirect_holder: '' },
  { company_code: 'Z', company_name: '已转出公司', account_subject: '其他非流动资产', holding_type: '直接', indirect_holder: '' },
]

function mountTabs() {
  return mount(ConsolWorksheetTabs, {
    props: { projectId: 'project-7', year: 2025, consolMode: 'subsidiary', isRootSelection: true },
    global: {
      stubs: {
        SubsidiaryInfoSheet: InfoStub, EntrySummarySheet: SummaryStub, EliminationSheet: true,
        InvestmentCostSheet: true, InvestmentEquitySheet: true, NetAssetSheet: true, EquitySimSheet: true,
        CapitalReserveSheet: true, ShareChangeSheet: true, PostElimInvestSheet: true, PostElimIncomeSheet: true,
        MinorityInterestSheet: true, InternalArApSheet: true, InternalTradeSheet: true, InternalCashFlowSheet: true,
        G7SuggestionDraftSheet: true,
        'el-alert': Pass, 'el-tooltip': Pass, 'el-tag': Pass, 'el-icon': Pass, 'el-button': Pass, 'el-dropdown': Pass,
        'el-dropdown-menu': Pass, 'el-dropdown-item': Pass, 'el-dialog': true, 'el-descriptions': true,
        'el-descriptions-item': true, 'el-table': true, 'el-table-column': true, 'el-select': true, 'el-option': true,
        'el-checkbox': true, 'el-checkbox-group': true, 'el-switch': true,
      },
    },
  })
}

const state = (w: ReturnType<typeof mountTabs>) => (w.vm as any).$.setupState

beforeEach(() => {
  worksheetApi.loadAllWorksheetData.mockReset().mockResolvedValue({ status: 'loaded', data: { info: { rows: SAVED_INFO } }, versions: { info: 3 } })
  worksheetApi.loadWorksheetData.mockReset().mockResolvedValue({ status: 'empty', data: {}, versions: {} })
  worksheetApi.saveWorksheetData.mockReset().mockResolvedValue({ ok: true, version: 4 })
  treeApi.getWorksheetTree.mockReset().mockResolvedValue(MEMBERS)
  Object.values(message).forEach((f) => f.mockReset())
  summaryLoad.mockReset()
  excelRows.value = []
})

describe('ConsolWorksheetTabs 基本信息表按企业树带出（R4）', () => {
  it('企业树成员在前、填写值按代码保留、不在树中的留在表尾；向表格传企业树代码；企业列只认企业树', async () => {
    const wrapper = mountTabs()
    await flushPromises()
    const info = wrapper.findComponent(InfoStub)
    expect(info.props('treeCodes')).toEqual(['A', 'B'])
    const rows = info.props('modelValue')
    expect(rows.map((r: any) => r.company_code)).toEqual(['A', 'B', 'Z'])
    expect(rows[0]).toMatchObject({ company_name: '甲公司', parent_code: 'G', ultimate_controller: '某集团', account_subject: '长期股权投资' })
    expect(rows[1]).toMatchObject({ company_name: '乙公司', account_subject: '' })
    expect(state(wrapper).companyColumns).toEqual([
      { name: '甲公司', code: 'A', ratio: 60 }, { name: '乙公司', code: 'B', ratio: 0 },
    ])
  })

  it('企业树先到、已保存数据后到也得到同一结果（对齐幂等）', async () => {
    let resolveData!: (v: unknown) => void
    worksheetApi.loadAllWorksheetData.mockImplementationOnce(() => new Promise((r) => { resolveData = r }))
    const wrapper = mountTabs()
    await flushPromises()
    expect(wrapper.findComponent(InfoStub).props('modelValue').map((r: any) => r.company_code)).toEqual(['A', 'B'])
    resolveData({ status: 'loaded', data: { info: { rows: SAVED_INFO } }, versions: { info: 3 } })
    await flushPromises()
    expect(wrapper.findComponent(InfoStub).props('modelValue').map((r: any) => r.company_code)).toEqual(['A', 'B', 'Z'])
  })

  it('企业树读取失败：保持手工维护（不锁定、不改已保存行），企业列回退基本信息表', async () => {
    treeApi.getWorksheetTree.mockRejectedValueOnce(new Error('down'))
    const wrapper = mountTabs()
    await flushPromises()
    const info = wrapper.findComponent(InfoStub)
    expect(info.props('treeCodes')).toBeNull()
    expect(info.props('modelValue').map((r: any) => r.company_name)).toEqual(['旧名甲', '已转出公司'])
    expect(state(wrapper).companyColumns.map((c: any) => c.code)).toEqual(['A', 'Z'])
  })

  it('工具栏导入基本信息表（锁定）：按企业代码只更新可编辑字段并保存，匹配不上的提示跳过', async () => {
    const wrapper = mountTabs()
    await flushPromises()
    excelRows.value = [
      { 企业代码: 'A', 企业名称: '改名甲', 上级企业代码: 'HACK', 核算方式: '权益法' },
      { 企业代码: 'Q', 企业名称: '外部公司' },
    ]
    await (wrapper.vm as any).handleImportFile({ target: { value: '' } })
    await flushPromises()
    expect(message.warning).toHaveBeenCalledWith(expect.stringContaining('已跳过：Q'))
    const call = worksheetApi.saveWorksheetData.mock.calls.at(-1)!
    expect(call.slice(0, 3)).toEqual(['project-7', 2025, 'info'])
    expect(call[4]).toBe(3)
    const saved = (call[3] as any).rows
    expect(saved.map((r: any) => r.company_code)).toEqual(['A', 'B', 'Z'])
    expect(saved[0]).toMatchObject({ company_name: '甲公司', parent_code: 'G', accounting_method: '权益法' })
    expect(message.success).toHaveBeenCalledWith('基本信息表已保存')
  })
})

describe('ConsolWorksheetTabs 分录汇总表接线（R9.4）', () => {
  it('分录汇总表在「合并抵消」分组；打开后传项目 / 年度；reloadEntrySummary 与推送后 reload 都重读', async () => {
    const wrapper = mountTabs()
    await flushPromises()
    const g5 = state(wrapper).navGroups.find((g: any) => g.key === 'g5')
    expect(g5.sheets.map((s: any) => s.key)).toEqual(['elimination', 'entry_summary', 'capital', 'g7_suggestions'])

    await (wrapper.vm as any).reloadEntrySummary()
    expect(summaryLoad).not.toHaveBeenCalled()

    state(wrapper).activeSheet = 'entry_summary'
    await flushPromises()
    const summary = wrapper.findComponent(SummaryStub)
    expect(summary.props()).toEqual({ projectId: 'project-7', year: 2025 })
    await (wrapper.vm as any).reloadEntrySummary()
    expect(summaryLoad).toHaveBeenCalledTimes(1)
    await (wrapper.vm as any).reload()
    expect(summaryLoad).toHaveBeenCalledTimes(2)
  })
})
