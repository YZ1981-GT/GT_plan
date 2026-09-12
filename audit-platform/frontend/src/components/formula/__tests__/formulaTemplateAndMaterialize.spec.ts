/**
 * formulaTemplateAndMaterialize.spec.ts — 「保存为模板 / 引用模板 / 落入项目」守卫
 *
 * 复核发现的三个真实缺陷（本文件锁死修复）：
 *
 * 1. **保存为模板只存"看过的部分"**：`allRowsMap` 只装用户点过的报表，
 *    采集时不补齐 ⇒ 只逛过资产负债表就保存，模板里静默只有 BS 行。
 * 2. **引用模板不落库**：旧实现只改内存（`allRowsMap`），后端 `apply_template`
 *    仅记引用不写公式，弹窗却提示「已引用 N 条」⇒ 关掉即丢的假成功；
 *    且目标报表未加载时 `if (!rows) continue` 整类静默跳过。
 * 3. **预设带不进项目**：旧「自动生成」打后端零实现的 `formula/auto-generate` 恒 404。
 *    现走既有 `POST /api/report-config/clone` 的 `mode: 'sync'`，
 *    把带公式的模板行落成 `project:{id}`（取数层优先消费该口径）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const { get, post, put, confirm, httpGet, acnrListSheets, noteState, scopeState } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  confirm: vi.fn(),
  httpGet: vi.fn(),
  acnrListSheets: vi.fn(),
  noteState: { presets: [] as any[] },
  scopeState: { rows: [] as any[] },
}))

vi.mock('@/services/apiProxy', () => ({ api: { get, post, put } }))
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

describe('保存为模板：必须覆盖全部 6 类报表', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('preset-formulas')) return clone(noteState.presets)
      if (String(url).includes('report-config')) return clone(ROWS_BY_TYPE[cfg?.params?.report_type] ?? [])
      return {}
    })
    post.mockReset(); post.mockResolvedValue({})
    put.mockReset(); put.mockResolvedValue({})
    confirm.mockReset(); confirm.mockResolvedValue('confirm')
    noteState.presets = []
    scopeState.rows = []
    httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
  })

  it('只逛过一类报表也会补齐其余五类后再采集', async () => {
    const w = await mounted()
    // 模拟"只加载过资产负债表"
    state(w).allRowsMap = { balance_sheet: ROWS_BY_TYPE.balance_sheet }
    await flushPromises()

    const data = await state(w).getFormulaConfigData()

    expect(Object.keys(data.coverage).sort()).toEqual([
      'balance_sheet', 'cash_flow_statement', 'cash_flow_supplement',
      'equity_statement', 'impairment_provision', 'income_statement',
      // 覆盖面已扩到附注预设与项目级底稿公式（只读留档段）
      'note_presets', 'workpaper_project',
    ].sort())
    expect(data.note_formulas).toEqual([])
    expect(data.workpaper_formulas).toEqual([])
    expect(data.formulas).toHaveLength(6)
    expect(data.applicable_standard).toBe('soe_standalone')
    expect(data.template_type).toBe('soe')
    w.unmount()
  })

  it('覆盖面含附注预设与项目级底稿公式（只读留档段）', async () => {
    noteState.presets = [
      { id: 'n-1', note_section: '五、1', section_title: '货币资金', formula: "NOTE('货币资金','合计','期末')" },
    ]
    scopeState.rows = [
      {
        id: 'wpf-1', scope: 'workpaper', scopeLabel: '底稿', wpId: 'wp-1',
        sheetName: 'D2-1', targetCell: 'E10', expression: "TB('1122','期末余额')",
        formulaType: 'auto_calc', issueDescription: '', hintText: '', sourceLabel: null,
        lastComputedAt: null, refs: [], addrKey: 'k1', sourceAddrId: null, formulaSource: null,
      },
    ]
    const w = await mounted()

    const data = await state(w).getFormulaConfigData()

    expect(data.note_formulas).toHaveLength(1)
    expect(data.note_formulas[0]).toMatchObject({ note_section: '五、1', section_title: '货币资金' })
    expect(data.workpaper_formulas).toHaveLength(1)
    expect(data.workpaper_formulas[0]).toMatchObject({ scope: 'workpaper', sheet_name: 'D2-1', target_cell: 'E10' })
    expect(data.coverage.note_presets).toBe(1)
    expect(data.coverage.workpaper_project).toBe(1)
    w.unmount()
  })

  it('无公式行不进模板（模板只存真配置）', async () => {
    const w = await mounted()
    const data = await state(w).getFormulaConfigData()

    expect(data.formulas.map((f: any) => f.row_code)).not.toContain('BS-006')
    w.unmount()
  })
})

describe('引用模板：填入必须落库且计数准确', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string, cfg?: any) => {
      if (String(url).includes('report-config/types')) return []
      if (String(url).includes('preset-formulas')) return clone(noteState.presets)
      if (String(url).includes('report-config')) return clone(ROWS_BY_TYPE[cfg?.params?.report_type] ?? [])
      return {}
    })
    post.mockReset(); post.mockResolvedValue({})
    put.mockReset(); put.mockResolvedValue({})
    confirm.mockReset(); confirm.mockResolvedValue('confirm')
    noteState.presets = []
    scopeState.rows = []
    httpGet.mockReset(); httpGet.mockResolvedValue({ data: { scopes: {} } })
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
  })

  it('填入的行逐条 PUT 落库（此前只改内存，关窗即丢）', async () => {
    const w = await mounted()
    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [{ report_type: 'balance_sheet', row_code: 'BS-006', formula: "TB('1122','期末余额')", formula_category: 'auto_calc' }],
    })

    const puts = put.mock.calls.filter(([url]) => String(url).includes('/api/report-config/'))
    expect(puts).toHaveLength(1)
    expect(puts[0][0]).toBe('/api/report-config/bs-2')
    expect(puts[0][1]).toMatchObject({ formula: "TB('1122','期末余额')" })
    w.unmount()
  })

  it('目标报表未加载时不再整类静默跳过（先补齐再匹配）', async () => {
    const w = await mounted()
    state(w).allRowsMap = {}   // 一类都没加载
    await flushPromises()

    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [{ report_type: 'impairment_provision', row_code: 'IMP-001', formula: 'X' }],
    })

    // IMP-001 已有公式 ⇒ 计入"跳过已有"，但必须真的被匹配到（不是 unmatched）
    const requested = get.mock.calls
      .map(([, cfg]) => cfg?.params?.report_type)
      .filter(Boolean)
    expect(requested).toContain('impairment_provision')
    w.unmount()
  })

  it('已有公式的行不覆盖，且不会误报成已保存', async () => {
    const w = await mounted()
    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [{ report_type: 'balance_sheet', row_code: 'BS-002', formula: '不该覆盖' }],
    })

    expect(put).not.toHaveBeenCalled()
    expect(state(w).allRowsMap.balance_sheet[0].formula).toBe("TB('1001','期末余额')")
    w.unmount()
  })

  it('写入前给出预览确认（含将写入/跳过/不存在条数），取消则零写入', async () => {
    const w = await mounted()
    confirm.mockReset()
    confirm.mockRejectedValueOnce('cancel')

    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [
        { report_type: 'balance_sheet', row_code: 'BS-006', formula: "TB('1122','期末余额')" },
        { report_type: 'balance_sheet', row_code: 'BS-002', formula: '已有公式不写' },
        { report_type: 'balance_sheet', row_code: 'BS-999', formula: '行次不存在' },
      ],
    })

    const msg = String(confirm.mock.calls[0]?.[0] ?? '')
    expect(msg).toContain('将写入 1 条')
    expect(msg).toContain('跳过已有 1 条')
    expect(msg).toContain('模板行次不存在 1 条')
    expect(put).not.toHaveBeenCalled()
    expect(state(w).allRowsMap.balance_sheet[1].formula).toBeNull()
    w.unmount()
  })

  it('写入后可整体撤销（逐条 PUT 还原为引用前的值）', async () => {
    const w = await mounted()
    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [{ report_type: 'balance_sheet', row_code: 'BS-006', formula: "TB('1122','期末余额')" }],
    })
    expect(state(w).lastTemplateUndo.entries).toHaveLength(1)

    put.mockClear()
    await state(w).onUndoTemplateApply()

    expect(put).toHaveBeenCalledWith('/api/report-config/bs-2', {
      formula: null, formula_category: null, formula_description: null,
    })
    expect(state(w).allRowsMap.balance_sheet[1].formula).toBeNull()
    expect(state(w).lastTemplateUndo).toBeNull()
    w.unmount()
  })

  it('单行写库失败时内存同步还原（不留"界面已写、库里没有"）', async () => {
    const w = await mounted()
    put.mockRejectedValueOnce(new Error('500'))

    await state(w).onTemplateApplied({
      template_type: 'soe',
      formulas: [{ report_type: 'balance_sheet', row_code: 'BS-006', formula: 'X' }],
    })

    expect(state(w).allRowsMap.balance_sheet[1].formula).toBeNull()
    expect(state(w).lastTemplateUndo).toBeNull()
    w.unmount()
  })

  it('模板版本与当前页不一致时先确认（取消则不动数据）', async () => {
    confirm.mockRejectedValueOnce('cancel')
    const w = await mounted()

    await state(w).onTemplateApplied({
      template_type: 'listed',
      formulas: [{ report_type: 'balance_sheet', row_code: 'BS-006', formula: 'X' }],
    })

    expect(confirm).toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('把报表预设落入项目（替代 404 的自动生成）', () => {
  beforeEach(() => {
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
