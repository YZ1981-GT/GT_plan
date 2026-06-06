/**
 * useReportData.spec.ts — composable 单元测试
 *
 * 验证 useReportData 核心动作：
 * - fetchReport: 调用 getReport + 正确参数 + 设置 rows
 * - onGenerate: 调用 generateReports + ElMessage.success + 再调 fetchReport
 * - loadTemplateRows: 调用 report config API + 将响应映射为 ReportRow 格式
 *
 * Validates: Requirements 3.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockPush,
    currentRoute: ref({ params: { projectId: 'proj-1' } }),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

vi.mock('@/services/auditPlatformApi', () => ({
  generateReports: vi.fn(),
  getReport: vi.fn(),
  getReportConsistencyCheck: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn() },
}))

vi.mock('@/composables/useWorkflowGuide', () => ({
  showGuide: vi.fn().mockResolvedValue(true),
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

import { ElMessage } from 'element-plus'
import { generateReports, getReport, getReportConsistencyCheck } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'

import { useReportData } from '../useReportData'

// Cast mocked functions for easy access
const mockGetReport = vi.mocked(getReport)
const mockGenerateReports = vi.mocked(generateReports)
const mockGetReportConsistencyCheck = vi.mocked(getReportConsistencyCheck)
const mockApiGet = vi.mocked(api.get)

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createOptions() {
  return {
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2025),
    activeTab: ref('balance_sheet'),
    reportMode: ref<'audited' | 'unadjusted' | 'compare'>('audited'),
    currentApplicableStandard: computed(() => 'soe'),
  }
}

function makeFakeRows(n = 3): ReportRow[] {
  return Array.from({ length: n }, (_, i) => ({
    row_code: `BS-${String(i + 1).padStart(3, '0')}`,
    row_name: `Row ${i + 1}`,
    current_period_amount: String((i + 1) * 1000),
    prior_period_amount: String((i + 1) * 800),
    formula_used: 'SUM()',
    source_accounts: ['1001'],
    indent_level: 1,
    is_total_row: false,
  }))
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useReportData — fetchReport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReportConsistencyCheck.mockResolvedValue({ consistent: true })
  })

  it('calls getReport with correct params and sets rows', async () => {
    const fakeRows = makeFakeRows()
    mockGetReport.mockResolvedValue(fakeRows)

    const options = createOptions()
    const { fetchReport, rows } = useReportData(options)

    await fetchReport()

    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', false, 'soe')
    expect(rows.value).toEqual(fakeRows)
  })

  it('in compare mode, calls getReport twice (audited + unadjusted) and sets compareRows', async () => {
    const auditedRows = makeFakeRows(2)
    const unadjustedRows = [
      { ...auditedRows[0], current_period_amount: '500' },
      { ...auditedRows[1], current_period_amount: '1500' },
    ]
    mockGetReport
      .mockResolvedValueOnce(auditedRows)
      .mockResolvedValueOnce(unadjustedRows)

    const options = createOptions()
    options.reportMode.value = 'compare'
    const { fetchReport, rows, compareRows } = useReportData(options)

    await fetchReport()

    expect(mockGetReport).toHaveBeenCalledTimes(2)
    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', false, 'soe')
    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', true, 'soe')
    expect(rows.value).toEqual(auditedRows)
    expect(compareRows.value.length).toBe(2)
    // Each compare row should have adjustment field
    expect(compareRows.value[0]).toHaveProperty('adjustment')
  })

  it('on 404 error, calls loadTemplateRows (falls back to template)', async () => {
    const err = { response: { status: 404 } }
    mockGetReport.mockRejectedValue(err)
    // Mock api.get for reportConfig list
    mockApiGet.mockResolvedValue([
      { row_code: 'BS-001', row_name: '货币资金', indent_level: 1, is_total: false, formula: null },
    ])

    const options = createOptions()
    const { fetchReport, rows } = useReportData(options)

    await fetchReport()

    // Should have loaded template rows
    expect(rows.value.length).toBe(1)
    expect(rows.value[0].row_code).toBe('BS-001')
    expect(rows.value[0].current_period_amount).toBeNull()
  })
})

describe('useReportData — onGenerate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetReportConsistencyCheck.mockResolvedValue({ consistent: true })
  })

  it('calls generateReports, shows ElMessage.success, then calls fetchReport', async () => {
    const fakeRows = makeFakeRows()
    mockGenerateReports.mockResolvedValue({ summary: { total_rows: 30, non_zero_rows: 20 } })
    mockGetReport.mockResolvedValue(fakeRows)
    // runBalanceCheck mock
    mockApiGet.mockResolvedValue(null)

    const options = createOptions()
    const { onGenerate, rows } = useReportData(options)

    await onGenerate()

    expect(mockGenerateReports).toHaveBeenCalledWith('proj-1', 2025)
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith(
      expect.stringContaining('30'),
    )
    // fetchReport should have been called after generate
    expect(mockGetReport).toHaveBeenCalledWith('proj-1', 2025, 'balance_sheet', false, 'soe')
    expect(rows.value).toEqual(fakeRows)
  })

  it('shows generic success message when summary has no rows', async () => {
    mockGenerateReports.mockResolvedValue({})
    mockGetReport.mockResolvedValue([])
    mockApiGet.mockResolvedValue(null)

    const options = createOptions()
    const { onGenerate } = useReportData(options)

    await onGenerate()

    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith('报表生成完成')
  })
})

describe('useReportData — loadTemplateRows', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls report config API with correct params and maps response to ReportRow format', async () => {
    const configRows = [
      { row_code: 'BS-001', row_name: '货币资金', indent_level: 1, is_total: false, formula: 'SUM()' },
      { row_code: 'BS-002', row_name: '应收账款', indent_level: 1, is_total: true, formula: null },
    ]
    mockApiGet.mockResolvedValue(configRows)

    const options = createOptions()
    const { loadTemplateRows, rows } = useReportData(options)

    await loadTemplateRows()

    // Verify api.get was called with P_rc.list path and correct params
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/report-config',
      expect.objectContaining({
        params: { report_type: 'balance_sheet', project_id: 'proj-1', applicable_standard: 'soe' },
      }),
    )

    // Verify rows were mapped correctly
    expect(rows.value).toHaveLength(2)
    expect(rows.value[0]).toEqual({
      row_code: 'BS-001',
      row_name: '货币资金',
      current_period_amount: null,
      prior_period_amount: null,
      indent_level: 1,
      is_total_row: false,
      formula_used: 'SUM()',
      source_accounts: null,
    })
    expect(rows.value[1].is_total_row).toBe(true)
    expect(rows.value[1].formula_used).toBeNull()
  })

  it('sets empty rows when API returns empty array', async () => {
    mockApiGet.mockResolvedValue([])

    const options = createOptions()
    const { loadTemplateRows, rows } = useReportData(options)

    await loadTemplateRows()

    expect(rows.value).toEqual([])
  })

  it('sets empty rows on API error', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    const options = createOptions()
    const { loadTemplateRows, rows } = useReportData(options)

    await loadTemplateRows()

    expect(rows.value).toEqual([])
  })
})

describe('useReportData — derived state', () => {
  it('activeTabLabel returns correct Chinese label', () => {
    const options = createOptions()
    options.activeTab.value = 'income_statement'
    const { activeTabLabel } = useReportData(options)
    expect(activeTabLabel.value).toBe('利润表')
  })

  it('coverageSummary computes correct stats', () => {
    const options = createOptions()
    const { coverageSummary, rows } = useReportData(options)

    rows.value = [
      { row_code: 'BS-001', row_name: '流动资产：', current_period_amount: '0', prior_period_amount: null, formula_used: null, source_accounts: null, indent_level: 0, is_total_row: false },
      { row_code: 'BS-002', row_name: '货币资金', current_period_amount: '1000', prior_period_amount: null, formula_used: 'SUM()', source_accounts: null, indent_level: 1, is_total_row: false },
      { row_code: 'BS-003', row_name: '应收账款', current_period_amount: '0', prior_period_amount: null, formula_used: 'SUM()', source_accounts: null, indent_level: 1, is_total_row: false },
    ]

    expect(coverageSummary.value).not.toBeNull()
    expect(coverageSummary.value!.total).toBe(3)
    // First row is header (contains ：), second has data (1000), third is zero
    expect(coverageSummary.value!.withData).toBe(1)
  })
})
