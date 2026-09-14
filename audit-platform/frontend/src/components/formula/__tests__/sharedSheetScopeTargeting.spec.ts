/**
 * sharedSheetScopeTargeting.spec.ts — 跨循环共享页的公式中心定位守卫
 *
 * 用户实测缺陷（D2 应收账款页 → 子页「核实被函证单位信息D0-2」→ 公式管理）：
 * 左树没定位到 D0-2、面包屑却显示 D0-2、右侧列出 D2-1 等全册公式。
 *
 * 运行时取证（本机 200 响应）：
 *  - `/api/acnr/entries?cycle=D` → D0-2 的 addr_id 是 `D0/D0-2`、parent_wp_code 是 `D0`；
 *    D2 名下只有 D2-1…D2-13，没有任何 D0-*。
 *  - D2 实例 render-config → 23 张 sheet 里 7 张是 D0 系共享函证表。
 *
 * 故「归属」的真源是宿主 render-config 的 sheet 集，不是 ACNR 的 parent_wp_code。
 * 本文件按真实数据形态锁死：共享页必须定位到自己的坐标节点、按本页过滤公式；
 * 真正定位不到时必须显式告警，不得把全册公式伪装成本页公式。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const D0_2_NAME = '核实被函证单位信息D0-2'
const D2_1_NAME = '应收账款审定表D2-1'

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
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: vi.fn(async () => []) }))
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
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

/** ACNR 目录真实形态：D0-2 挂在 D0 名下，D2 名下没有 D0-*。 */
const ACNR_D_CYCLE = [
  { addr_id: 'D2/D2-1', domain: 'wp', cycle: 'D', parent_wp_code: 'D2', sheet_code: 'D2-1', sheet_name: D2_1_NAME, account_name: '应收账款' },
  { addr_id: 'D2/D2-2', domain: 'wp', cycle: 'D', parent_wp_code: 'D2', sheet_code: 'D2-2', sheet_name: '明细测试D2-2' },
  { addr_id: 'D0/D0-1', domain: 'wp', cycle: 'D', parent_wp_code: 'D0', sheet_code: 'D0-1', sheet_name: '函证结果汇总表D0-1' },
  { addr_id: 'D0/D0-2', domain: 'wp', cycle: 'D', parent_wp_code: 'D0', sheet_code: 'D0-2', sheet_name: D0_2_NAME },
]

/** 该 D2 实例的底稿公式：D2-1 与 D0-2 各一条，用于验证按本页过滤。 */
const INSTANCE_FORMULAS = {
  items: [
    { id: 'f-d2-1', sheet_name: 'D2-1', formula: "TB('1122','期末余额')", formula_category: '取数' },
    { id: 'f-d0-2', sheet_name: 'D0-2', formula: "WP('D0-2','被函证单位')", formula_category: '取数' },
  ],
  surfaced: [],
  extraction: { tierA: [], tierB: [] },
}

/** 宿主 render-config 的 sheet 集（含共享页），由入口下发。 */
const HOST_SHEET_CODES = ['D2A', 'D2-1', 'D2-2', 'D0-1', 'D0-2', 'D0-3']

function create(props: Record<string, unknown> = {}) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false,
      rows: [],
      scope: 'workpaper',
      wpId: 'wp-d2-instance',
      wpCode: 'D2',
      projectId: 'project-1',
      year: 2025,
      sheetName: D0_2_NAME,
      hostSheetCodes: HOST_SHEET_CODES,
      ...props,
    },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

async function open(props: Record<string, unknown> = {}) {
  const w = create(props)
  await w.setProps({ modelValue: true })
  await flushPromises()
  await flushPromises()
  return w
}

