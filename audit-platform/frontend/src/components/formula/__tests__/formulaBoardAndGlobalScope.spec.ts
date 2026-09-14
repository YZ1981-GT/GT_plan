/**
 * formulaBoardAndGlobalScope.spec.ts — 「📊 公式看板」与「🌐 全局公式」守卫
 *
 * 用户实测：看板什么都看不到；全局公式里预设也带不进项目。
 *
 * 实测取证（本机）：
 *  - `GET /api/report-config?report_type=balance_sheet&applicable_standard=soe_standalone`
 *    返回 129 行 / 90 条带公式（全 6 类合计 183 条）——数据源并不空；
 *  - 看板却恒 0 条，因为 `allFormulaRows` 里 `if (key.includes('_')) continue`
 *    想跳过缓存键（`soe_balance_sheet`），但 `balance_sheet` 等**每个报表键都含下划线**
 *    ⇒ 报表行被全部跳掉。同一 bug 也在「保存为模板」的 `getFormulaConfigData` 里；
 *  - `GET /api/formula-scope/{pid}/formulas` 7 域全 0：项目级公式存于 wp_formula，
 *    而报表/附注预设是模板级（report_config 唯一键不含 project_id），本就不会进该口径。
 *
 * 本文件锁死：看板能列出报表预设并按域/层级归类；项目级公式与模板预设都被覆盖；
 * 项目级公式不得走报表编辑链路（只能定位）；全局公式 7 域全列且 0 条时也给出解释。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const { get, httpGet, scopeGetRows, acnrListSheets, addressState, scopeState } = vi.hoisted(() => ({
  get: vi.fn(),
  httpGet: vi.fn(),
  scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(),
  addressState: { loaded: false, tbAddresses: [] },
  scopeState: { rows: [] as any[] },
}))

vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/utils/http', () => ({ default: { get: httpGet } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: vi.fn(async () => []) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? ''), fmt: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({
    get loaded() { return addressState.loaded },
    get tbAddresses() { return addressState.tbAddresses },
  }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', async () => {
  const { computed } = await import('vue')
  return {
    useFormulaScopeCatalog: () => ({
      loadScope: vi.fn(async () => []),
      resolveSources: vi.fn(async () => undefined),
      getScopeRows: scopeGetRows,
      loadGlobal: vi.fn(async () => ({})),
      resolveScopeSources: vi.fn(async () => undefined),
      allRows: computed(() => scopeState.rows),
      totalCount: computed(() => scopeState.rows.length),
      globalGrouped: computed(() => {
        const out: Record<string, any[]> = {
          note: [], consol_note: [], consol_worksheet: [], consol_report: [],
          report: [], tb: [], workpaper: [],
        }
        for (const r of scopeState.rows) (out[r.scope] ||= []).push(r)
        return out
      }),
    }),
    SCOPE_LABEL_MAP: {
      note: '单体附注', consol_note: '合并附注', consol_worksheet: '合并工作底稿',
      consol_report: '合并报表', report: '报表', tb: '试算平衡表', workpaper: '底稿',
    },
  }
})
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets, listCells: vi.fn(), resolve: vi.fn(), resolveFormula: vi.fn(),
    resolveUri: vi.fn(), resolveAddr: vi.fn(), resolveIndex: vi.fn(), resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

/** report_config 预设（模板级）：两类报表各 1 条带公式 + 1 条无公式。 */
const REPORT_ROWS: Record<string, any[]> = {
  balance_sheet: [
    { id: 'rc-1', row_code: 'BS-001', row_name: '货币资金', formula: null },
    { id: 'rc-2', row_code: 'BS-002', row_name: '货币资金合计', formula: "TB('1001','期末余额')", formula_category: 'auto_calc', formula_description: '从余额表取数' },
  ],
  income_statement: [
    { id: 'rc-3', row_code: 'IS-002', row_name: '营业收入', formula: "TB('6001','本期发生额')", formula_category: 'auto_calc' },
  ],
}

/** 项目级公式（wp_formula 派生 7 类作用域）。 */
const SCOPE_ROWS = [
  {
    id: 'wpf-1', scope: 'workpaper', scopeLabel: '底稿', wpId: 'wp-1',
    sheetName: 'D2-1', targetCell: 'E10', expression: "TB('1122','期末余额')",
    formulaType: 'auto_calc', issueDescription: '', hintText: '', sourceLabel: null,
    lastComputedAt: null, refs: [], addrKey: 'k1', sourceAddrId: null, formulaSource: null,
  },
]

