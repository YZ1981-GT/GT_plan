/**
 * 报表格内编辑提交（spec excel-style-table-editing 5.4）：权益表 / 减值表不再双击弹输入框，
 * 提交走 onRvCellEdit → PUT /reports/cell；粘贴 / 清空一个区域连发多格时同一批只重新取数一次。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
const msg = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }))
const prompt = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessage: msg, ElMessageBox: { prompt } }))
const put = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), put } }))
const handleApiError = vi.hoisted(() => vi.fn())
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))

import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import { useReportColumns } from '../useReportColumns'
import { useReportContextMenu } from '../useReportContextMenu'

function setup(opts: { tab?: string; year?: number | null } = {}) {
  const fetchReport = vi.fn().mockResolvedValue(undefined)
  const toReportRow = vi.fn()
  const yearRef = ref<number | null>(opts.year === undefined ? 2025 : opts.year)
  const cm = useReportContextMenu({
    projectId: computed(() => 'p1'),
    year: computed(() => yearRef.value),
    activeTab: ref(opts.tab ?? 'equity_statement'),
    rows: ref([]),
    reportMode: ref('audited'),
    isConsolidated: computed(() => false),
    fetchReport,
    getRowType: () => 'data',
    goToNote: vi.fn(),
    showFormulaManager: ref(false),
    openTrustScore: vi.fn(),
    rvCtx: { closeContextMenu: vi.fn(), contextMenu: { rowData: null, itemName: '' } } as never,
    rvPenetrate: { toReportRow, toWorkpaperEditor: vi.fn() } as never,
    onDrilldown: vi.fn(),
  })
  return { cm, fetchReport, toReportRow }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
})
afterEach(() => vi.useRealTimers())

describe('onRvCellEdit', () => {
  it('同一批两格：各 PUT 一次（列键 / 年度 / 报表类型照传），只重新取数一次、提示「已保存 2 格」', async () => {
    put.mockResolvedValue({})
    const { cm, fetchReport } = setup()
    const row = { row_code: 'EQ-005' }
    cm.onRvCellEdit(row, 'cy:oci', 12.5, 'current_year')
    cm.onRvCellEdit(row, 'py:paid_in_capital', null, 'prior_year')
    expect(put).toHaveBeenCalledTimes(2)
    const cfg = { params: { year: 2025, report_type: 'equity_statement' } }
    expect(put).toHaveBeenNthCalledWith(1, '/api/projects/p1/reports/cell',
      { row_code: 'EQ-005', column_key: 'cy:oci', value: 12.5, year_key: 'current_year' }, cfg)
    expect(put).toHaveBeenNthCalledWith(2, '/api/projects/p1/reports/cell',
      { row_code: 'EQ-005', column_key: 'py:paid_in_capital', value: null, year_key: 'prior_year' }, cfg)
    expect(fetchReport).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(250)
    expect(fetchReport).toHaveBeenCalledTimes(1)
    expect(msg.success).toHaveBeenCalledWith('已保存 2 格')
  })

  it('减值表不带年度键；保存失败报错、仍重新取数（格子恢复成服务器上的值）、不提示已保存', async () => {
    put.mockRejectedValue(new Error('500'))
    const { cm, fetchReport } = setup({ tab: 'impairment_provision' })
    cm.onRvCellEdit({ row_code: 'IMP-001' }, 'provision', 40)
    expect(put).toHaveBeenCalledWith('/api/projects/p1/reports/cell',
      { row_code: 'IMP-001', column_key: 'provision', value: 40 },
      { params: { year: 2025, report_type: 'impairment_provision' } })
    await vi.advanceTimersByTimeAsync(250)
    expect(handleApiError).toHaveBeenCalledTimes(1)
    expect(fetchReport).toHaveBeenCalledTimes(1)
    expect(msg.success).not.toHaveBeenCalled()
  })

  it('没填审计年度：提示去填，不发请求；没有行次的行不发请求', async () => {
    const { cm, fetchReport } = setup({ year: null })
    cm.onRvCellEdit({ row_code: 'EQ-005' }, 'cy:oci', 1, 'current_year')
    expect(msg.warning).toHaveBeenCalledWith(MISSING_AUDIT_YEAR_MESSAGE)
    const ok = setup()
    ok.cm.onRvCellEdit({ row_code: '' }, 'cy:oci', 1, 'current_year')
    expect(put).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(250)
    expect(fetchReport).not.toHaveBeenCalled()
  })
})

describe('onRvCellDblClick', () => {
  it('权益表 / 减值表双击不再弹输入框', () => {
    for (const tab of ['equity_statement', 'impairment_provision']) {
      const { cm } = setup({ tab })
      cm.onRvCellDblClick({ row_code: 'X-1', row_name: '项目' }, { label: '资本公积', property: 'cy:capital_reserve' })
    }
    expect(prompt).not.toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
  })

  it('主表双击金额仍穿透', () => {
    const { cm, toReportRow } = setup({ tab: 'balance_sheet' })
    cm.onRvCellDblClick({ row_code: 'BS-002' }, { label: '本期金额' })
    expect(toReportRow).toHaveBeenCalledWith('balance_sheet', 'BS-002')
  })
})

describe('减值表列键契约', () => {
  it('与导出模板 {{imp:CODE:列键}} 同一套列键（后端按它存取 source_accounts；原先 merge_add / writeoff 等对不上）', () => {
    // 现算（2026-10-28，backend/data/audit_report_templates/financial_statements/soe_*.xlsx）：
    // provision / merge_increase / other_increase / reversal / write_off / merge_decrease / other_decrease 各 36 处，
    // subtotal_increase / subtotal_decrease 为合计列，opening_balance / closing_balance 为年初 / 期末
    const { impIncCols, impDecCols } = useReportColumns({ isConsolidated: computed(() => false), activeTab: ref('impairment_provision'), rows: ref([]) } as never)
    expect(impIncCols.map((c) => c.key)).toEqual(['provision', 'merge_increase', 'other_increase', 'subtotal_increase'])
    expect(impDecCols.map((c) => c.key)).toEqual(['reversal', 'write_off', 'merge_decrease', 'other_decrease', 'subtotal_decrease'])
    expect([...impIncCols, ...impDecCols].filter((c) => c.sum).map((c) => c.key)).toEqual(['subtotal_increase', 'subtotal_decrease'])
  })
})