describe('跨循环共享页（D2 册内的 D0-2）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      if (String(url).includes('/formulas')) return INSTANCE_FORMULAS
      if (String(url).includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue(ACNR_D_CYCLE)
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('定位到 D0-2 自己的坐标节点，而不是停在宿主 D2 父节点', async () => {
    const w = await open()

    expect(state(w).selectedNodeKey).toBe('wp_d0_2')
    expect(state(w).selectedWpSheetCode).toBe('D0-2')
    w.unmount()
  })

  it('面包屑说明本页在宿主册内且共享自 D0（不谎报为 D2 自有页）', async () => {
    const w = await open()

    expect(state(w).selectedPath).toBe('底稿 > D2 > D0-2（共享自 D0）')
    expect(state(w).selectedPath).not.toContain('全册')
    w.unmount()
  })

  it('右侧只列本页公式，不再混入 D2-1', async () => {
    const w = await open()

    expect(get).toHaveBeenCalledWith('/api/workpapers/wp-d2-instance/formulas')
    const rows = state(w).currentRows as any[]
    expect(rows.map((r) => r.id)).toEqual(['f-d0-2'])
    expect(state(w).wpFormulaError).toBe('')
    expect(state(w).wpSheetLocateMiss).toBe('')
    w.unmount()
  })

  it('宿主自有页（D2-1）行为不回归', async () => {
    const w = await open({ sheetName: D2_1_NAME })

    expect(state(w).selectedNodeKey).toBe('wp_d2_1')
    expect(state(w).selectedPath).toBe('底稿 > D2 > D2-1')
    expect((state(w).currentRows as any[]).map((r) => r.id)).toEqual(['f-d2-1'])
    w.unmount()
  })

  it('在左树点击该共享页仍按宿主实例加载（不报「缺少匹配的底稿实例」）', async () => {
    const w = await open()
    // 树节点的 _wpCode 是原生工作簿 D0；加载身份必须仍走宿主实例 wp-d2-instance
    state(w).onTreeNodeClick({ key: 'wp_d0_2', label: 'D0-2', _wpCode: 'D0', _sheetCode: 'D0-2' })
    await flushPromises()

    expect(state(w).wpFormulaError).toBe('')
    expect((state(w).currentRows as any[]).map((r) => r.id)).toEqual(['f-d0-2'])
    w.unmount()
  })

  it('真正的外册页仍被拒绝（不得用本实例 id 加载别册公式）', async () => {
    const w = await open()
    state(w).onTreeNodeClick({ key: 'wp_e1_1', label: 'E1-1', _wpCode: 'E1', _sheetCode: 'E1-1' })
    await flushPromises()

    expect(state(w).wpFormulaError).toContain('缺少匹配的底稿实例')
    w.unmount()
  })

  it('入口未下发 sheet 集时退回旧口径（不崩、显式告警而非伪装成本页）', async () => {
    const w = await open({ hostSheetCodes: undefined })

    expect(state(w).selectedWpSheetCode).toBe('')
    expect(state(w).selectedPath).toContain('全册')
    expect(state(w).wpSheetLocateMiss).toContain(D0_2_NAME)
    w.unmount()
  })
})

describe('定位失败必须显式告警（fail-open 伪装守卫）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) =>
      String(url).includes('/formulas') ? INSTANCE_FORMULAS : (String(url).includes('report-config/types') ? [] : {}),
    )
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue(ACNR_D_CYCLE)
  })

  it('坐标目录里没有该页时：面包屑标注全册 + 告警 + 不谎称定位成功', async () => {
    const w = await open({ sheetName: '尚未登记的新页D2-99', hostSheetCodes: ['D2-99'] })

    expect(state(w).selectedWpSheetCode).toBe('')
    expect(state(w).selectedPath).toContain('全册')
    expect(state(w).selectedPath).toContain('当前位置：尚未登记的新页D2-99')
    expect(state(w).wpSheetLocateMiss).toContain('不是本页公式')
    w.unmount()
  })

  it('工作簿级视图（调用页未给 sheet）不出告警', async () => {
    const w = await open({ sheetName: '' })

    expect(state(w).selectedPath).toContain('全册')
    expect(state(w).wpSheetLocateMiss).toBe('')
    w.unmount()
  })
})
