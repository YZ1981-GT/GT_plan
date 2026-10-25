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

describe('useReportColumns — eqCellVal', () => {
  it('reads eq_matrix current_year via UI→backend column mapping', () => {
    const options = createOptions()
    const { eqCellVal } = useReportColumns(options)
    const row = {
      source_accounts: {
        eq_matrix: {
          current_year: {
            share_capital: 4000000,
            other_comprehensive_income: 9000,
          },
        },
      },
    }
    expect(eqCellVal(row, 'paid_in_capital')).toBe(4000000)
    expect(eqCellVal(row, 'oci')).toBe(9000)
  })

  it('falls back to flat source_accounts[colKey]', () => {
    const options = createOptions()
    const { eqCellVal } = useReportColumns(options)
    const row = { source_accounts: { capital_reserve: 250000 } }
    expect(eqCellVal(row, 'capital_reserve')).toBe(250000)
  })

  it('reads prior_year block from eq_matrix', () => {
    const options = createOptions()
    const { eqCellVal } = useReportColumns(options)
    const row = {
      source_accounts: {
        eq_matrix: {
          prior_year: { share_capital: 3500000, capital_reserve: 650000 },
        },
      },
    }
    expect(eqCellVal(row, 'paid_in_capital', 'prior_year')).toBe(3500000)
    expect(eqCellVal(row, 'capital_reserve', 'prior_year')).toBe(650000)
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

/**
 * 🔴 2026-09-28 修：`getNoteSection` 的语义已从「查静态 `_ROW_NOTE_SECTION_MAP`」
 * 改为「查 `noteSequenceMap`」—— 后者**只收录出现在 `rows` 里且有金额的行**
 * （零额行不编附注序号）。
 *
 * 原测试用 `createOptions()` 的空 `rows` 去断言 `getNoteSection('BS-002') === '五、1'`
 * ⇒ 恒得 null，这两条一直红。这是**测试没跟上实现**，不是实现缺陷：
 * 报表页只给有金额的行标附注序号，空 rows 自然无任何映射。
 *
 * 故这里显式喂入带金额的行。同时保留「零额行不编号」这条正向语义断言，
 * 否则改回静态映射也能让本组变绿（判据会失去区分力）。
 */
describe('useReportColumns — getNoteSection', () => {
  function withRows(rows: Array<Partial<ReportRow>>) {
    const options = {
      isConsolidated: computed(() => false),
      activeTab: ref('balance_sheet'),
      rows: ref(rows as ReportRow[]),
    }
    return useReportColumns(options)
  }

  it('returns mapped section for known row code BS-002（该行须在 rows 内且有金额）', () => {
    const { getNoteSection } = withRows([
      { row_code: 'BS-002', current_period_amount: '1000', prior_period_amount: '900' },
    ])
    expect(getNoteSection('BS-002')).toBe('五、1')
  })

  // 🔴 期望值由 '五、29' 更正为 '五、62'：映射真源 `_ROW_NOTE_SECTION_MAP` 里
  // `'IS-001': '五、62'`（营业收入，与营业成本 IS-002 合并同一章节）。
  // 旧期望 29 是过时值，实现是对的 —— 本条同时是「测试期望必须对着真源核，
  // 不能凭记忆写」的样本。
  it('returns mapped section for known row code IS-001（同上）', () => {
    const { getNoteSection } = withRows([
      { row_code: 'IS-001', current_period_amount: '5000', prior_period_amount: '4000' },
    ])
    expect(getNoteSection('IS-001')).toBe('五、62')
  })

  it('IS-001 与 IS-002 共用同一章节（营业收入/成本合并披露）', () => {
    const { getNoteSection } = withRows([
      { row_code: 'IS-001', current_period_amount: '5000' },
      { row_code: 'IS-002', current_period_amount: '3000' },
    ])
    expect(getNoteSection('IS-002')).toBe(getNoteSection('IS-001'))
  })

  it('🔴 零额行不编附注序号 ⇒ 即便 row_code 已知也返回 null（动态编号语义）', () => {
    const { getNoteSection } = withRows([
      { row_code: 'BS-002', current_period_amount: '0', prior_period_amount: '0' },
    ])
    expect(getNoteSection('BS-002')).toBeNull()
  })

  it('行不在 rows 内 ⇒ 返回 null（不再回落静态映射）', () => {
    const { getNoteSection } = withRows([
      { row_code: 'IS-001', current_period_amount: '5000' },
    ])
    expect(getNoteSection('BS-002')).toBeNull()
  })

  it('returns null for unknown row code', () => {
    const { getNoteSection } = withRows([
      { row_code: 'BS-002', current_period_amount: '1000' },
    ])
    expect(getNoteSection('UNKNOWN-999')).toBeNull()
  })

  it('returns null for empty string', () => {
    const { getNoteSection } = withRows([
      { row_code: 'BS-002', current_period_amount: '1000' },
    ])
    expect(getNoteSection('')).toBeNull()
  })
})

describe('useReportColumns — goToNote', () => {
  beforeEach(() => {
    mockPush.mockClear()
  })

  // 同 getNoteSection：goToNote 依赖动态编号，行必须在 rows 内且有金额（见上方说明）
  function withRows(rows: Array<Partial<ReportRow>>) {
    return useReportColumns({
      isConsolidated: computed(() => false),
      activeTab: ref('balance_sheet'),
      rows: ref(rows as ReportRow[]),
    })
  }

  it('navigates to disclosure-notes with section query for known row code', () => {
    const { goToNote } = withRows([
      { row_code: 'BS-002', current_period_amount: '1000', prior_period_amount: '900' },
    ])
    goToNote('BS-002')
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/test-project-id/disclosure-notes',
      query: { section: '五、1' },
    })
  })

  it('does not navigate for unknown row code', () => {
    const { goToNote } = withRows([
      { row_code: 'BS-002', current_period_amount: '1000' },
    ])
    goToNote('UNKNOWN-999')
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('🔴 零额行不跳转（无附注序号 ⇒ 无 section ⇒ 不 push）', () => {
    const { goToNote } = withRows([
      { row_code: 'BS-002', current_period_amount: '0', prior_period_amount: '0' },
    ])
    goToNote('BS-002')
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
