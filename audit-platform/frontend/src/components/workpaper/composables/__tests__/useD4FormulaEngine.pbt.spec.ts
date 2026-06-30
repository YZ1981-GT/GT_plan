/**
 * Property-Based Tests — D4 营业收入公式引擎
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Tasks: 2.2 ~ 2.10
 *
 * Property 1: 损益类审定数公式链正确性
 * Property 2: 合计行恒等于明细行之和
 * Property 4: 变动率阈值高亮判定
 * Property 10: 毛利率公式正确性
 * Property 11: 关联方价格差异率
 * Property 13: IPO/舞弊组可见性控制
 * Property 14: 资金回流可疑判定
 * Property 16: 金额格式化规则
 * Property 20: 占比计算正确性
 *
 * **Validates: Requirements 1.5, 2.3, 2.4, 3.2, 3.3, 3.6, 4.2, 4.3, 4.5, 8.2, 8.3, 8.5, 13.2, 13.3, 14.1, 14.11, 15.1, 25.1-25.4, 26.7**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  parseNum,
  calcMonthlyTotal,
  calcAuditedWithAdj,
  calcChangeRate,
  calcSubtotal,
  calcGrossMarginRate,
  calcProportion,
  calcPriceDiffRate,
  isChangeRateExceeding,
  isSuspiciousFundFlow,
  isIpoGroupVisible,
} from '../useD4FormulaEngine'

// ─── Property 1 PBT: 损益类审定数公式链 ────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 1: 损益类审定数公式链正确性', () => {
  /**
   * **Validates: Requirements 1.5, 2.3, 3.2**
   *
   * For any D4-2 row input (12 months + audit adjustment + prior unadjusted + prior adjustment):
   * - N = SUM(months)
   * - P = N + O (audit adjustment)
   * - S = Q + R (prior unadjusted + prior adjustment)
   * - T = (N - Q) / Q (Q=0 special handling)
   * - U = (P - S) / S (S=0 special handling)
   */
  it('formula chain holds for any valid row inputs', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(
        // 12 months
        valArb, valArb, valArb, valArb,
        valArb, valArb, valArb, valArb,
        valArb, valArb, valArb, valArb,
        // O: audit adjustment, Q: prior unadjusted
        valArb, valArb,
        (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, auditAdj, priorUnadj) => {
          const months = [m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12]

          // N = SUM(months)
          const N = calcMonthlyTotal(months)
          const expectedN = months.reduce((a, b) => a + b, 0)
          expect(N).toBeCloseTo(expectedN, 5)

          // P = N + O
          const P = calcAuditedWithAdj(N, auditAdj)
          expect(P).toBeCloseTo(N + auditAdj, 5)

          // T = (N - Q) / Q with special handling
          const T = calcChangeRate(N, priorUnadj)
          if (N === 0 && priorUnadj === 0) {
            expect(T).toBe('')
          } else if (priorUnadj === 0) {
            expect(T).toBe('N/A')
          } else {
            expect(T).toBeCloseTo((N - priorUnadj) / priorUnadj, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('prior audited and audited change rate hold', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(
        valArb, valArb, valArb, valArb,
        (N, auditAdj, priorUnadj, priorAdj) => {
          // P = N + O
          const P = calcAuditedWithAdj(N, auditAdj)

          // S = Q + R
          const S = calcAuditedWithAdj(priorUnadj, priorAdj)
          expect(S).toBeCloseTo(priorUnadj + priorAdj, 5)

          // U = (P - S) / S
          const U = calcChangeRate(P, S)
          if (P === 0 && S === 0) {
            expect(U).toBe('')
          } else if (S === 0) {
            expect(U).toBe('N/A')
          } else {
            expect(U).toBeCloseTo((P - S) / S, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 2 PBT: 合计行 ────────────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 2: 合计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 2.4, 3.3, 4.3**
   *
   * For any array of values, calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('calcSubtotal equals manual reduce sum for any array', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          { minLength: 1, maxLength: 30 },
        ),
        (values) => {
          const result = calcSubtotal(values)
          const expected = values.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 4 PBT: 阈值判定 ──────────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 4: 变动率阈值高亮判定', () => {
  /**
   * **Validates: Requirements 3.6, 4.5, 8.2, 8.3, 8.5, 13.3, 25.8**
   *
   * For any numeric rate r and threshold t:
   * isChangeRateExceeding(r, t) === (Math.abs(r) > t)
   */
  it('returns true iff |rate| > threshold for numeric rates', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: 10, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true }),
        (rate, threshold) => {
          const result = isChangeRateExceeding(rate, threshold)
          const expected = Math.abs(rate) > threshold
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('always returns false for empty string or N/A', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true }),
        (threshold) => {
          expect(isChangeRateExceeding('', threshold)).toBe(false)
          expect(isChangeRateExceeding('N/A', threshold)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 10 PBT: 毛利率 ───────────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 10: 毛利率公式正确性', () => {
  /**
   * **Validates: Requirements 8.2, 8.3, 15.1**
   *
   * For any (revenue, cost) pair:
   * calcGrossMarginRate(rev, cost) === (rev - cost) / rev when rev > 0
   */
  it('equals (revenue - cost) / revenue when revenue > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (revenue, cost) => {
          const result = calcGrossMarginRate(revenue, cost)
          const expected = (revenue - cost) / revenue
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when revenue is 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (cost) => {
          expect(calcGrossMarginRate(0, cost)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 11 PBT: 关联价格差异率 ───────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 11: 关联方价格差异率', () => {
  /**
   * **Validates: Requirements 13.2, 13.3**
   *
   * For any (relatedPrice, nonRelatedPrice) pair:
   * calcPriceDiffRate(rp, nrp) === (rp - nrp) / nrp * 100
   */
  it('equals (rp - nrp) / nrp * 100 when nonRelatedPrice > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (relatedPrice, nonRelatedPrice) => {
          const result = calcPriceDiffRate(relatedPrice, nonRelatedPrice)
          const expected = ((relatedPrice - nonRelatedPrice) / nonRelatedPrice) * 100
          expect(result).toBeCloseTo(expected, 4)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when nonRelatedPrice is 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (relatedPrice) => {
          expect(calcPriceDiffRate(relatedPrice, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 13 PBT: IPO可见性 ────────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 13: IPO/舞弊组可见性控制', () => {
  /**
   * **Validates: Requirements 14.1, 26.7**
   *
   * isIpoGroupVisible returns true iff businessCategory contains one of the
   * keywords (case insensitive): 'ipo', 'listed', 'neeq', 'restructuring', 'fraud_risk'
   */
  const IPO_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'fraud_risk'] as const

  it('returns true when businessCategory contains any IPO keyword', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...IPO_KEYWORDS),
        fc.string({ minLength: 0, maxLength: 10 }),
        fc.string({ minLength: 0, maxLength: 10 }),
        (keyword, prefix, suffix) => {
          const category = prefix + keyword + suffix
          expect(isIpoGroupVisible(category)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns true for uppercase keywords (case insensitive)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...IPO_KEYWORDS),
        (keyword) => {
          expect(isIpoGroupVisible(keyword.toUpperCase())).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns false for non-matching categories', () => {
    const nonMatchingArb = fc.constantFrom(
      'normal', 'general_audit', '', 'small_business', 'private_company',
      'state_owned', 'joint_venture', 'foreign_invested',
    )

    fc.assert(
      fc.property(nonMatchingArb, (category) => {
        expect(isIpoGroupVisible(category)).toBe(false)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 14 PBT: 资金回流可疑 ─────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 14: 资金回流可疑判定', () => {
  /**
   * **Validates: Requirements 14.11**
   *
   * isSuspiciousFundFlow returns true iff:
   * 1. diffRatio = |inAmount - outAmount| / max(inAmount, outAmount) < threshold (default 0.1)
   * 2. daysDiff < 30
   * 3. max(inAmount, outAmount) > 0
   */
  it('correctly identifies suspicious flows based on amount proximity and timing', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.nat({ max: 60 }),
        (inAmount, outAmount, daysDiff) => {
          const result = isSuspiciousFundFlow(inAmount, outAmount, daysDiff)
          const maxAmount = Math.max(inAmount, outAmount)

          if (maxAmount === 0) {
            expect(result).toBe(false)
          } else {
            const diffRatio = Math.abs(inAmount - outAmount) / maxAmount
            const expected = diffRatio < 0.1 && daysDiff < 30
            expect(result).toBe(expected)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns false when daysDiff >= 30 regardless of amounts', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 30, max: 60 }),
        (inAmount, outAmount, daysDiff) => {
          expect(isSuspiciousFundFlow(inAmount, outAmount, daysDiff)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 16 PBT: 金额格式化 ───────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 16: 金额格式化规则', () => {
  /**
   * **Validates: Requirements 25.1, 25.2, 25.3, 25.4**
   *
   * parseNum always returns a safe finite number (never NaN or Infinity).
   * For any float input, parseNum(val) returns a finite number or 0.
   */
  it('parseNum always returns a finite number for any double input', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e12, max: 1e12 }),
        (val) => {
          const result = parseNum(val)
          expect(typeof result).toBe('number')
          expect(isFinite(result)).toBe(true)
          expect(isNaN(result)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('parseNum returns finite for string representations', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e12, max: 1e12, noNaN: true, noDefaultInfinity: true }),
        (val) => {
          const result = parseNum(String(val))
          expect(typeof result).toBe('number')
          expect(isFinite(result)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('parseNum returns 0 for null/undefined/empty/NaN/Infinity inputs', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(null, undefined, '', NaN, Infinity, -Infinity, 'abc', 'not-a-number'),
        (val) => {
          const result = parseNum(val as any)
          expect(result).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 20 PBT: 占比计算 ─────────────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 20: 占比计算正确性', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * For any (item, total) pair:
   * calcProportion(item, total) === item / total * 100 when total > 0
   */
  it('equals item / total * 100 when total > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (item, total) => {
          const result = calcProportion(item, total)
          const expected = (item / total) * 100
          expect(result).toBeCloseTo(expected, 4)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when total is 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (item) => {
          expect(calcProportion(item, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 100 when item equals total (total > 0)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (val) => {
          expect(calcProportion(val, val)).toBeCloseTo(100, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
