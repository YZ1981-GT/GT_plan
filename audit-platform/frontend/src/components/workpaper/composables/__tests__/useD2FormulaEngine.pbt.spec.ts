/**
 * Property-Based Tests — D2 应收账款公式引擎
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 *
 * Property 1: 审定数公式链
 * Property 2: SUMIF legacy 聚合
 * Property 3: ECL 迁徙率连乘
 * Property 4: 质押比例
 * Property 5: 截止跨期判定
 * Property 6: 周转率/周转天数
 * Property 7: parseNum 安全解析
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  parseNum,
  getAuditedAmount,
  getChangeRate,
  calculateProvision,
  calculateDifference,
  calculateExpectedLossRate,
  calculatePledgeRatio,
  determineCutoff,
  calculateTurnoverRate,
  calculateTurnoverDays,
  sumifLegacy,
  fmtAuditAmount,
} from '../useD2FormulaEngine'

const valArb = fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })

describe('Feature: d2-accounts-receivable, Property 1: 审定数公式链', () => {
  it('getAuditedAmount equals unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(valArb, valArb, valArb, (u, a, r) => {
        expect(getAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('getChangeRate handles zero prior consistently', () => {
    fc.assert(
      fc.property(valArb, (audited) => {
        if (audited === 0) {
          expect(getChangeRate(0, 0)).toBe('')
        } else {
          expect(getChangeRate(0, audited)).toBe(1)
        }
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d2-accounts-receivable, Property 2: SUMIF legacy 聚合', () => {
  it('sumifLegacy equals filtered reduce for AI/S/Z/AA rows', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            AI: fc.constantFrom('单项计提', '账龄组合', '客户类型组合'),
            S: valArb,
            Z: valArb,
            AA: valArb,
          }),
          { maxLength: 20 },
        ),
        fc.constantFrom('单项计提', '账龄组合', '客户类型组合'),
        fc.constantFrom('S', 'Z', 'AA') as fc.Arbitrary<'S' | 'Z' | 'AA'>,
        (rows, classification, column) => {
          const result = sumifLegacy(rows, classification, column)
          const expected = rows
            .filter(r => r.AI === classification)
            .reduce((sum, r) => sum + (parseNum(r[column]) || 0), 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d2-accounts-receivable, Property 3: ECL 迁徙率连乘', () => {
  it('calculateExpectedLossRate equals rates product', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 0, max: 1, noNaN: true }), { minLength: 1, maxLength: 5 }),
        (rates) => {
          const result = calculateExpectedLossRate(rates)
          const expected = rates.reduce((a, b) => a * b, 1)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('empty rates returns 0', () => {
    expect(calculateExpectedLossRate([])).toBe(0)
  })
})

describe('Feature: d2-accounts-receivable, Property 4: 质押比例', () => {
  it('pledge ratio equals pledged/total when total > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        (pledged, total) => {
          expect(calculatePledgeRatio(pledged, total)).toBeCloseTo(pledged / total, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when total is 0', () => {
    expect(calculatePledgeRatio(100, 0)).toBe(0)
  })
})

describe('Feature: d2-accounts-receivable, Property 5: 截止跨期判定', () => {
  it('returns true when revenue date is after balance sheet date', () => {
    expect(determineCutoff('2025-02-01', '2024-12-31')).toBe(true)
    expect(determineCutoff('2024-11-01', '2024-12-31')).toBe(false)
  })
})

describe('Feature: d2-accounts-receivable, Property 6: 周转率/周转天数', () => {
  it('turnover days equals 365/rate when rate > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 100, noNaN: true }),
        (rate) => {
          expect(calculateTurnoverDays(rate)).toBeCloseTo(365 / rate, 4)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calculateProvision equals balance * rate', () => {
    fc.assert(
      fc.property(valArb, fc.double({ min: 0, max: 1, noNaN: true }), (balance, rate) => {
        expect(calculateProvision(balance, rate)).toBeCloseTo(balance * rate, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('calculateDifference equals actual - should', () => {
    fc.assert(
      fc.property(valArb, valArb, (actual, should) => {
        expect(calculateDifference(actual, should)).toBeCloseTo(actual - should, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d2-accounts-receivable, Property 7: parseNum 与金额格式化', () => {
  it('parseNum always returns finite number', () => {
    fc.assert(
      fc.property(fc.double({ min: -1e12, max: 1e12 }), (val) => {
        const result = parseNum(val)
        expect(Number.isFinite(result)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('fmtAuditAmount returns dash for zero', () => {
    expect(fmtAuditAmount(0)).toBe('-')
  })
})
