/**
 * useReportCellActions.spec.ts — composable 单元测试
 *
 * 验证 useReportCellActions 关键路径：
 * - onDrilldown: 调用 getReportDrilldown API，设置 drilldownData
 * - onRvCellClick: 通过 rvCtx.selectCell 设置选中态
 * - onRvCtxCopy: 调用 rvCtx.copySelectedValues
 * - onRvCtxDrillDown: 委托给 onDrilldown
 *
 * Validates: Requirements 3.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockRouterPush,
    currentRoute: ref({ params: { projectId: 'proj-1' }, fullPath: '/projects/proj-1/reports' }),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockRejectedValue('cancel') },
}))

const mockGetReportDrilldown = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({
  getReportDrilldown: (...args: any[]) => mockGetReportDrilldown(...args),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('@/utils/formatters', () => ({
  fmtAmount: (v: number) => String(v),
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn() },
}))

const mockNavPush = vi.fn()
vi.mock('@/composables/useNavigationStack', () => ({
  useNavigationStack: () => ({ push: mockNavPush, pop: vi.fn(), stack: ref([]) }),
}))

import { ElMessage } from 'element-plus'
import { useReportCellActions } from '../useReportCellActions'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createMockRvCtx() {
  return {
    selectedCells: ref<any[]>([]),
    contextMenu: {
      rowData: null as any,
      itemName: '',
    },
    cellClassName: vi.fn(),
    isCellSelected: vi.fn().mockReturnValue(false),
    selectCell: vi.fn(),
    selectRange: vi.fn(),
    selectRow: vi.fn(),
    selectColumn: vi.fn(),
    selectAll: vi.fn(),
    startDrag: vi.fn(),
    updateDrag: vi.fn(),
    endDrag: vi.fn(),
    clearSelection: vi.fn(),
    getSelectionBounds: vi.fn(),
    registerCellValueGetter: vi.fn(),
    setupTableDrag: vi.fn(),
    openContextMenu: vi.fn(),
    closeContextMenu: vi.fn(),
    copySelectedValues: vi.fn(),
    sumSelectedValues: vi.fn().mockReturnValue(0),
    selectionCount: computed(() => 0),
    selectionStats: computed(() => ({ count: 0, numCount: 0, sum: 0, avg: 0, max: 0, min: 0 })),
  }
}

function createMockRvPenetrate() {
  return {
    toReportRow: vi.fn(),
    toWorkpaperEditor: vi.fn(),
  }
}

function createMockRvComments() {
  return {
    comments: ref([]),
    loadComments: vi.fn(),
  }
}

function createOptions(overrides: Partial<any> = {}) {
  const rows = ref<ReportRow[]>([
    { row_code: 'BS-001', row_name: '货币资金', current_period_amount: '1000', prior_period_amount: '800', formula_used: null, source_accounts: null, indent_level: 1, is_total_row: false },
    { row_code: 'BS-002', row_name: '应收账款', current_period_amount: '2000', prior_period_amount: '1500', formula_used: null, source_accounts: null, indent_level: 1, is_total_row: false },
  ])

  return {
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2025),
    activeTab: ref('balance_sheet'),
    rows,
    reportMode: ref('audited'),
    isConsolidated: computed(() => false),
    fetchReport: vi.fn().mockResolvedValue(undefined),
    activeTabLabel: computed(() => '资产负债表'),
    getRowType: vi.fn().mockReturnValue('data'),
    goToNote: vi.fn(),
    consistencyResult: ref({ checks: [] }),
    showFormulaManager: ref(false),
    openTrustScore: vi.fn(),
    rvCtx: createMockRvCtx(),
    rvPenetrate: createMockRvPenetrate(),
    rvComments: createMockRvComments(),
    ...overrides,
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useReportCellActions — onDrilldown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls getReportDrilldown API with correct params and sets drilldownData', async () => {
    const fakeResult = {
      row_code: 'BS-001',
      row_name: '货币资金',
      amount: '1000',
      accounts: [
        { code: '1001', name: '库存现金', amount: '500', unadjusted_amount: '400', audited_amount: '500' },
      ],
    }
    mockGetReportDrilldown.mockResolvedValue(fakeResult)

    const options = createOptions()
    const { onDrilldown, drilldownVisible, drilldownLoading, drilldownData } = useReportCellActions(options)

    const row: ReportRow = { row_code: 'BS-001', row_name: '货币资金', current_period_amount: '1000', prior_period_amount: '800', formula_used: null, source_accounts: null, indent_level: 1, is_total_row: false }
    await onDrilldown(row)

    expect(mockGetReportDrilldown).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', 'BS-001')
    expect(drilldownVisible.value).toBe(true)
    expect(drilldownLoading.value).toBe(false)
    expect(drilldownData.value).not.toBeNull()
    // In audited mode, should use audited_amount
    expect(drilldownData.value!.accounts[0].amount).toBe('500')
  })

  it('skips drilldown for total rows', async () => {
    const options = createOptions()
    const { onDrilldown } = useReportCellActions(options)

    const totalRow: ReportRow = { row_code: 'BS-T01', row_name: '合计', current_period_amount: '3000', prior_period_amount: '2300', formula_used: null, source_accounts: null, indent_level: 0, is_total_row: true }
    await onDrilldown(totalRow)

    expect(mockGetReportDrilldown).not.toHaveBeenCalled()
  })

  it('skips drilldown when row_code is empty', async () => {
    const options = createOptions()
    const { onDrilldown } = useReportCellActions(options)

    const headerRow: ReportRow = { row_code: '', row_name: '流动资产：', current_period_amount: null as any, prior_period_amount: null as any, formula_used: null, source_accounts: null, indent_level: 0, is_total_row: false }
    await onDrilldown(headerRow)

    expect(mockGetReportDrilldown).not.toHaveBeenCalled()
  })
})

describe('useReportCellActions — onRvCellClick', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls rvCtx.selectCell with correct row/col indices', () => {
    const options = createOptions()
    const { onRvCellClick } = useReportCellActions(options)

    const row = options.rows.value[0]
    const column = { label: '本期金额', property: 'current_period_amount', index: 2 }
    const event = { ctrlKey: false, metaKey: false, shiftKey: false } as MouseEvent

    onRvCellClick(row, column, document.createElement('td'), event)

    expect(options.rvCtx.selectCell).toHaveBeenCalledWith(0, 2, '1000', false, false)
    expect(options.rvCtx.contextMenu.rowData).toBe(row)
    expect(options.rvCtx.contextMenu.itemName).toBe('货币资金')
  })

  it('passes ctrlKey for multi-select', () => {
    const options = createOptions()
    const { onRvCellClick } = useReportCellActions(options)

    const row = options.rows.value[1]
    const column = { label: '上期金额', property: 'prior_period_amount', index: 3 }
    const event = { ctrlKey: true, metaKey: false, shiftKey: false } as MouseEvent

    onRvCellClick(row, column, document.createElement('td'), event)

    // Value extracted: row.current_period_amount ?? row[column.property]
    // row.current_period_amount = '2000' (non-null), so that's the value passed
    expect(options.rvCtx.selectCell).toHaveBeenCalledWith(1, 3, '2000', true, false)
  })
})

describe('useReportCellActions — onRvCtxCopy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls rvCtx.copySelectedValues and shows success message', () => {
    const options = createOptions()
    const { onRvCtxCopy } = useReportCellActions(options)

    onRvCtxCopy()

    expect(options.rvCtx.closeContextMenu).toHaveBeenCalled()
    expect(options.rvCtx.copySelectedValues).toHaveBeenCalled()
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith('已复制')
  })
})

describe('useReportCellActions — onRvCtxDrillDown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('delegates to onDrilldown with contextMenu.rowData', async () => {
    const fakeResult = {
      row_code: 'BS-002',
      row_name: '应收账款',
      amount: '2000',
      accounts: [],
    }
    mockGetReportDrilldown.mockResolvedValue(fakeResult)

    const options = createOptions()
    const { onRvCtxDrillDown } = useReportCellActions(options)

    // Set context menu row data (simulates right-click)
    options.rvCtx.contextMenu.rowData = options.rows.value[1]

    onRvCtxDrillDown()

    expect(options.rvCtx.closeContextMenu).toHaveBeenCalled()
    // Should have called getReportDrilldown for the row
    expect(mockGetReportDrilldown).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', 'BS-002')
  })

  it('does nothing when contextMenu.rowData is null', () => {
    const options = createOptions()
    const { onRvCtxDrillDown } = useReportCellActions(options)

    options.rvCtx.contextMenu.rowData = null

    onRvCtxDrillDown()

    expect(options.rvCtx.closeContextMenu).toHaveBeenCalled()
    expect(mockGetReportDrilldown).not.toHaveBeenCalled()
  })
})
