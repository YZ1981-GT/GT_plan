import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { worksheetApi, scopeApi, eventBus, formulaHandlers } = vi.hoisted(() => {
  const handlers = new Map<string, (payload: unknown) => unknown>()
  return {
    worksheetApi: {
      loadAllWorksheetData: vi.fn(),
      loadWorksheetData: vi.fn(),
      saveWorksheetData: vi.fn(),
      previewG7Linkage: vi.fn(),
      importG7Linkage: vi.fn(),
    },
    scopeApi: {
      getConsolScope: vi.fn(),
      getWorksheetTree: vi.fn(),
    },
    eventBus: {
      on: vi.fn((name: string, handler: (payload: unknown) => unknown) => handlers.set(name, handler)),
      off: vi.fn(),
      emit: vi.fn(),
    },
    formulaHandlers: handlers,
  }
})

vi.mock('@/services/consolWorksheetDataApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/consolWorksheetDataApi')>()
  return {
    ...actual,
    loadAllWorksheetData: (...args: unknown[]) => worksheetApi.loadAllWorksheetData(...args),
    loadWorksheetData: (...args: unknown[]) => worksheetApi.loadWorksheetData(...args),
    saveWorksheetData: (...args: unknown[]) => worksheetApi.saveWorksheetData(...args),
    previewG7Linkage: (...args: unknown[]) => worksheetApi.previewG7Linkage(...args),
    importG7Linkage: (...args: unknown[]) => worksheetApi.importG7Linkage(...args),
  }
})
vi.mock('@/services/consolidationApi', () => ({
  getConsolScope: (...args: unknown[]) => scopeApi.getConsolScope(...args),
  getWorksheetTree: (...args: unknown[]) => scopeApi.getWorksheetTree(...args),
}))
vi.mock('@/utils/eventBus', () => ({ eventBus }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), onFileSelected: vi.fn() }),
}))
vi.mock('@/components/workpaper/composables/g7ConsolLinkageEntry', () => ({
  useG7ConsolLinkageEntry: () => ({ stale: ref(false), staleSheets: ref([]), refreshStale: vi.fn() }),
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

import ConsolWorksheetTabs from '../worksheets/ConsolWorksheetTabs.vue'

const Pass = defineComponent({
  inheritAttrs: true,
  setup(_, { attrs, slots }) {
    return () => h('div', attrs, [slots.default?.(), slots.title?.(), slots.footer?.()])
  },
})
const ButtonStub = defineComponent({
  inheritAttrs: true,
  setup(_, { attrs, slots }) {
    return () => h('button', attrs, slots.default?.())
  },
})
const InfoStub = defineComponent({
  name: 'SubsidiaryInfoSheet',
  emits: ['save', 'open-share-change', 'open-formula'],
  setup(_, { emit }) {
    return () => h('button', {
      'data-testid': 'info-save',
      onClick: () => emit('save', [{ company_code: 'A' }]),
    }, '保存基本信息')
  },
})
const EliminationStub = defineComponent({
  name: 'EliminationSheet',
  props: ['projectId', 'year'],
  setup() { return () => h('div', { 'data-testid': 'elimination-stub' }) },
})

const emptyPreview = {
  source_wp_id: 'wp-g7',
  item_versions: { info: 'v1' },
  sources_used: ['G7-10'],
  unresolved_companies: [],
  available_companies: [],
  counts: {},
  targets: {},
  importable: {},
}

function mountTabs(props: Partial<{ projectId: string; year: number; consolMode: string | null; isRootSelection: boolean }> = {}) {
  return mount(ConsolWorksheetTabs, {
    props: {
      projectId: 'project-7',
      year: 2025,
      consolMode: 'subsidiary',
      isRootSelection: true,
      ...props,
    },
    global: {
      stubs: {
        SubsidiaryInfoSheet: InfoStub,
        EliminationSheet: EliminationStub,
        InvestmentCostSheet: true,
        InvestmentEquitySheet: true,
        NetAssetSheet: true,
        EquitySimSheet: true,
        CapitalReserveSheet: true,
        ShareChangeSheet: true,
        PostElimInvestSheet: true,
        PostElimIncomeSheet: true,
        MinorityInterestSheet: true,
        InternalArApSheet: true,
        InternalTradeSheet: true,
        InternalCashFlowSheet: true,
        G7SuggestionDraftSheet: true,
        'el-alert': Pass,
        'el-tooltip': Pass,
        'el-tag': Pass,
        'el-icon': Pass,
        'el-button': ButtonStub,
        'el-dropdown': Pass,
        'el-dropdown-menu': Pass,
        'el-dropdown-item': Pass,
        'el-dialog': Pass,
        'el-descriptions': Pass,
        'el-descriptions-item': Pass,
        'el-table': Pass,
        'el-table-column': Pass,
        'el-select': Pass,
        'el-option': Pass,
        'el-checkbox': Pass,
        'el-checkbox-group': Pass,
        'el-switch': Pass,
        'el-empty': Pass,
      },
    },
  })
}

function setupData(wrapper: ReturnType<typeof mountTabs>) {
  return (wrapper.vm as any).$.setupState.data as { subsidiaryInfo: Array<{ company_code: string }> }
}

beforeEach(() => {
  worksheetApi.loadAllWorksheetData.mockReset().mockResolvedValue({ status: 'empty', data: {}, versions: {} })
  worksheetApi.loadWorksheetData.mockReset().mockResolvedValue({ status: 'empty', data: {}, versions: {} })
  worksheetApi.saveWorksheetData.mockReset().mockResolvedValue({ ok: true, version: 1 })
  worksheetApi.previewG7Linkage.mockReset().mockResolvedValue(emptyPreview)
  worksheetApi.importG7Linkage.mockReset().mockResolvedValue({ imported: {}, unresolved_companies: [] })
  scopeApi.getConsolScope.mockReset().mockResolvedValue([])
  scopeApi.getWorksheetTree.mockReset().mockResolvedValue({
    mode: 'subsidiary',
    tree: { company_code: 'G', children: [] },
  })
  eventBus.on.mockClear()
  eventBus.off.mockClear()
  eventBus.emit.mockClear()
  formulaHandlers.clear()
})

describe('ConsolWorksheetTabs 任务7：年度、状态和页签上下文', () => {
  it('成功空响应显示中文 empty 状态，并保留可编辑默认数据', async () => {
    const wrapper = mountTabs()
    await flushPromises()

    expect(wrapper.find('[data-testid="cw-empty-state"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cw-load-error"]').exists()).toBe(false)
    expect(setupData(wrapper).subsidiaryInfo.length).toBeGreaterThan(0)
    expect(worksheetApi.loadAllWorksheetData).toHaveBeenCalledWith('project-7', 2025)
  })

  it('加载失败显示独立 error 状态，并在重载失败时保留已加载数据', async () => {
    worksheetApi.loadAllWorksheetData.mockResolvedValueOnce({
      status: 'loaded',
      data: { info: { rows: [{ company_code: 'LOADED' }] } },
      versions: { info: 1 },
    })
    const wrapper = mountTabs()
    await flushPromises()
    expect(setupData(wrapper).subsidiaryInfo[0].company_code).toBe('LOADED')

    worksheetApi.loadAllWorksheetData.mockResolvedValueOnce({
      status: 'error', data: {}, versions: {}, errorMessage: '后端暂时不可用',
    })
    await (wrapper.vm as any).reload()
    await flushPromises()

    expect(wrapper.find('[data-testid="cw-load-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cw-empty-state"]').exists()).toBe(false)
    expect(setupData(wrapper).subsidiaryInfo[0].company_code).toBe('LOADED')
  })

  it('年度切换后旧请求响应不能覆盖新年度数据，且请求不携带伪 node_key', async () => {
    let resolveOld!: (value: unknown) => void
    let resolveNew!: (value: unknown) => void
    const oldRequest = new Promise((resolve) => { resolveOld = resolve })
    const newRequest = new Promise((resolve) => { resolveNew = resolve })
    worksheetApi.loadAllWorksheetData.mockImplementationOnce(() => oldRequest)
      .mockImplementationOnce(() => newRequest)

    const wrapper = mountTabs()
    await nextTick()
    await wrapper.setProps({ year: 2026 })
    await nextTick()

    expect(worksheetApi.loadAllWorksheetData).toHaveBeenNthCalledWith(1, 'project-7', 2025)
    expect(worksheetApi.loadAllWorksheetData).toHaveBeenNthCalledWith(2, 'project-7', 2026)
    expect(worksheetApi.loadAllWorksheetData.mock.calls.flat()).not.toContain('node_key')

    resolveNew({ status: 'loaded', data: { info: { rows: [{ company_code: 'NEW_YEAR' }] } }, versions: { info: 2 } })
    await flushPromises()
    resolveOld({ status: 'loaded', data: { info: { rows: [{ company_code: 'OLD_YEAR' }] } }, versions: { info: 1 } })
    await flushPromises()

    expect(setupData(wrapper).subsidiaryInfo[0].company_code).toBe('NEW_YEAR')
  })

  it('保存、G7 预览/导入和公式重载都使用父页传入的年度', async () => {
    const wrapper = mountTabs({ projectId: 'project-parent', year: 2031 })
    await flushPromises()

    await wrapper.find('[data-testid="info-save"]').trigger('click')
    await flushPromises()
    expect(worksheetApi.saveWorksheetData).toHaveBeenCalledWith(
      'project-parent', 2031, 'info', { rows: [{ company_code: 'A' }] }, 0,
    )

    await (wrapper.vm as any).openG7Linkage()
    expect(worksheetApi.previewG7Linkage).toHaveBeenCalledWith('project-parent', 2031)
    await (wrapper.vm as any).confirmG7Linkage()
    expect(worksheetApi.importG7Linkage).toHaveBeenCalledWith(
      'project-parent', 2031,
      expect.objectContaining({ sheet_keys: ['info', 'cost', 'equity_inv', 'net_asset'] }),
    )

    worksheetApi.loadAllWorksheetData.mockClear()
    await formulaHandlers.get('formula-changed')?.({ source: 'test' })
    expect(worksheetApi.loadAllWorksheetData).toHaveBeenCalledWith('project-parent', 2031)
  })

  it('工作底稿请求保持项目/年度级作用域，右侧页签切换不会改写节点身份', async () => {
    const wrapper = mountTabs({ projectId: 'project-node', year: 2028 })
    await flushPromises()
    const initialCalls = worksheetApi.loadAllWorksheetData.mock.calls.length

    ;(wrapper.vm as any).activeSheet = 'cost'
    await nextTick()
    ;(wrapper.vm as any).activeSheet = 'info'
    await nextTick()

    ;(wrapper.vm as any).activeSheet = 'elimination'
    await nextTick()
    expect(wrapper.findComponent(EliminationStub).props('projectId')).toBe('project-node')
    expect(wrapper.findComponent(EliminationStub).props('year')).toBe(2028)
  })

  it('总分汇总提示只由已验证 branch mode 决定，根/母公司/单户选择不会改变该项目模式', async () => {
    const root = mountTabs({ consolMode: 'branch', isRootSelection: true })
    await flushPromises()
    expect(root.find('[data-testid="cw-branch-notice"]').exists()).toBe(true)

    await root.setProps({ isRootSelection: false })
    await nextTick()
    expect(root.find('[data-testid="cw-branch-notice"]').exists()).toBe(true)

    const nonBranch = mountTabs({ consolMode: 'subsidiary', isRootSelection: false })
    await flushPromises()
    expect(nonBranch.find('[data-testid="cw-branch-notice"]').exists()).toBe(false)
  })

  it('保存遇到版本冲突（409）时自动重载数据并提示用户', async () => {
    // 首次加载带版本号
    worksheetApi.loadAllWorksheetData.mockResolvedValueOnce({
      status: 'loaded',
      data: { info: { rows: [{ company_code: 'V1' }] } },
      versions: { info: 5 },
    })
    const wrapper = mountTabs()
    await flushPromises()
    expect(setupData(wrapper).subsidiaryInfo[0].company_code).toBe('V1')

    // 模拟保存时后端返回 409 版本冲突
    const { WorksheetVersionConflictError } = await import('@/services/consolWorksheetDataApi')
    worksheetApi.saveWorksheetData.mockRejectedValueOnce(
      new WorksheetVersionConflictError(5, 6, '工作底稿已被其他操作修改'),
    )
    // 重载时返回新版本数据
    worksheetApi.loadAllWorksheetData.mockResolvedValueOnce({
      status: 'loaded',
      data: { info: { rows: [{ company_code: 'V2_RELOADED' }] } },
      versions: { info: 6 },
    })

    await wrapper.find('[data-testid="info-save"]').trigger('click')
    await flushPromises()

    // 409 后应自动重载，展示新版本数据
    expect(setupData(wrapper).subsidiaryInfo[0].company_code).toBe('V2_RELOADED')
    // saveWorksheetData 被调用时应传入版本号 5
    expect(worksheetApi.saveWorksheetData).toHaveBeenCalledWith(
      'project-7', 2025, 'info', { rows: [{ company_code: 'A' }] }, 5,
    )
  })
})
