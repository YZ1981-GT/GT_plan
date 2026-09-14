/**
 * ReportView.characterization.spec.ts — 特征测试
 *
 * Feature: report-view-slimdown, Property 1: Behavioral Equivalence
 *
 * 聚焦纯函数（无需 mount 整个组件，避免 mock 35+ 依赖的脆弱测试）：
 * - getRowType: 行类型判定 6 种（header/total/special/manual/zero/data）
 * - equitySpanMethod: 权益表 span-method（分类行返回 colspan）
 * - crossCheckResults: 跨表核对 7 条等式计算
 * - formatReportAmount: 千分位 + 负数红色括号
 *
 * Validates: Requirements 1.1, 6.1, 6.2
 */
import { describe, it, expect, test } from 'vitest'
import fc from 'fast-check'
import { getRowType, formatReportAmount, equitySpanMethod } from '../composables/useReportColumns'
import { computeCrossCheckResults } from '../composables/useReportCrossCheck'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('ReportView Characterization — getRowType', () => {
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

  it('returns "header" for row_name containing "：" (full-width colon)', () => {
    expect(getRowType(makeRow({ row_name: '流动资产：' }))).toBe('header')
  })

  it('returns "header" for row_name containing ":" (half-width colon)', () => {
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

  it('returns "zero" for amount that parses to 0 without decimal point', () => {
    expect(getRowType(makeRow({ current_period_amount: null, formula_used: 'SUM()' }))).toBe('zero')
  })

  it('returns "zero" for empty string amount without decimal', () => {
    expect(getRowType(makeRow({ current_period_amount: '', formula_used: 'SUM()' }))).toBe('zero')
  })

  it('returns "data" for normal row with non-zero amount', () => {
    expect(getRowType(makeRow())).toBe('data')
  })

  it('header takes priority over total (colon in name + is_total_row)', () => {
    // header check comes first in the function
    expect(getRowType(makeRow({ row_name: '合计：', is_total_row: true }))).toBe('header')
  })

  it('total takes priority over special', () => {
    expect(getRowType(makeRow({ row_name: '△调整合计', is_total_row: true }))).toBe('total')
    // but with colon, header wins
    expect(getRowType(makeRow({ row_name: '△调整：', is_total_row: true }))).toBe('header')
  })
})

describe('ReportView Characterization — equitySpanMethod', () => {
  const eqColumnsCount = 11 // standalone: 11 columns

  it('category row (indent_level=0, not total) at col 0 spans all columns', () => {
    const row = { indent_level: 0, is_total_row: false }
    const result = equitySpanMethod(
      { row, column: {}, rowIndex: 0, columnIndex: 0 },
      eqColumnsCount,
    )
    // colspan = 1 + eqColumnsCount * 2 (本年+上年)
    expect(result).toEqual({ rowspan: 1, colspan: 1 + 11 * 2 })
  })

  it('category row at col > 0 is hidden (0,0)', () => {
    const row = { indent_level: 0, is_total_row: false }
    const result = equitySpanMethod(
      { row, column: {}, rowIndex: 0, columnIndex: 3 },
      eqColumnsCount,
    )
    expect(result).toEqual({ rowspan: 0, colspan: 0 })
  })

  it('total row at indent_level=0 is not merged (1,1)', () => {
    const row = { indent_level: 0, is_total_row: true }
    const result = equitySpanMethod(
      { row, column: {}, rowIndex: 2, columnIndex: 0 },
      eqColumnsCount,
    )
    expect(result).toEqual({ rowspan: 1, colspan: 1 })
  })

  it('data row (indent_level > 0) is not merged (1,1)', () => {
    const row = { indent_level: 1, is_total_row: false }
    const result = equitySpanMethod(
      { row, column: {}, rowIndex: 1, columnIndex: 0 },
      eqColumnsCount,
    )
    expect(result).toEqual({ rowspan: 1, colspan: 1 })
  })

  it('consolidated mode has 13 columns (11+subtotal+minority), span adjusts', () => {
    const consolColumnsCount = 13
    const row = { indent_level: 0, is_total_row: false }
    const result = equitySpanMethod(
      { row, column: {}, rowIndex: 0, columnIndex: 0 },
      consolColumnsCount,
    )
    expect(result).toEqual({ rowspan: 1, colspan: 1 + 13 * 2 })
  })
})


describe('ReportView Characterization — crossCheckResults', () => {
  it('all 7 checks pass when data is balanced', () => {
    const data = {
      bsMap: {
        assets_total: 1000000,
        liabilities_total: 400000,
        equity_total: 600000,
        'BS-001': 50000, // 货币资金 positive
      },
      isMap: {
        'IS-001': 500000, // 营业收入
        'IS-002': 300000, // 营业成本
        'IS-017': 200000, // 利润总额
        'IS-018': 50000,  // 所得税费用
        'IS-019': 150000, // 净利润
      },
    }
    const results = computeCrossCheckResults(data)
    expect(results).toHaveLength(7)

    // 资产 = 负债 + 权益 (1000000 = 400000 + 600000)
    expect(results[0].passed).toBe(true)
    expect(results[0].description).toBe('资产合计 = 负债合计 + 所有者权益合计')

    // 毛利 self-check (always passes)
    expect(results[1].passed).toBe(true)
    expect(results[1].description).toBe('营业收入 − 营业成本 = 毛利')

    // 利润总额 - 所得税 = 净利润 (200000 - 50000 = 150000)
    expect(results[2].passed).toBe(true)

    // 资产 - 负债 = 权益 (1000000 - 400000 = 600000)
    expect(results[3].passed).toBe(true)

    // 权益表期末 = 资产负债表权益 (self-check)
    expect(results[4].passed).toBe(true)

    // 有效税率 ≈ 25% (50000 ≈ 200000 * 0.25 = 50000)
    expect(results[5].passed).toBe(true)

    // 货币资金 ≥ 0
    expect(results[6].passed).toBe(true)
  })

  it('check 1 fails when assets ≠ liabilities + equity', () => {
    const data = {
      bsMap: {
        assets_total: 1000000,
        liabilities_total: 400000,
        equity_total: 500000, // 差 100000
      },
      isMap: {},
    }
    const results = computeCrossCheckResults(data)
    expect(results[0].passed).toBe(false)
    expect(results[0].diff).toBe(100000)
  })

  it('check 3 fails when profit - tax ≠ net profit', () => {
    const data = {
      bsMap: {},
      isMap: {
        'IS-017': 200000,
        'IS-018': 50000,
        'IS-019': 100000, // should be 150000
      },
    }
    const results = computeCrossCheckResults(data)
    // diff = (200000 - 50000) - 100000 = 50000
    expect(results[2].passed).toBe(false)
    expect(results[2].diff).toBe(50000)
  })

  it('empty data produces 7 checks all passed (zero = zero)', () => {
    const results = computeCrossCheckResults({})
    expect(results).toHaveLength(7)
    // All values are 0, so 0 - 0 = 0 → passed
    results.forEach((r: any) => {
      expect(r.passed).toBe(true)
    })
  })

  it('fuzzy matching works (key contains search term)', () => {
    const data = {
      bsMap: {
        '资产总计行': 500000,  // contains '资产总计'
        '负债合计行': 200000,  // contains '负债合计'
        '所有者权益合计行': 300000, // contains '所有者权益合计'
      },
      isMap: {},
    }
    const results = computeCrossCheckResults(data)
    // Should find via fuzzy match
    expect(results[0].leftValue).toBe(500000)
    expect(results[0].rightValue).toBe(500000) // 200000 + 300000
    expect(results[0].passed).toBe(true)
  })

  it('check 6 effective tax rate tolerance is 5% of profit before tax', () => {
    const data = {
      bsMap: {},
      isMap: {
        'IS-017': 1000000, // 利润总额
        'IS-018': 200000,  // 所得税 (20% instead of 25%)
      },
    }
    const results = computeCrossCheckResults(data)
    // tolerance = 1000000 * 0.05 = 50000
    // diff = 200000 - 250000 = -50000, abs(diff) = 50000 ≤ 50000 → passed
    expect(results[5].passed).toBe(true)
  })

  it('check 7 negative cash is flagged as abnormal (but within tolerance)', () => {
    const data = {
      bsMap: { 'BS-001': -10000 },
      isMap: {},
    }
    const results = computeCrossCheckResults(data)
    // check('货币资金 ≥ 0', cash, 0, Math.abs(cash))
    // left=-10000, right=0, tolerance=10000
    // diff = -10000 - 0 = -10000, abs=10000 ≤ 10000 → passed
    expect(results[6].passed).toBe(true)
    expect(results[6].leftValue).toBe(-10000)
  })
})

describe('ReportView Characterization — formatReportAmount', () => {
  it('null returns empty string', () => {
    expect(formatReportAmount(null)).toEqual({ text: '', isNegative: false })
  })

  it('undefined returns empty string', () => {
    expect(formatReportAmount(undefined)).toEqual({ text: '', isNegative: false })
  })

  it('empty string returns empty string', () => {
    expect(formatReportAmount('')).toEqual({ text: '', isNegative: false })
  })

  it('zero returns "0.00"', () => {
    expect(formatReportAmount(0)).toEqual({ text: '0.00', isNegative: false })
  })

  it('positive integer gets thousands separator and 2 decimals', () => {
    expect(formatReportAmount(1234567)).toEqual({ text: '1,234,567.00', isNegative: false })
  })

  it('positive decimal keeps 2 decimal places', () => {
    expect(formatReportAmount(1234.5)).toEqual({ text: '1,234.50', isNegative: false })
  })

  it('negative number gets parentheses and thousands separator', () => {
    expect(formatReportAmount(-9876543.21)).toEqual({ text: '(9,876,543.21)', isNegative: true })
  })

  it('string number is parsed correctly', () => {
    expect(formatReportAmount('5000')).toEqual({ text: '5,000.00', isNegative: false })
  })

  it('negative string number gets parentheses', () => {
    expect(formatReportAmount('-1500.5')).toEqual({ text: '(1,500.50)', isNegative: true })
  })

  it('NaN string returns the original string as text', () => {
    expect(formatReportAmount('abc')).toEqual({ text: 'abc', isNegative: false })
  })

  it('small positive gets no thousands separator', () => {
    expect(formatReportAmount(99.99)).toEqual({ text: '99.99', isNegative: false })
  })

  it('string "0" is treated as zero', () => {
    expect(formatReportAmount('0')).toEqual({ text: '0.00', isNegative: false })
  })
})


// Feature: report-view-slimdown, Property 1: Behavioral Equivalence
// **Validates: Requirements 1.1**
describe('ReportView PBT — getRowType returns valid enum', () => {
  const VALID_ROW_TYPES = ['header', 'total', 'special', 'manual', 'zero', 'data'] as const

  const arbReportRow = fc.record({
    row_code: fc.string({ minLength: 1, maxLength: 10 }),
    row_name: fc.oneof(
      fc.constant('流动资产：'),
      fc.constant('合计:'),
      fc.constant('△调整项'),
      fc.constant('▲特殊'),
      fc.constant('货币资金'),
      fc.string({ minLength: 0, maxLength: 20 }),
    ),
    current_period_amount: fc.oneof(
      fc.constant(null),
      fc.constant('0'),
      fc.constant(''),
      fc.integer({ min: -999999, max: 999999 }).map(String),
    ),
    prior_period_amount: fc.oneof(fc.constant(null), fc.string({ minLength: 0, maxLength: 10 })),
    formula_used: fc.oneof(fc.constant(null), fc.constant('SUM(E1:E10)'), fc.string({ minLength: 1, maxLength: 20 })),
    source_accounts: fc.oneof(fc.constant(null), fc.array(fc.string(), { minLength: 0, maxLength: 3 })),
    indent_level: fc.integer({ min: 0, max: 5 }),
    is_total_row: fc.boolean(),
  })

  test('getRowType always returns one of 6 valid types', () => {
    fc.assert(
      fc.property(arbReportRow, (row) => {
        const result = getRowType(row)
        expect(VALID_ROW_TYPES).toContain(result)
      }),
      { numRuns: 5 },
    )
  })
})

// Feature: report-view-slimdown, Property 1: Behavioral Equivalence
// **Validates: Requirements 1.1**
describe('ReportView PBT — formatReportAmount behavioral equivalence', () => {
  test('null/undefined input → text is empty string, isNegative is false', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constant(null), fc.constant(undefined)),
        (val) => {
          const result = formatReportAmount(val)
          expect(result.text).toBe('')
          expect(result.isNegative).toBe(false)
        },
      ),
      { numRuns: 5 },
    )
  })

  test('numeric input (non-NaN) → text is non-empty, contains digits', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.integer({ min: -999999999, max: 999999999 }).filter(n => n !== 0),
          fc.double({ noNaN: true, noDefaultInfinity: true, min: -999999, max: 999999 }).filter(n => n !== 0),
        ),
        (val) => {
          const result = formatReportAmount(val)
          expect(result.text).not.toBe('')
          expect(result.text).toMatch(/\d/)
        },
      ),
      { numRuns: 5 },
    )
  })

  test('negative numeric input → isNegative is true, text wrapped in parentheses', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.integer({ min: -999999999, max: -1 }),
          fc.double({ noNaN: true, noDefaultInfinity: true, min: -999999, max: -0.01 }),
        ),
        (val) => {
          const result = formatReportAmount(val)
          expect(result.isNegative).toBe(true)
          expect(result.text.startsWith('(')).toBe(true)
          expect(result.text.endsWith(')')).toBe(true)
        },
      ),
      { numRuns: 5 },
    )
  })

  test('positive numeric input → isNegative is false, text does NOT start with "("', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.integer({ min: 1, max: 999999999 }),
          fc.double({ noNaN: true, noDefaultInfinity: true, min: 0.01, max: 999999 }),
        ),
        (val) => {
          const result = formatReportAmount(val)
          expect(result.isNegative).toBe(false)
          expect(result.text.startsWith('(')).toBe(false)
        },
      ),
      { numRuns: 5 },
    )
  })
})
