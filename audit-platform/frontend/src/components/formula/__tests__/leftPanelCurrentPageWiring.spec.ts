/**
 * leftPanelCurrentPageWiring.spec.ts — Task 3.2 / ADR-FMC-05 左栏接线组件级守卫
 *
 * 纯逻辑决策已由 leftPanelAnchors.spec.ts 覆盖；本文件真挂载 FormulaManagerDialog，
 * 锁死组件接线（铁律㉕：新接线须真 mount 验证，不能只测纯函数）：
 *   - 当前页上下文（底稿实例页）左栏默认只显精确当前 sheet 的 anchors（来自 listCells），
 *     每行带同一 location identity；treeData 不含全局五域节点（trial_balance/report…）。
 *   - 缺当前页 sheet 身份 → fail-closed：treeData 空集 + leftPanelWarning 非空，**不退全局树**。
 *   - 「全局浏览」是独立显式动作（enterGlobalBrowse）：treeData 变全局五域树；exitGlobalBrowse 退回。
 *   - 变异反证：fail-closed 态下 treeData 绝不含全局域节点（把它改成回退全局树即打红）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const E1_1_NAME = '货币资金审定表E1-1'

const { get, scopeLoad, scopeGetRows, acnrListSheets, acnrListCells, addressState } = vi.hoisted(() => ({
  get: vi.fn(),
  scopeLoad: vi.fn(),
  scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(),
  acnrListCells: vi.fn(),
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
    listCells: acnrListCells,
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

/** ACNR 目录：E1 册含 E1-1。 */
const ACNR_E_CYCLE = [
  { addr_id: 'E1/E1-1', domain: 'wp', cycle: 'E', parent_wp_code: 'E1', sheet_code: 'E1-1', sheet_name: E1_1_NAME, account_name: '货币资金' },
  { addr_id: 'E1/E1-2', domain: 'wp', cycle: 'E', parent_wp_code: 'E1', sheet_code: 'E1-2', sheet_name: '明细E1-2' },
]

/** E1-1 页的 anchors（listCells 返回）。 */
const E1_1_CELLS = [
  { addr_id: 'E1/E1-1/E6', parent_addr_id: 'E1/E1-1', domain: 'wp', cell_address: 'E6', semantic_label: '库存现金期末', formula_ref: "WP('E1','E1-1','E6')" },
  { addr_id: 'E1/E1-1/E7', parent_addr_id: 'E1/E1-1', domain: 'wp', cell_address: 'E7', semantic_label: '银行存款期末', formula_ref: "WP('E1','E1-1','E7')" },
]

const INSTANCE_FORMULAS = { items: [], surfaced: [], extraction: { tierA: [], tierB: [] } }

const GLOBAL_DOMAIN_KEYS = ['trial_balance', 'report', 'note', 'workpaper', 'consol_report', 'cross_check']

function create(props: Record<string, unknown> = {}) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false,
      rows: [],
      scope: 'workpaper',
      wpId: 'wp-e1-instance',
      wpCode: 'E1',
      projectId: 'project-1',
      year: 2025,
      sheetName: E1_1_NAME,
      hostSheetCodes: ['E1A', 'E1-1', 'E1-2'],
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

describe('左栏当前页 anchors 接线（底稿实例页）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      if (String(url).includes('/formulas')) return INSTANCE_FORMULAS
      if (String(url).includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue(ACNR_E_CYCLE)
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue(E1_1_CELLS)
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('默认只显当前页 anchors：treeData = 本 sheet 的 addr_id 节点，不含全局五域节点', async () => {
    const w = await open()

    expect(state(w).isCurrentPageContext).toBe(true)
    expect(state(w).leftPanelGlobalBrowse).toBe(false)
    expect(state(w).selectedWpSheetCode).toBe('E1-1')

    const tree = state(w).treeData as any[]
    expect(tree.map((n) => n._addrId)).toEqual(['E1/E1-1/E6', 'E1/E1-1/E7'])
    // 每行带同一 location identity（projectId/wpId/sheetUid）。
    for (const n of tree) {
      expect(n._identity).toEqual({ projectId: 'project-1', wpId: 'wp-e1-instance', sheetUid: 'E1-1' })
    }
    // 默认左栏不含任何全局域节点（替换旧全局五域树行为）。
    for (const key of GLOBAL_DOMAIN_KEYS) {
      expect(tree.some((n) => n.key === key)).toBe(false)
    }
    // listCells 被按精确当前 sheet 调用（wp_code=E1, sheet=E1-1）。
    expect(acnrListCells).toHaveBeenCalledWith('E1', 'E1-1')
    expect(state(w).leftPanelWarning).toBe('')
    w.unmount()
  })

  it('缺当前页 sheet 身份 → fail-closed：treeData 空集 + 告警，不退全局树（变异反证锚）', async () => {
    // 坐标目录里没有该页 → selectedWpSheetCode 解析为空 → fail-closed。
    const w = await open({ sheetName: '尚未登记的新页E1-99', hostSheetCodes: ['E1-99'] })

    expect(state(w).isCurrentPageContext).toBe(true)
    expect(state(w).selectedWpSheetCode).toBe('')

    const tree = state(w).treeData as any[]
    // 🔴 fail-closed：空集 + 告警，绝不回退全局树（把它改成全局树则下列断言打红）。
    expect(tree).toEqual([])
    expect(state(w).leftPanelWarning).not.toBe('')
    for (const key of GLOBAL_DOMAIN_KEYS) {
      expect(tree.some((n) => n.key === key)).toBe(false)
    }
    // fail-closed 不取当前页 anchors（wpCode/sheet 任一空 → loader 返空且不发 listCells）。
    expect(acnrListCells).not.toHaveBeenCalled()
    w.unmount()
  })

  it('「全局浏览」是独立显式动作：进入后 treeData 变全局五域树，退回后回到当前页 anchors', async () => {
    const w = await open()
    expect((state(w).treeData as any[]).every((n) => String(n.key).startsWith('anchor_'))).toBe(true)

    // 显式进入全局浏览。
    await state(w).enterGlobalBrowse()
    await flushPromises()
    expect(state(w).leftPanelGlobalBrowse).toBe(true)
    const globalTree = state(w).treeData as any[]
    for (const key of ['trial_balance', 'report', 'note', 'workpaper']) {
      expect(globalTree.some((n) => n.key === key)).toBe(true)
    }
    expect(state(w).leftPanelWarning).toBe('')

    // 退回当前页地址。
    await state(w).exitGlobalBrowse()
    await flushPromises()
    expect(state(w).leftPanelGlobalBrowse).toBe(false)
    expect((state(w).treeData as any[]).map((n) => n._addrId)).toEqual(['E1/E1-1/E6', 'E1/E1-1/E7'])
    w.unmount()
  })
})