function create(props: Record<string, unknown> = {}) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: true, rows: [], scope: 'report',
      projectId: 'project-1', year: 2025, ...props,
    },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

async function openBoard(props: Record<string, unknown> = {}) {
  const w = create(props)
  await flushPromises()
  state(w).showFormulaDashboard = true
  await flushPromises()
  await flushPromises()
  return w
}

describe('公式看板：跨域总览不再恒空', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('report-config')) {
        // 该项目尚未落入项目级 ⇒ project: 口径返空（组件回退到模板级）
        if (String(cfg?.params?.applicable_standard).startsWith('project:')) return []
        return REPORT_ROWS[cfg?.params?.report_type] ?? []
      }
      if (String(url).includes('preset-formulas')) return []
      return {}
    })
    httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    scopeState.rows = []
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('列出报表预设公式（此前被 key.includes("_") 全部跳掉 ⇒ 恒 0 条）', async () => {
    const w = await openBoard()

    const rows = state(w).allFormulaRows as any[]
    // 3 行 report_config 里只有 2 行带公式（无公式行不计入看板）
    expect(rows.length).toBe(2)
    expect(rows.map((r) => r.row_code).sort()).toEqual(['BS-002', 'IS-002'])
    expect(rows.every((r) => r._level === '模板预设')).toBe(true)
    w.unmount()
  })

  it('项目级公式（wp_formula 各作用域）一并纳入总览', async () => {
    scopeState.rows = SCOPE_ROWS as any[]
    const w = await openBoard()

    const rows = state(w).allFormulaRows as any[]
    const project = rows.filter((r) => r._level === '项目级')
    expect(project).toHaveLength(1)
    expect(project[0]).toMatchObject({ _domainLabel: '底稿', row_code: 'E10', row_name: 'D2-1' })
    w.unmount()
  })

  it('维度可用：按域分组 + 按域/层级筛选 + 搜索命中域名', async () => {
    scopeState.rows = SCOPE_ROWS as any[]
    const w = await openBoard()

    expect(state(w).dashboardGroupBy).toBe('domain')
    expect((state(w).dashboardGroupedData as any[]).map((g) => g.key).sort())
      .toEqual(['report', 'workpaper'])

    state(w).dashboardFilterLevel = '项目级'
    await flushPromises()
    expect((state(w).dashboardFilteredRows as any[]).map((r) => r.id)).toEqual(['wpf-1'])

    state(w).dashboardFilterLevel = ''
    state(w).dashboardFilterDomain = 'report'
    await flushPromises()
    expect((state(w).dashboardFilteredRows as any[]).every((r) => r._domain === 'report')).toBe(true)

    state(w).dashboardFilterDomain = ''
    state(w).dashboardSearch = '底稿'
    await flushPromises()
    expect((state(w).dashboardFilteredRows as any[]).map((r) => r.id)).toEqual(['wpf-1'])
    w.unmount()
  })

  it('只有报表预设可直接编辑；项目级公式只给定位（防把 wp_formula id 发到 report-config）', async () => {
    scopeState.rows = SCOPE_ROWS as any[]
    const w = await openBoard()
    const rows = state(w).allFormulaRows as any[]
    const reportRow = rows.find((r) => r._domain === 'report')
    const wpRow = rows.find((r) => r._level === '项目级')

    expect(reportRow._editable).toBe(true)
    expect(wpRow._editable).toBe(false)

    state(w).onDashboardEdit(wpRow)
    expect(state(w).showFormulaEdit).toBe(false)

    state(w).onDashboardEdit(reportRow)
    expect(state(w).showFormulaEdit).toBe(true)
    expect(state(w).editingRow.row_code).toBe(reportRow.row_code)
    w.unmount()
  })

  it('覆盖情况文案给出每类条数（空态不只显示 No Data）', async () => {
    const w = await openBoard()

    expect(state(w).dashboardCoverageText).toContain('报表预设 2 条')
    expect(state(w).dashboardCoverageText).toContain('项目级公式 0 条')
    w.unmount()
  })
})

