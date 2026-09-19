/**
 * consolWorksheetScopeTargeting.spec.ts — 合并工作底稿「公式管理」定位守卫
 *
 * 背景：合并 worksheet 入口此前只发 `{ nodeKey }`，无 wpId ⇒ 全局挂载层按
 * 「有 wpId 才算底稿域」的规则把它判成报表域，弹窗停在「报表 > 资产负债表」，
 * 右侧列的也不是当前 worksheet 的公式。
 *
 * 合并模块是项目级的（没有普通底稿实例），故定位身份 = projectId + year + 当前 worksheet。
 * 本文件用真实 FormulaManagerDialog 挂载做行为级断言，不做字符串存在性检查。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
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
  return {
    ...actual,
    linkageBus: {},
    formulaAuditLog: { list: '/api/formula-audit-logs' },
  }
})

/** 合并 worksheet 场景：调用页传 scope + 当前 worksheet，不传 wpId（项目级模块）。 */
function create(sheetName?: string) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false,
      rows: [],
      scope: 'consol_worksheet',
      projectId: 'project-1',
      year: 2025,
      sheetName,
    },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

const state = (wrapper: ReturnType<typeof create>) => (wrapper.vm as any).$.setupState

async function open(sheetName?: string) {
  const w = create(sheetName)
  await w.setProps({ modelValue: true })
  await flushPromises()
  await flushPromises()
  return w
}

describe('合并工作底稿 scope 定位', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) =>
      String(url).includes('report-config/types') ? [] : {},
    )
    scopeLoad.mockReset()
    scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset()
    scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset()
    // 合并模块不依赖 ACNR 底稿 catalog：即便为空也必须能定位到合并工作底稿页
    acnrListSheets.mockResolvedValue([])
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('按当前 worksheet 定位到对应节点，且不落到报表域默认节点', async () => {
    const w = await open('elimination')

    expect(state(w).selectedNodeKey).toBe('consol_elimination')
    expect(state(w).selectedPath).toBe('合并工作底稿 > 合并抵消分录')
    expect(state(w).expandedKeys).toContain('consolidation')
    w.unmount()
  })

  it('切换 worksheet 后重新定位（不残留上一页）', async () => {
    const w = await open('elimination')
    await w.setProps({ sheetName: 'net_asset' })
    await flushPromises()
    await flushPromises()

    expect(state(w).selectedNodeKey).toBe('consol_net_asset')
    expect(state(w).selectedPath).toBe('合并工作底稿 > 净资产表')
    w.unmount()
  })

  it('树中无该 worksheet 节点时退到合并工作底稿域根，不跑到报表域', async () => {
    const w = await open('internal_arap')

    expect(state(w).selectedNodeKey).toBe('consolidation')
    expect(state(w).selectedPath).toBe('合并工作底稿')
    expect(state(w).selectedPath).not.toContain('资产负债表')
    w.unmount()
  })

  it('模块级入口（无当前 worksheet）停在合并工作底稿域根', async () => {
    const w = await open(undefined)

    expect(state(w).selectedNodeKey).toBe('consolidation')
    expect(state(w).selectedPath).toBe('合并工作底稿')
    w.unmount()
  })

  it('合并报表节点仍归属合并报表域（不被工作底稿分支串走）', async () => {
    const w = await open('elimination')
    state(w).onTreeNodeClick({ key: 'consol_report_bs', label: '合并资产负债表' })
    await flushPromises()

    expect(state(w).selectedPath).toBe('合并报表 > 合并资产负债表')
    w.unmount()
  })
})
