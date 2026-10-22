/**
 * 表间审核分组节点可选中 + 内置勾稽问题清单按节点裁剪（spec formula-governance-coverage-closure R4）。
 *
 * 真挂载 FormulaManagerDialog：树点击原先只认叶子 ⇒ 有内置勾稽结论时的「报表 ↔ 附注」、恒有三个子项的
 * 「合并 ↔ 报表」，规则集与问题清单永远点不到（选中态停在上一个节点，右栏不变）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const { get, put, post, scopeLoad, scopeGetRows, acnrListSheets, acnrListCells, getNoteTree } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(),
  scopeLoad: vi.fn(), scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(), acnrListCells: vi.fn(), getNoteTree: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { get, put, post } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: getNoteTree }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({ loaded: false, tbAddresses: [] }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', () => ({
  useFormulaScopeCatalog: () => ({
    loadScope: scopeLoad, resolveSources: vi.fn(async () => undefined), getScopeRows: scopeGetRows,
    loadGlobal: vi.fn(async () => ({})), resolveScopeSources: vi.fn(async () => undefined),
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets, listCells: acnrListCells, resolve: vi.fn(), resolveFormula: vi.fn(),
    resolveUri: vi.fn(), resolveAddr: vi.fn(), resolveIndex: vi.fn(), resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

const RUN = {
  issue_list: [{ formula_id: 'f1', addr_id: null, description: '资产 ≠ 负债 + 权益', left_value: '10', right_value: '9' }],
  results: [
    { formula_id: 'f1', description: '资产 ≠ 负债 + 权益', expression: 'A = B', passed: false },
    { formula_id: 'f2', description: '净利润一致', expression: 'C = D', passed: true },
  ],
  hints: [], last_computed_at: '2026-10-22T08:00:00', run_id: 'r1', status: 'executed', no_result: false,
}

function create() {
  return shallowMount(FormulaManagerDialog, {
    props: { modelValue: false, rows: [], scope: 'report', projectId: 'project-1', year: 2025, templateType: 'soe' },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}
const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

describe('表间审核分组节点', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      if (u.endsWith('/report-cross-check')) return RUN
      if (u.endsWith('/cross-check-rules')) {
        return { rules: { cross_report_note: [{ rule_id: 'r1', label: '规则一', left_ref: 'A', right_ref: 'B' }],
          cross_consol: [{ rule_id: 'c1', label: '合并规则', left_ref: 'X', right_ref: 'Y' }] }, loaded: {} }
      }
      if (u.includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue([])
    getNoteTree.mockReset(); getNoteTree.mockResolvedValue([])
  })

  async function open() {
    const w = create()
    await w.setProps({ modelValue: true })
    for (let i = 0; i < 4; i++) await flushPromises()
    return w
  }

  it('有子节点的分组节点也能选中：规则集与完整问题清单可见；单条勾稽只看自己', async () => {
    const w = await open()
    const s = state(w)
    // 打开时执行一次内置勾稽，结论挂到「报表 ↔ 附注」下（该节点因此有子节点）
    expect(get.mock.calls.filter((c) => String(c[0]).endsWith('/report-cross-check'))).toHaveLength(1)
    const tree = s.treeData as any[]
    const group = tree.find((n) => n.key === 'cross_check').children.find((n: any) => n.key === 'cross_report_note')
    expect(group.children.map((c: any) => c.key)).toEqual(['cross_exec_f1', 'cross_exec_f2'])

    s.onTreeNodeClick(group)
    await flushPromises()
    expect(s.selectedNodeKey).toBe('cross_report_note')
    expect(s.crossCheckRulesForCurrent.map((r: any) => r.label)).toEqual(['规则一'])
    expect(s.crossCheckIssueRun.executed).toBe(true)
    expect(s.crossCheckIssueRun.outcomes).toHaveLength(2)
    expect(s.crossCheckIssueRun.issues).toHaveLength(1)

    s.onTreeNodeClick(group.children[1])
    await flushPromises()
    expect(s.selectedNodeKey).toBe('cross_exec_f2')
    expect(s.crossCheckIssueRun.outcomes.map((o: any) => o.formula_id)).toEqual(['f2'])
    expect(s.crossCheckIssueRun.issues).toEqual([])

    // 恒有三个静态子项的「合并 ↔ 报表」：原先永远选不中，规则点不到
    const consol = tree.find((n) => n.key === 'cross_check').children.find((n: any) => n.key === 'cross_consol')
    s.onTreeNodeClick(consol)
    await flushPromises()
    expect(s.selectedNodeKey).toBe('cross_consol')
    expect(s.crossCheckRulesForCurrent.map((r: any) => r.label)).toEqual(['合并规则'])
    expect(s.crossCheckIssueRun).toBeNull()
    // 打开期间只执行过一次（问题清单复用同一次响应）
    expect(get.mock.calls.filter((c) => String(c[0]).endsWith('/report-cross-check'))).toHaveLength(1)
    w.unmount()
  })

  it('其他有子节点的分组（报表 / 附注 根节点、底稿循环节点）仍然只展开不选中', async () => {
    const w = await open()
    const s = state(w)
    const before = s.selectedNodeKey
    s.onTreeNodeClick({ key: 'cross_check', label: '表间审核', children: [{ key: 'cross_report_wp' }] })
    s.onTreeNodeClick({ key: 'report', label: '报表', children: [{ key: 'report_balance_sheet' }] })
    s.onTreeNodeClick({ key: 'wp_cycle_e', label: 'E 货币资金', children: [{ key: 'wp_e1', _wpCode: 'E1' }] })
    await flushPromises()
    expect(s.selectedNodeKey).toBe(before)
    expect(s.selectedWpCode).toBe('')
    w.unmount()
  })
})

describe('底稿工作簿节点（R5 走查：点「E1 货币资金」只高亮不切换）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      if (u.endsWith('/formula-push/bindings')) return { supported_wp_codes: ['E1'] }
      if (u.includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue([])
    getNoteTree.mockReset(); getNoteTree.mockResolvedValue([])
  })

  it('点工作簿节点即选中整本：底稿编码就位、不限定页，推送页按本底稿；没选底稿时推送空状态引导去选', async () => {
    const w = create()
    await w.setProps({ modelValue: true })
    for (let i = 0; i < 4; i++) await flushPromises()
    const s = state(w)
    expect(s.pushWpSelected).toBe(false)
    s.onTreeNodeClick({
      key: 'wp_e1', label: 'E1 货币资金', _wpCode: 'E1', _sheetCode: '',
      children: [{ key: 'wp_e1_1', label: 'E1-1', _wpCode: 'E1', _sheetCode: 'E1-1' }],
    })
    await flushPromises()
    expect(s.selectedNodeKey).toBe('wp_e1')
    expect(s.selectedWpCode).toBe('E1')
    expect(s.selectedWpSheetCode).toBe('')
    expect(s.selectedPath).toBe('底稿 > E1 货币资金')
    expect(s.pushWpSelected).toBe(true)
    expect(s.pushWpCode).toBe('E1')
    w.unmount()
  })
})