describe('项目级优先：落入项目后界面必须跟着变', () => {
  beforeEach(() => {
    get.mockReset()
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    scopeState.rows = []
  })

  it('存在 project:{id} 行时优先读它，并标为项目级', async () => {
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('report-config')) {
        const std = cfg?.params?.applicable_standard
        if (std === 'project:project-1' && cfg?.params?.report_type === 'balance_sheet') {
          return [{ id: 'p-1', row_code: 'BS-002', row_name: '货币资金', formula: "TB('1001','期末余额')", formula_category: 'auto_calc' }]
        }
        if (String(std).startsWith('project:')) return []
        return REPORT_ROWS[cfg?.params?.report_type] ?? []
      }
      return {}
    })

    const w = await openBoard()

    expect(state(w).reportStandardByType.balance_sheet).toBe('project:project-1')
    expect(state(w).reportStandardByType.income_statement).toBe('soe_standalone')
    const bs = (state(w).allFormulaRows as any[]).find((r) => r.id === 'p-1')
    expect(bs._level).toBe('项目级')
    w.unmount()
  })

  it('项目级为空时退回模板级（空数组不得当成"已配置"）', async () => {
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('report-config')) {
        if (String(cfg?.params?.applicable_standard).startsWith('project:')) return []
        return REPORT_ROWS[cfg?.params?.report_type] ?? []
      }
      return {}
    })

    const w = await openBoard()

    expect(state(w).reportStandardByType.balance_sheet).toBe('soe_standalone')
    expect((state(w).allFormulaRows as any[]).every((r) => r._level === '模板预设')).toBe(true)
    w.unmount()
  })
})

describe('看板分类健康度维度', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('report-config')) {
        if (String(cfg?.params?.applicable_standard).startsWith('project:')) return []
        if (cfg?.params?.report_type === 'balance_sheet') {
          return [
            { id: 'c-1', row_code: 'BS-002', formula: "TB('1001','期末余额')", formula_category: 'auto_calc' },
            { id: 'c-2', row_code: 'BS-003', formula: "TB('1101','期末余额')", formula_category: null },
          ]
        }
        return []
      }
      return {}
    })
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    scopeState.rows = []
  })

  it('未分类计数真实（无 formula_category 的行不被自动补类）', async () => {
    const w = await openBoard()

    // fetchReportRows 会给"有公式无分类"补 auto_calc ⇒ 该口径下未分类应为 0
    expect(state(w).dashboardCategorizedCount).toEqual({ yes: 2, no: 0 })
    w.unmount()
  })

  it('按已分类/未分类筛选生效', async () => {
    const w = await openBoard()
    state(w).allRowsMap = {
      balance_sheet: [
        { id: 'x-1', row_code: 'BS-002', formula: 'A', formula_category: 'auto_calc' },
        { id: 'x-2', row_code: 'BS-003', formula: 'B', formula_category: null },
      ],
    }
    await flushPromises()

    expect(state(w).dashboardCategorizedCount).toEqual({ yes: 1, no: 1 })

    state(w).dashboardFilterCategorized = 'no'
    await flushPromises()
    expect((state(w).dashboardFilteredRows as any[]).map((r) => r.id)).toEqual(['x-2'])

    state(w).dashboardFilterCategorized = 'yes'
    await flushPromises()
    expect((state(w).dashboardFilteredRows as any[]).map((r) => r.id)).toEqual(['x-1'])
    w.unmount()
  })
})

describe('全局公式：7 域全列 + 说明预设归属', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async () => ({}))
    httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    scopeState.rows = []
  })

  it('项目级公式为 0 时仍列出全部 7 个作用域分组', async () => {
    const w = create()
    await flushPromises()

    const groups = state(w).globalScopeGroups as any[]
    expect(groups).toHaveLength(7)
    expect(groups.map((g) => g.scope)).toContain('workpaper')
    expect(state(w).globalScopeNonEmpty).toHaveLength(0)
    w.unmount()
  })

  it('有项目级公式时空态引导消失、对应分组非空', async () => {
    scopeState.rows = SCOPE_ROWS as any[]
    const w = create()
    await flushPromises()

    expect(state(w).globalScopeNonEmpty.map((g: any) => g.scope)).toEqual(['workpaper'])
    w.unmount()
  })
})
