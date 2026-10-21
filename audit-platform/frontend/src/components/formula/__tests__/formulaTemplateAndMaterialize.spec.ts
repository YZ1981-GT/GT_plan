/**
 * formulaTemplateAndMaterialize.spec.ts — 报表行「有效定义 / 本项目适配」+「落入项目」守卫
 *
 * spec formula-global-settings-sync（R1.2 / R1.4 / R6 / R13.10 / R14.2）：
 * 1. **旧「保存为模板 / 引用模板 / 撤销引用」已下线**：它走共享配置 formula_config（只回填报表段、
 *    引用会写全局行），后端已 410。改为顶栏 FormulaSettingsToolbar（订阅一层，只写本项目层）。
 * 2. **项目上下文读本项目有效定义**：旧口径「有项目行就只显示项目行」会把只适配了几行的项目
 *    其余全局行全部藏掉；现读 `/formula-settings/report/effective`，每行带层级标签。
 * 3. **保存写本项目适配**（带本项目版本 CAS），不再 PUT 全局行（非管理员 403）；批量只发改过的行。
 * 4. **预设带进项目**：走既有 `POST /api/report-config/clone` 的 `mode: 'sync'`（替代 404 的 auto-generate）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import { invalidateEffectiveReport } from '@/components/formula/settings/reportEffectiveRows'

const { get, post, put, del, confirm, httpGet, acnrListSheets, noteState, scopeState } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
  confirm: vi.fn(),
  httpGet: vi.fn(),
  acnrListSheets: vi.fn(),
  noteState: { presets: [] as any[] },
  scopeState: { rows: [] as any[] },
}))

vi.mock('@/services/apiProxy', () => ({ api: { get, post, put, delete: del } }))
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
  useAddressRegistry: () => ({ loaded: false, tbAddresses: [] }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', async () => {
  const { computed } = await import('vue')
  return {
    useFormulaScopeCatalog: () => ({
      loadScope: vi.fn(async () => []),
      resolveSources: vi.fn(async () => undefined),
      getScopeRows: vi.fn(() => []),
      loadGlobal: vi.fn(async () => ({})),
      resolveScopeSources: vi.fn(async () => undefined),
      allRows: computed(() => scopeState.rows),
      totalCount: computed(() => scopeState.rows.length),
      globalGrouped: computed(() => ({
        note: [], consol_note: [], consol_worksheet: [], consol_report: [],
        report: [], tb: [], workpaper: [],
      })),
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
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm },
  }
})

/**
 * 每次请求返回**深拷贝** —— 组件会就地改这些行对象（引用模板即写 formula），
 * 共享同一份 fixture 会让前一个用例污染后一个（实测：写过 BS-006 后，
 * 后续用例把它当"已有公式"跳过 ⇒ 断言莫名打红）。
 */
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

/** 每类报表各 1 条带公式（用于验证"全 6 类都被采集"）。 */
const ROWS_BY_TYPE: Record<string, any[]> = {
  balance_sheet: [
    { id: 'bs-1', row_code: 'BS-002', row_name: '货币资金', formula: "TB('1001','期末余额')", formula_category: 'auto_calc' },
    { id: 'bs-2', row_code: 'BS-006', row_name: '应收账款', formula: null },
  ],
  income_statement: [{ id: 'is-1', row_code: 'IS-002', row_name: '营业收入', formula: "TB('6001','本期')" }],
  cash_flow_statement: [{ id: 'cfs-1', row_code: 'CFS-001', row_name: '经营流入', formula: "TB('1001','本期')" }],
  equity_statement: [{ id: 'eq-1', row_code: 'EQ-001', row_name: '实收资本', formula: "TB('4001','期末余额')" }],
  cash_flow_supplement: [{ id: 'cfss-1', row_code: 'CFSS-001', row_name: '净利润', formula: "TB('4103','本期')" }],
  impairment_provision: [{ id: 'imp-1', row_code: 'IMP-001', row_name: '坏账准备', formula: "TB('1231','期末余额')" }],
}

