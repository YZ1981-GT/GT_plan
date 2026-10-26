/**
 * Property-Based Tests — D1 应收票据公式引擎
 *
 * Property 1: 审定数公式链
 * Property 2: 变动率零期初处理
 * Property 3: ECL 预期损失率连乘
 * Property 4: 应计提/差异
 * Property 5: 净值与小计
 * Property 6: parseNum 安全解析
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  parseNum,
  calcAuditedAmount,
  calcChangeRate,
  calcExpectedLossRate,
  calcProvision,
  calcDifference,
  calcSubtotal,
  calcNetValue,
  calcBadDebtEndBalance,
  safeDivide,
} from '../useD1FormulaEngine'

const valArb = fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })

describe('Feature: d1-notes-receivable, Property 1: 审定数公式链', () => {
  it('calcAuditedAmount equals unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(valArb, valArb, valArb, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 100 },
    )
  })

  // 模板 D1-1 K 列 IF(AND(E=0,I=0),"",IF(AND(E=0,I>0),1,J/E))：期末为负时除零（#DIV/0!）记 N/A
  it('calcChangeRate handles zero prior consistently', () => {
    fc.assert(
      fc.property(valArb, (audited) => {
        if (audited === 0) {
          expect(calcChangeRate(0, 0)).toBe('')
        } else if (audited > 0) {
          expect(calcChangeRate(0, audited)).toBe(1)
        } else {
          expect(calcChangeRate(0, audited)).toBe('N/A')
        }
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d1-notes-receivable, Property 2: ECL 公式', () => {
  it('calcExpectedLossRate equals product of rates', () => {
    fc.assert(
      fc.property(fc.array(fc.double({ min: 0, max: 1, noNaN: true }), { maxLength: 8 }), (rates) => {
        const expected = rates.length === 0 ? 0 : rates.reduce((a, r) => a * r, 1)
        expect(calcExpectedLossRate(rates)).toBeCloseTo(expected, 8)
      }),
      { numRuns: 100 },
    )
  })

  it('calcProvision = balance × lossRate', () => {
    fc.assert(
      fc.property(valArb, valArb, (balance, rate) => {
        expect(calcProvision(balance, rate)).toBeCloseTo(balance * rate, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('calcDifference = should - actual（模板 ⑤=③-④，spec oo-writeback-template-parity-closure R2）', () => {
    fc.assert(
      fc.property(valArb, valArb, (actual, should) => {
        expect(calcDifference(actual, should)).toBeCloseTo(should - actual, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d1-notes-receivable, Property 3: 小计与净值', () => {
  it('calcSubtotal equals sum', () => {
    fc.assert(
      fc.property(fc.array(valArb, { maxLength: 20 }), (rows) => {
        expect(calcSubtotal(rows)).toBeCloseTo(rows.reduce((s, v) => s + v, 0), 5)
      }),
      { numRuns: 100 },
    )
  })

  it('calcNetValue = gross - badDebt', () => {
    fc.assert(
      fc.property(valArb, valArb, (gross, bd) => {
        expect(calcNetValue(gross, bd)).toBeCloseTo(gross - bd, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('calcBadDebtEndBalance formula', () => {
    fc.assert(
      fc.property(valArb, valArb, valArb, valArb, valArb, valArb, (prior, prov, rec, rev, wo, other) => {
        const end = prior + prov - rec - rev - wo + other
        expect(calcBadDebtEndBalance(prior, prov, rec, rev, wo, other)).toBeCloseTo(end, 5)
      }),
      { numRuns: 80 },
    )
  })
})

describe('Feature: d1-notes-receivable, Property 4: parseNum / safeDivide', () => {
  it('parseNum maps invalid to 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum('abc')).toBe(0)
  })

  it('safeDivide returns 0 when divisor is 0', () => {
    fc.assert(
      fc.property(valArb, (num) => {
        expect(safeDivide(num, 0)).toBe(0)
      }),
      { numRuns: 50 },
    )
  })
})
