/**
 * Property-Based Tests — G4 债权投资(main组) 公式引擎
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Tasks 2.2 ~ 2.15
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcBalanceSubtotal,
  calcAmortizedCost,
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingBalance,
  calcInitialCarryingAmount,
  isDebitCreditBalanced,
  calcPeriodEndComponent,
  calcChangeRate,
  calcOneYearMaturity,
  calcBookValue,
} from '../useG4MainFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// P1 ~ P13: Property-Based Tests
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-main, Property 1: 借方余额公式', () => {
  /**
   * **Validates: Requirements 3.3, 8.1**
   */
  it('calcDebitBalance(opening, debit, credit) === opening + debit - credit', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (opening, debit, credit) => {
          expect(calcDebitBalance(opening, debit, credit)).toBeCloseTo(opening + debit - credit, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 2: 审定数公式', () => {
  /**
   * **Validates: Requirements 3.4, 8.2**
   */
  it('calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (unadjusted, aje, rje) => {
          expect(calcAdjustedAmount(unadjusted, aje, rje)).toBeCloseTo(unadjusted + aje + rje, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 3: 余额小计公式（三要素加法）', () => {
  /**
   * **Validates: Requirements 5.2, 5.4, 5.8, 8.4**
   */
  it('calcBalanceSubtotal(cost, interestAdj, accruedInterest) === cost + interestAdj + accruedInterest', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (cost, interestAdj, accruedInterest) => {
          expect(calcBalanceSubtotal(cost, interestAdj, accruedInterest)).toBeCloseTo(
            cost + interestAdj + accruedInterest,
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 4: 摊余成本公式', () => {
  /**
   * **Validates: Requirements 3.5, 5.3, 5.9, 7.3, 8.3**
   */
  it('calcAmortizedCost(subtotal, impairment) === subtotal - impairment', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (subtotal, impairment) => {
          expect(calcAmortizedCost(subtotal, impairment)).toBeCloseTo(subtotal - impairment, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 5: 实际利息收入公式', () => {
  /**
   * **Validates: Requirements 7.4, 7.5, 8.5**
   */
  it('整年: calcEffectiveInterest(amortizedCost, rate) === amortizedCost × rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true, noDefaultInfinity: true }),
        (amortizedCost, rate) => {
          expect(calcEffectiveInterest(amortizedCost, rate)).toBeCloseTo(amortizedCost * rate, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('按天数: calcEffectiveInterest(amortizedCost, rate, days) === amortizedCost × rate × days / 365', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 366 }),
        (amortizedCost, rate, days) => {
          expect(calcEffectiveInterest(amortizedCost, rate, days)).toBeCloseTo(
            amortizedCost * rate * days / 365,
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 6: 现金流入公式', () => {
  /**
   * **Validates: Requirements 7.6, 8.6**
   */
  it('整年: calcCashInflow(faceValue, couponRate) === faceValue × couponRate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true, noDefaultInfinity: true }),
        (faceValue, couponRate) => {
          expect(calcCashInflow(faceValue, couponRate)).toBeCloseTo(faceValue * couponRate, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('按天数: calcCashInflow(faceValue, couponRate, days) === faceValue × couponRate × days / 365', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 366 }),
        (faceValue, couponRate, days) => {
          expect(calcCashInflow(faceValue, couponRate, days)).toBeCloseTo(
            faceValue * couponRate * days / 365,
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 7: 期末账面余额公式', () => {
  /**
   * **Validates: Requirements 7.7, 8.7**
   */
  it('calcEndingBalance === opening + interest - cashInflow - principalRepaid', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (opening, interest, cashInflow, principalRepaid) => {
          expect(calcEndingBalance(opening, interest, cashInflow, principalRepaid)).toBeCloseTo(
            opening + interest - cashInflow - principalRepaid,
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 8: 初始入账价值公式', () => {
  /**
   * **Validates: Requirements 7.2, 8.8**
   */
  it('calcInitialCarryingAmount(price, fees) === price + fees', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
        (price, fees) => {
          expect(calcInitialCarryingAmount(price, fees)).toBeCloseTo(price + fees, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 9: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 6.2, 8.12**
   */
  it('isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const d = debits.reduce((s, v) => s + v, 0)
          const c = credits.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 10: 期末分项一致性（加法交换律）', () => {
  /**
   * **Validates: Requirements 5.5, 5.6, 5.7, 8.13**
   */
  it('calcPeriodEndComponent(opening, change) === opening + change', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (opening, change) => {
          expect(calcPeriodEndComponent(opening, change)).toBeCloseTo(opening + change, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('满足交换律: calcPeriodEndComponent(a, b) === calcPeriodEndComponent(b, a)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (a, b) => {
          expect(calcPeriodEndComponent(a, b)).toBeCloseTo(calcPeriodEndComponent(b, a), 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 11: 变动率方向性', () => {
  /**
   * **Validates: Requirements 3.10, 8.9**
   */
  it('current > prior > 0 → positive rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior + delta
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('current < prior, prior > 0 → negative rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.02, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          // Ensure current < prior by subtracting a positive delta
          const current = prior - Math.min(delta, prior * 0.99)
          if (current >= prior) return // skip degenerate
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeLessThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('prior === 0 → null', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (current) => {
          expect(calcChangeRate(0, current)).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 12: 一年内到期小计公式', () => {
  /**
   * **Validates: Requirements 5.10, 8.10**
   */
  it('calcOneYearMaturity(balance, impairment) === balance - impairment', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (balance, impairment) => {
          expect(calcOneYearMaturity(balance, impairment)).toBeCloseTo(balance - impairment, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g4-bond-investment-main, Property 13: 账面价值公式', () => {
  /**
   * **Validates: Requirements 5.11, 8.11**
   */
  it('calcBookValue(amortized, oneYear) === amortized - oneYear', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (amortized, oneYear) => {
          expect(calcBookValue(amortized, oneYear)).toBeCloseTo(amortized - oneYear, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// Unit Tests: parseNum边界 + 除零保护 + 浮点精度
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g4-bond-investment-main, Unit: parseNum边界与除零保护', () => {
  /**
   * **Validates: Requirements 8.14, 8.15**
   */
  it('parseNum(null) === 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('parseNum(undefined) === 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('parseNum(NaN) === 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it("parseNum('') === 0", () => {
    expect(parseNum('')).toBe(0)
  })

  it("parseNum('abc') === 0（非数字字符串）", () => {
    expect(parseNum('abc')).toBe(0)
  })

  it("parseNum('hello world') === 0", () => {
    expect(parseNum('hello world')).toBe(0)
  })

  it('parseNum(Infinity) === 0', () => {
    expect(parseNum(Infinity)).toBe(0)
  })

  it('parseNum(-Infinity) === 0', () => {
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('calcChangeRate(0, x) returns null without throwing', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
    expect(calcChangeRate(0, -50)).toBeNull()
    expect(calcChangeRate(0, 0)).toBeNull()
  })

  it('金额保留2位小数（四舍五入）验证', () => {
    // 验证公式引擎输出可安全 toFixed(2) 四舍五入
    const result = calcDebitBalance(100.126, 200.456, 50.123)
    // 100.126 + 200.456 - 50.123 = 250.459
    const rounded = Number(result.toFixed(2))
    expect(rounded).toBe(250.46)
  })

  it('利率至少4位小数精度', () => {
    // 验证实际利率法保持足够精度
    const result = calcEffectiveInterest(1000000, 0.0456)
    expect(result).toBeCloseTo(45600, 2)
    // 验证更小的利率
    const result2 = calcEffectiveInterest(1000000, 0.00015)
    expect(result2).toBeCloseTo(150, 2)
  })
})
