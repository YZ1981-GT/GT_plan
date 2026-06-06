/**
 * useReportColumns.spec.ts — composable 单元测试
 *
 * 验证 useReportColumns 返回的纯函数和计算属性行为正确：
 * - eqColumns: standalone 12 列 / consolidated 14 列
 * - equitySpanMethod: 分类行合并、数据行不合并
 * - getRowType: 6 种行类型
 * - formatReportAmount: null/0/positive/negative/string
 * - eqRowClassName: total/category/data
 * - impRowClassName: total/non-total
 * - getNoteSection: known code → section, unknown → null
 *
 * Validates: Requirements 3.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import type { ReportRow } from '@/services/auditPlatformApi'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockPush,
    currentRoute: ref({ params: { projectId: 'test-project-id' } }),
  }),
}))

import { useReportColumns } from '../useReportColumns'

function createOptions(overrides: { isConsolidated?: boolean } = {}) {
  const isConsolidated = computed(() => overrides.isConsolidated ?? false)
  const activeTab = ref('BS')
  const rows = ref<ReportRow[]>([])
  return { isConsolidated, activeTab, rows }
}

describe('useReportColumns — eqColumns', () => {
  it('standalone mode has 12 columns (11 base + total)', () => {
    const options = createOptions({ isConsolidated: false })
    const { eqColumns } = useReportColumns(options)
    expect(eqColumns.value).toHaveLength(12)
    expect(eqColumns.value[0].key).toBe('paid_in_capital')
    expect(eqColumns.value[eqColumns.value.length - 1].key).toBe('total')
  })

  it('consolidated mode has 14 columns (11 base + subtotal + minority + total)', () => {
    const options = createOptions({ isConsolidated: true })
    const { eqColumns } = useReportColumns(options)
    expect(eqColumns.value).toHaveLength(14)
    // Verify the extra columns are inserted before 'total'
    const keys = eqColumns.value.map(c => c.key)
    expect(keys).toContain('subtotal')
    expect(keys).toContain('minority')
    expect(keys[keys.length - 1]).toBe('total')
  })

  it('eqTotalCols matches eqColumns length', () => {
    const options = createOptions({ isConsolidated: false })
    const { eqColumns, eqTotalCols } = useReportColumns(options)
    expect(eqTotalCols.value).toBe(eqColumns.value.length)
  })
})

describe('useReportColumns — equitySpanMethod', () => {
  it('category row (indent_level=0, not total) at col 0 spans all equity columns', () => {
    const options = createOptions({ isConsolidated: false })
    const { equitySpanMethod, eqColumns } = useReportColumns(options)
    const row = { indent_level: 0, is_total_row: false }
    const result = equitySpanMethod({ row, column: {}, rowIndex: 0, columnIndex: 0 })
    // colspan = 1 (name col) + eqColumns.length * 2 (本年+上年 for each col)
    expect(result).toEqual({ rowspan: 1, colspan: 1 + eqColumns.value.length * 2 })
  })

  it('category row at col > 0 is hidden (0,0)', () => {
    const options = createOptions({ isConsolidated: false })
    const { equitySpanMethod } = useReportColumns(options)
    const row = { indent_level: 0, is_total_row: false }
    const result = equitySpanMethod({ row, column: {}, rowIndex: 0, columnIndex: 5 })
    expect(result).toEqual({ rowspan: 0, colspan: 0 })
  })

  it('total row at indent_level=0 is NOT merged', () => {
    const options = createOptions({ isConsolidated: false })
    const { equitySpanMethod } = useReportColumns(options)
    const row = { indent_level: 0, is_total_row: true }
    const result = equitySpanMethod({ row, column: {}, rowIndex: 2, columnIndex: 0 })
    expect(result).toEqual({ rowspan: 1, colspan: 1 })
  })

  it('data row (indent_level > 0) is NOT merged', () => {
    const options = createOptions({ isConsolidated: false })
    const { equitySpanMethod } = useReportColumns(options)
    const row = { indent_level: 1, is_total_row: false }
    const result = equitySpanMethod({ row, column: {}, rowIndex: 1, columnIndex: 0 })
    expect(result).toEqual({ rowspan: 1, colspan: 1 })
  })
})

describe('useReportColumns — getRowType', () => {
  const options = createOptions()
  const { getRowType } = useReportColumns(options)

  function makeRow(overrides: Partial<ReportRow> = {}): ReportRow {
    return {
      row_code: 'BS-001',
      row_name: '货币资金',
      current_period_amount: '1000',
      prior_period_amount: '800',
      formula_used: 'SUM(E1:E10)',
      source_accounts: ['1001'],
      indent_level: 1,
      is_total_row: false,
      ...overrides,
    }
  }

  it('returns "header" for row_name with full-width colon', () => {
    expect(getRowType(makeRow({ row_name: '流动资产：' }))).toBe('header')
  })

  it('returns "header" for row_name with half-width colon', () => {
    expect(getRowType(makeRow({ row_name: '流动资产:' }))).toBe('header')
  })

  it('returns "total" for is_total_row = true', () => {
    expect(getRowType(makeRow({ is_total_row: true }))).toBe('total')
  })

  it('returns "special" for row_name starting with "△"', () => {
    expect(getRowType(makeRow({ row_name: '△调整项' }))).toBe('special')
  })

  it('returns "special" for row_name starting with "▲"', () => {
    expect(getRowType(makeRow({ row_name: '▲特殊项目' }))).toBe('special')
  })

  it('returns "manual" for no formula and amount = "0"', () => {
    expect(getRowType(makeRow({ formula_used: null, current_period_amount: '0' }))).toBe('manual')
  })

  it('returns "zero" for null amount that parses to 0 without decimal', () => {
    expect(getRowType(makeRow({ current_period_amount: null, formula_used: 'SUM()' }))).toBe('zero')
  })

  it('returns "data" for normal row with non-zero amount', () => {
    expect(getRowType(makeRow())).toBe('data')
  })
})

describe('useReportColumns — formatReportAmount', () => {
  const options = createOptions()
  const { formatReportAmount } = useReportColumns(options)

  it('null returns empty text', () => {
    expect(formatReportAmount(null)).toEqual({ text: '', isNegative: false })
  })

  it('undefined returns empty text', () => {
    expect(formatReportAmount(undefined)).toEqual({ text: '', isNegative: false })
  })

  it('empty string returns empty text', () => {
    expect(formatReportAmount('')).toEqual({ text: '', isNegative: false })
  })

  it('zero returns "0.00"', () => {
    expect(formatReportAmount(0)).toEqual({ text: '0.00', isNegative: false })
  })

  it('positive integer formats with thousands separator', () => {
    expect(formatReportAmount(1234567)).toEqual({ text: '1,234,567.00', isNegative: false })
  })

  it('negative number formats with parentheses', () => {
    expect(formatReportAmount(-9876543.21)).toEqual({ text: '(9,876,543.21)', isNegative: true })
  })

  it('string number is parsed correctly', () => {
    expect(formatReportAmount('5000')).toEqual({ text: '5,000.00', isNegative: false })
  })

  it('NaN string returns original string as text', () => {
    expect(formatReportAmount('abc')).toEqual({ text: 'abc', isNegative: false })
  })
})

describe('useReportColumns — eqRowClassName', () => {
  const options = createOptions()
  const { eqRowClassName } = useReportColumns(options)

  it('returns total class for is_total_row', () => {
    expect(eqRowClassName({ row: { is_total_row: true, indent_level: 1 } })).toBe('gt-rv-eq-total-row')
  })

  it('returns category class for indent_level=0 non-total', () => {
    expect(eqRowClassName({ row: { is_total_row: false, indent_level: 0 } })).toBe('gt-rv-eq-category')
  })

  it('returns empty string for data rows', () => {
    expect(eqRowClassName({ row: { is_total_row: false, indent_level: 1 } })).toBe('')
  })
})

describe('useReportColumns — impRowClassName', () => {
  const options = createOptions()
  const { impRowClassName } = useReportColumns(options)

  it('returns total class for is_total_row', () => {
    expect(impRowClassName({ row: { is_total_row: true } })).toBe('gt-rv-eq-total-row')
  })

  it('returns empty string for non-total rows', () => {
    expect(impRowClassName({ row: { is_total_row: false } })).toBe('')
  })
})

describe('useReportColumns — getNoteSection', () => {
  const options = createOptions()
  const { getNoteSection } = useReportColumns(options)

  it('returns mapped section for known row code BS-002', () => {
    expect(getNoteSection('BS-002')).toBe('五、1')
  })

  it('returns mapped section for known row code IS-001', () => {
    expect(getNoteSection('IS-001')).toBe('五、29')
  })

  it('returns null for unknown row code', () => {
    expect(getNoteSection('UNKNOWN-999')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(getNoteSection('')).toBeNull()
  })
})

describe('useReportColumns — goToNote', () => {
  beforeEach(() => {
    mockPush.mockClear()
  })

  it('navigates to disclosure-notes with section query for known row code', () => {
    const options = createOptions()
    const { goToNote } = useReportColumns(options)
    goToNote('BS-002')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/test-project-id/disclosure-notes',
      query: { section: '五、1' },
    })
  })

  it('does not navigate for unknown row code', () => {
    const options = createOptions()
    const { goToNote } = useReportColumns(options)
    goToNote('UNKNOWN-999')
    expect(mockPush).not.toHaveBeenCalled()
  })
})

// Feature: report-view-slimdown, Property 1: Behavioral Equivalence
// equitySpanMethod PBT — 验证随机输入下返回值合法（rowspan ≥ 0, colspan ≥ 0）
import * as fc from 'fast-check'

describe('useReportColumns — equitySpanMethod PBT', () => {
  /**
   * **Validates: Requirements 1.1, 3.6**
   *
   * Property: For any random {row, column, rowIndex, columnIndex},
   * equitySpanMethod always returns {rowspan >= 0, colspan >= 0}.
   */
  it('always returns non-negative rowspan and colspan', () => {
    const options = createOptions({ isConsolidated: false })
    const { equitySpanMethod } = useReportColumns(options)

    const rowArb = fc.record({
      indent_level: fc.integer({ min: 0, max: 3 }),
      is_total_row: fc.boolean(),
    })

    fc.assert(
      fc.property(
        rowArb,
        fc.integer({ min: 0, max: 30 }),
        (row, columnIndex) => {
          const result = equitySpanMethod({ row, column: {}, rowIndex: 0, columnIndex })
          expect(result.rowspan).toBeGreaterThanOrEqual(0)
          expect(result.colspan).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 5 },
    )
  })
})