function create(props: Record<string, unknown> = {}) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: true, rows: [], scope: 'report',
      projectId: 'project-1', year: 2025, templateType: 'soe', ...props,
    },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

async function mounted(props: Record<string, unknown> = {}) {
  const w = create(props)
  await flushPromises()
  return w
}

/** 本项目有效定义（formula-settings/report/effective）：BS-002 本项目改过，BS-006 跟随全局。 */
const EFFECTIVE = {
  domain: 'report', project_id: 'project-1', scope: 'soe_standalone', frozen: false, can_edit_global: false,
  slots: [
    {
      slot_key: 'balance_sheet:BS-006', label: '资产负债表 BS-006 应收账款', layer: 'global', layer_label: '全局',
      definition: { formula: "TB('1122','期末余额')", formula_category: 'auto_calc' }, disabled: false, pending: false,
      structure: { row_number: 6, row_name: '应收账款', indent_level: 1 },
      global_definition: { formula: "TB('1122','期末余额')", formula_category: 'auto_calc' }, global_version: 4,
      local_definition: null, local_version: null, pinned: false,
    },
    {
      slot_key: 'balance_sheet:BS-002', label: '资产负债表 BS-002 货币资金', layer: 'project', layer_label: '本项目',
      definition: { formula: "TB('1001','期末余额')+1", formula_category: 'auto_calc' }, disabled: false, pending: true,
      structure: { row_number: 2, row_name: '货币资金', indent_level: 1 },
      global_definition: { formula: "TB('1001','期末余额')", formula_category: 'auto_calc' }, global_version: 4,
      local_definition: { formula: "TB('1001','期末余额')+1" }, local_version: 2, pinned: false,
    },
    {
      slot_key: 'income_statement:IS-002', label: '利润表 IS-002 营业收入', layer: 'global', layer_label: '全局',
      definition: { formula: "TB('6001','本期')" }, disabled: false, pending: false,
      structure: { row_number: 2, row_name: '营业收入' }, global_definition: { formula: "TB('6001','本期')" },
      global_version: 1, local_definition: null, local_version: null, pinned: false,
    },
  ],
}
const OVERRIDES_URL = '/api/projects/project-1/formula-settings/report/overrides'

function resetMocks() {
  invalidateEffectiveReport()
  get.mockReset()
  get.mockImplementation(async (url: string, cfg?: any) => {
    if (String(url).includes('/formula-settings/report/effective')) return clone(EFFECTIVE)
    if (String(url).includes('report-config/types')) return []
    if (String(url).includes('preset-formulas')) return clone(noteState.presets)
    if (String(url).includes('report-config')) {
      return clone((ROWS_BY_TYPE[cfg?.params?.report_type] ?? []).map((r) => ({ ...r, formula_version: 3 })))
    }
    return {}
  })
  post.mockReset(); post.mockResolvedValue({})
  put.mockReset(); put.mockImplementation(async (url: string, body: any) => (
    String(url) === OVERRIDES_URL ? { saved: body.items.map((i: any) => ({ slot_key: i.slot_key, version: 3 })) } : { formula_version: 4 }))
  del.mockReset(); del.mockResolvedValue({ restored: ['balance_sheet:BS-002'] })
  confirm.mockReset(); confirm.mockResolvedValue('confirm')
  noteState.presets = []
  scopeState.rows = []
  httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
  acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
}

describe('旧共享配置公式模板已下线，入口改走订阅机制（R13.10 / R14.2）', () => {
  beforeEach(resetMocks)

  it('组件里不再有 formula_config 的保存 / 引用 / 撤销引用', async () => {
    const w = await mounted()
    for (const gone of ['getFormulaConfigData', 'onTemplateApplied', 'onUndoTemplateApply', 'lastTemplateUndo']) {
      expect(state(w)[gone]).toBeUndefined()
    }
    // 顶栏入口带上当前公式域与项目口径
    expect(state(w).settingsDomain).toBe('report')
    expect(typeof state(w).askApplyScope).toBe('function')
    w.unmount()
  })
})

