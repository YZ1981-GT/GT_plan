import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { nextTick } from 'vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const { get, scopeLoad, scopeGetRows, acnrListSheets, addressState } = vi.hoisted(() => ({
  get: vi.fn(),
  scopeLoad: vi.fn(),
  scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(),
  addressState: { loaded: false, tbAddresses: [] },
}))

vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({
    get loaded() { return addressState.loaded },
    get tbAddresses() { return addressState.tbAddresses },
  }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', () => ({
  useFormulaScopeCatalog: () => ({
    loadScope: scopeLoad,
    resolveSources: vi.fn(async () => undefined),
    getScopeRows: scopeGetRows,
    loadGlobal: vi.fn(async () => ({})),
    resolveScopeSources: vi.fn(async () => undefined),
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets,
    listCells: vi.fn(),
    resolve: vi.fn(),
    resolveFormula: vi.fn(),
    resolveUri: vi.fn(),
    resolveAddr: vi.fn(),
    resolveIndex: vi.fn(),
    resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    linkageBus: {},
    formulaAuditLog: { list: '/api/formula-audit-logs' },
  }
})

const data = (id: string) => ({
  items: [{ id, sheet_name: 'Sheet A', formula: '1' }],
  surfaced: [{ id: 'surface', formula: '2' }],
  extraction: {
    tierA: [{ id: 'a', expression: '3', anchor: 'Sheet A::x' }],
    tierB: [{ anchor: 'Sheet A::y', description: 'trace' }],
  },
})

function create() {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false,
      rows: [],
      scope: 'workpaper',
      wpId: 'instance-a',
      wpCode: 'E1',
      projectId: 'project',
      year: 2025,
      sheetName: 'Sheet A',
    },
    global: {
      plugins: [ElementPlus],
      renderStubDefaultSlot: false,
    },
  })
}

const state = (wrapper: ReturnType<typeof create>) => (wrapper.vm as any).$.setupState

describe('real FormulaManagerDialog page context', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue(data('first'))
    scopeLoad.mockReset()
    scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset()
    scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset()
    acnrListSheets.mockResolvedValue([
      {
        addr_id: 'E1/Sheet A',
        domain: 'wp',
        cycle: 'E',
        parent_wp_code: 'E1',
        sheet_code: 'Sheet A',
        sheet_name: 'Sheet A',
        account_name: '货币资金',
      },
    ])
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('loads all workbook sources by instance and clears previous filters', async () => {
    const w = create()
    await w.setProps({ modelValue: true })
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/workpapers/instance-a/formulas')
    expect(get.mock.calls.some(([url]) => String(url).includes('wp-id-by-code'))).toBe(false)
    expect(state(w).currentRows).toHaveLength(4)
    expect(state(w).selectedPath).toContain('Sheet A')

    state(w).activeCategory = 'logic_check'
    state(w).uriSearchQuery = 'missing'
    await w.setProps({ modelValue: false })
    await w.setProps({ modelValue: true })
    await flushPromises()

    expect(state(w).activeCategory).toBe('all')
    expect(state(w).filteredRows).toHaveLength(4)
    w.unmount()
  })

  it('discards slow old instance results and loading completion', async () => {
    let finish!: (value: unknown) => void
    get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const w = create()
    await w.setProps({ modelValue: true })
    await flushPromises()
    await w.setProps({ wpId: 'instance-b' })
    await flushPromises()
    finish(data('stale'))
    await flushPromises()

    expect(state(w).currentRows[0].id).toBe('first')
    expect(state(w).wpFormulaLoading).toBe(false)
    w.unmount()
  })

  it('shows explicit failure instead of empty success', async () => {
    get.mockRejectedValueOnce(new Error('403'))
    const w = create()
    await w.setProps({ modelValue: true })
    await flushPromises()

    expect(state(w).wpFormulaError).toContain('加载失败')
    expect(state(w).currentRows).toEqual([])
    w.unmount()
  })

  it('uses real wpId for user tab and rejects closed-session response', async () => {
    const w = create()
    await w.setProps({ modelValue: true })
    await flushPromises()

    let finish!: (value: unknown) => void
    get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    state(w).activeCategory = 'user_formulas'
    await nextTick()

    expect(get).toHaveBeenLastCalledWith('/api/workpapers/instance-a/user-formulas')
    await w.setProps({ modelValue: false })
    finish({ items: [{ cell_key: 'old!A1', formula: '1' }] })
    await flushPromises()

    expect(state(w).userFormulasList).toEqual([])
    w.unmount()
  })
})
