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

// 🔴 为什么本文件用「按 URL 分派」而非 `mockResolvedValueOnce` 排队：
// 打开弹窗的 watch 会在**加载底稿公式之前**先 `void loadPushBindings()`
// （Task 1.4 / Phase 2 接线新增的 GET `/formula-push/bindings`，未 await）。
// 旧测用 `get.mockResolvedValueOnce/RejectedValueOnce/ImplementationOnce` 控制
// 「第一个 GET」——但第一个 GET 现在是 bindings，不是底稿公式 ⇒ 受控行为被 bindings
// 抢先消费，底稿公式落到默认 resolve，断言恒假（memory 前端坑③同源：同页多 GET，
// 排队式 mock 对「哪个请求先发」敏感）。
// 修正方向（tasks §8.3「显式等待对应请求」）：把受控行为**绑定到对应端点 URL**，
// 与调用顺序解耦 —— bindings / user-formulas / 底稿公式各有独立受控点，反映真实接线。
type Dispatcher = (url: string) => unknown
const endpoints = {
  // 底稿公式 GET `/api/workpapers/{wpId}/formulas`
  wpFormulas: { current: null as Dispatcher | null, once: null as Dispatcher | null },
  // 用户自定义公式 GET `/api/workpapers/{wpId}/user-formulas`
  userFormulas: { current: null as Dispatcher | null, once: null as Dispatcher | null },
}

function takeDispatcher(slot: { current: Dispatcher | null; once: Dispatcher | null }): Dispatcher | null {
  if (slot.once) {
    const d = slot.once
    slot.once = null
    return d
  }
  return slot.current
}

function dispatch(url: string): unknown {
  const u = String(url)
  // bindings 恒返空清单（Task 1.4 接线产生的旁路 GET，与底稿公式加载无关）。
  if (u.includes('/formula-push/bindings')) return Promise.resolve({ items: [] })
  if (u.endsWith('/user-formulas')) {
    const d = takeDispatcher(endpoints.userFormulas)
    return d ? d(u) : Promise.resolve({ items: [] })
  }
  if (u.endsWith('/formulas')) {
    const d = takeDispatcher(endpoints.wpFormulas)
    return d ? d(u) : Promise.resolve(data('first'))
  }
  // 其余弹窗打开时的旁路 GET（report-config/types、cross-check 等）——空响应即可。
  return Promise.resolve({})
}

const data = (id: string) => ({
  // 🔴 结构化 sheet 身份：Task 1.2/1.4 把右栏归属改为 `stable_sheet_key`/`sheet_codes`/
  // 结构化 sheet 名**精确等值 + fail-closed**（禁 includes 串页）。故本测的样本行必须
  // 携带精确归属当前 sheet（E1-1）的结构身份，否则会被真实过滤逻辑如实排除。
  items: [{ id, sheet_name: '审定表E1-1', sheet_codes: ['E1-1'], formula: '1' }],
  // surfaced 无 sheet_codes = 工作簿级，恒显示。
  surfaced: [{ id: 'surface', formula: '2' }],
  extraction: {
    tierA: [{ id: 'a', expression: '3', anchor: 'E1-1', sheet_name: '审定表E1-1' }],
    tierB: [{ anchor: 'E1-1', sheet_name: '审定表E1-1', description: 'trace' }],
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
      sheetName: '审定表E1-1',
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
    get.mockImplementation((url: string) => dispatch(url))
    endpoints.wpFormulas.current = null
    endpoints.wpFormulas.once = null
    endpoints.userFormulas.current = null
    endpoints.userFormulas.once = null
    scopeLoad.mockReset()
    scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset()
    scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset()
    acnrListSheets.mockResolvedValue([
      {
        addr_id: 'E1/E1-1',
        domain: 'wp',
        cycle: 'E',
        parent_wp_code: 'E1',
        sheet_code: 'E1-1',
        sheet_name: '审定表E1-1',
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
    expect(state(w).selectedPath).toContain('E1-1')

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
    // instance-a 的底稿公式 GET 挂起（不解析）；切到 instance-b 后用默认 `data('first')`。
    // 受控点绑定在「底稿公式端点」上，不受 bindings 等旁路 GET 的发起顺序影响。
    let finish!: (value: unknown) => void
    endpoints.wpFormulas.once = () => new Promise(resolve => { finish = resolve })
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
    // 底稿公式端点拒绝（受控点绑定在该端点，不会被先发的 bindings GET 抢先消费）。
    endpoints.wpFormulas.once = () => Promise.reject(new Error('403'))
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
    endpoints.userFormulas.once = () => new Promise(resolve => { finish = resolve })
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