describe('项目上下文：报表行 = 本项目有效定义，保存写本项目适配（R1.2 / R1.4 / R6）', () => {
  beforeEach(resetMocks)

  it('读有效定义：全局行与本项目行一起显示、按行号排序、逐行带层级与待确认', async () => {
    const w = await mounted()
    const rows = await state(w).fetchReportRows('balance_sheet')

    expect(rows.map((r: any) => r.row_code)).toEqual(['BS-002', 'BS-006'])
    expect(rows[0]).toMatchObject({ _layer: 'project', _layer_label: '本项目', _pending: true, _local_version: 2 })
    expect(rows[1]).toMatchObject({ _layer: 'global', _layer_label: '全局', formula: "TB('1122','期末余额')" })
    // 不再按旧口径单读 project:{id} 行（只适配几行的项目会把其余全局行藏掉）
    const legacy = get.mock.calls.filter(([url, cfg]) => String(url).includes('/api/report-config')
      && String(cfg?.params?.applicable_standard || '').startsWith('project:'))
    expect(legacy).toEqual([])
    w.unmount()
  })

  it('行内保存：写本项目适配（带本项目版本），不 PUT 全局报表配置行', async () => {
    const w = await mounted()
    const [row] = await state(w).fetchReportRows('balance_sheet')
    state(w).editFormula = "TB('1001','期末余额')+2"
    state(w).editCategory = 'auto_calc'
    state(w).editDescription = '本项目口径'
    await state(w).saveEdit(row)

    const calls = put.mock.calls.filter(([url]) => String(url) === OVERRIDES_URL)
    expect(calls).toHaveLength(1)
    expect(calls[0][1].items).toEqual([expect.objectContaining({
      slot_key: 'balance_sheet:BS-002', expected_version: 2,
      definition: expect.objectContaining({ formula: "TB('1001','期末余额')+2", formula_description: '本项目口径' }),
    })])
    expect(put.mock.calls.some(([url]) => String(url).startsWith('/api/report-config/'))).toBe(false)
    expect(row).toMatchObject({ formula: "TB('1001','期末余额')+2", _local_version: 3, _layer: 'project' })
    w.unmount()
  })

  it('跟随全局的行第一次改：不带版本（新建本项目适配）；改回与全局相同时标回「全局」', async () => {
    const w = await mounted()
    const rows = await state(w).fetchReportRows('balance_sheet')
    const bs006 = rows[1]
    state(w).editFormula = "TB('1122','期末余额')"
    state(w).editCategory = 'auto_calc'
    state(w).editDescription = ''
    await state(w).saveEdit(bs006)

    const body = put.mock.calls.find(([url]) => String(url) === OVERRIDES_URL)![1]
    expect(body.items[0]).toMatchObject({ slot_key: 'balance_sheet:BS-006', expected_version: null })
    expect(bs006).toMatchObject({ _layer: 'global', _layer_label: '全局' })
    w.unmount()
  })

  it('保存失败：行保持原值（不留「界面已改、库里没有」）', async () => {
    const w = await mounted()
    const [row] = await state(w).fetchReportRows('balance_sheet')
    put.mockRejectedValueOnce({ response: { status: 409, data: { detail: { message: '本项目公式已被他人修改，请刷新后重试' } } } })
    state(w).editFormula = 'X'
    await state(w).saveEdit(row)

    expect(row.formula).toBe("TB('1001','期末余额')+1")
    w.unmount()
  })

  it('「💾 保存」只发改过的行，一次写入本项目适配', async () => {
    const w = await mounted()
    const rows = await state(w).fetchReportRows('balance_sheet')
    state(w).allRowsMap = { balance_sheet: rows }
    await flushPromises()
    state(w).allRowsMap.balance_sheet[1].formula = "TB('1122','期末余额')*2"
    await state(w).onSaveAllFormulas()

    const calls = put.mock.calls.filter(([url]) => String(url) === OVERRIDES_URL)
    expect(calls).toHaveLength(1)
    expect(calls[0][1].items.map((i: any) => i.slot_key)).toEqual(['balance_sheet:BS-006'])
    w.unmount()
  })

  it('恢复为全局：确认后删除本项目适配并重取有效定义', async () => {
    const w = await mounted()
    const [row] = await state(w).fetchReportRows('balance_sheet')
    get.mockClear()
    await state(w).onRestoreGlobal(row)

    expect(del).toHaveBeenCalledWith(OVERRIDES_URL, expect.objectContaining({ params: { slot_key: ['balance_sheet:BS-002'] } }))
    expect(get.mock.calls.some(([url]) => String(url).includes('/formula-settings/report/effective'))).toBe(true)
    w.unmount()
  })

  it('恢复为全局：取消确认则零写入', async () => {
    const w = await mounted()
    const [row] = await state(w).fetchReportRows('balance_sheet')
    confirm.mockRejectedValueOnce('cancel')
    await state(w).onRestoreGlobal(row)

    expect(del).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('无项目上下文（管理员全局入口）：保存报表配置行带 formula_version', () => {
  beforeEach(resetMocks)

  it('行内保存 PUT 报表配置行，带载入时的版本并采用响应里的新版本', async () => {
    const w = await mounted({ projectId: '' })
    const rows = await state(w).fetchReportRows('balance_sheet')
    const row = rows.find((r: any) => r.row_code === 'BS-002')
    state(w).editFormula = "TB('1001','期末余额')"
    state(w).editCategory = 'auto_calc'
    state(w).editDescription = ''
    await state(w).saveEdit(row)

    expect(put).toHaveBeenCalledWith('/api/report-config/bs-1', expect.objectContaining({ expected_version: 3 }))
    expect(row.formula_version).toBe(4)
    expect(get.mock.calls.some(([url]) => String(url).includes('/formula-settings/'))).toBe(false)
    w.unmount()
  })
})

describe('把报表预设落入项目（替代 404 的自动生成）', () => {
  beforeEach(() => {
    invalidateEffectiveReport()
    get.mockReset()
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('preset-formulas')) return clone(noteState.presets)
      if (String(url).includes('report-config')) return clone(ROWS_BY_TYPE[cfg?.params?.report_type] ?? [])
      return {}
    })
    post.mockReset()
    post.mockResolvedValue({ created: 183, skipped: 0, updated: 0, count: 183 })
    put.mockReset(); put.mockResolvedValue({})
    confirm.mockReset(); confirm.mockResolvedValue('confirm')
    noteState.presets = []
    scopeState.rows = []
    httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
  })

  it('走 /api/report-config/clone 的 mode=sync，且不再请求 auto-generate', async () => {
    const w = await mounted()
    await state(w).onMaterializeReportPresets()

    const calls = post.mock.calls.filter(([url]) => String(url).includes('report-config/clone'))
    expect(calls).toHaveLength(1)
    expect(calls[0][1]).toMatchObject({
      project_id: 'project-1',
      applicable_standard: 'soe_standalone',
      mode: 'sync',
      overwrite: false,
    })
    expect(post.mock.calls.some(([url]) => String(url).includes('auto-generate'))).toBe(false)
    w.unmount()
  })

  it('用户取消确认时不发请求', async () => {
    confirm.mockRejectedValueOnce('cancel')
    const w = await mounted()
    await state(w).onMaterializeReportPresets()

    expect(post.mock.calls.some(([url]) => String(url).includes('report-config/clone'))).toBe(false)
    w.unmount()
  })
})
