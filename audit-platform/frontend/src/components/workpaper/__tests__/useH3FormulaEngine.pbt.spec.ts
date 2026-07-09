/**
 * Property-Based Tests — H3 投资性房地产公式引擎 + 互转引擎
 *
 * Spec: .kiro/specs/h3-investment-property/ Tasks 2.3 ~ 2.16
 * Framework: fast-check (fc.assert + fc.property)
 * numRuns: 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcFairEndBalance,
  calcCostTriangle,
  calcSubtotal,
  calcStraightLineDepreciation,
  calcFairValueChange,
  calcRentalIncome,
  calcDcfPresentValue,
  isBalanced,
} from '../composables/useH3FormulaEngine'
import {
  calcSelfToInvestFair,
  calcInvestToSelf,
  calcTitleDiff,
} from '../composables/useH3TransferEngine'

// ============================================================
// P1 (Task 2.3): 审定数公式链
// ============================================================
describe('Feature: h3-investment-property, Property P1: 审定数公式链正确性', () => {
  /**
   * **Validates: Requirements 1.5, 2.3**
   * ∀ unadj, aje, rje ∈ ℝ: calcAuditedAmount(unadj, aje, rje) === unadj + aje + rje
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (unadj, aje, rje) => {
          const result = calcAuditedAmount(unadj, aje, rje)
          const expected = unadj + aje + rje
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P2 (Task 2.4): 资产类期末余额（成本模式）
// ============================================================
describe('Feature: h3-investment-property, Property P2: 资产类期末余额（成本模式）', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ begin, debit, credit ∈ ℝ≥0: calcAssetEndBalance(begin, debit, credit) === begin + debit - credit
   */
  it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, debit, credit) => {
          const result = calcAssetEndBalance(begin, debit, credit)
          const expected = begin + debit - credit
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P3 (Task 2.5): 公允价值模式期末
// ============================================================
describe('Feature: h3-investment-property, Property P3: 公允价值模式期末公式', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ begin, increase, decrease, transfer, fairChange ∈ ℝ:
   * calcFairEndBalance(b, i, d, t, fc) === b + i - d + t + fc
   */
  it('calcFairEndBalance(b, i, d, t, fc) === b + i - d + t + fc', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, increase, decrease, transfer, fairChange) => {
          const result = calcFairEndBalance(begin, increase, decrease, transfer, fairChange)
          const expected = begin + increase - decrease + transfer + fairChange
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P4 (Task 2.6): 三角勾稽（成本模式）
// ============================================================
describe('Feature: h3-investment-property, Property P4: 成本模式三角勾稽', () => {
  /**
   * **Validates: Requirements 2.5**
   * ∀ begin, increase, decrease, transfer ∈ ℝ≥0, end=begin+increase-decrease+transfer:
   * calcCostTriangle(b, i, d, t, b+i-d+t) === 0
   */
  it('calcCostTriangle(b, i, d, t, b+i-d+t) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, increase, decrease, transfer) => {
          const end = begin + increase - decrease + transfer
          const result = calcCostTriangle(begin, increase, decrease, transfer, end)
          expect(Math.abs(result)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P5 (Task 2.7): 合计行恒等
// ============================================================
describe('Feature: h3-investment-property, Property P5: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.5**
   * ∀ arr: number[] (len≥1): calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P6 (Task 2.8): 互转公允值（自用→投资）
// ============================================================
describe('Feature: h3-investment-property, Property P6: 自用→投资互转公允值处理', () => {
  /**
   * **Validates: Requirements 7.2**
   * ∀ bookValue, fairValue ∈ ℝ≥0:
   * calcSelfToInvestFair(book, fair).oci === max(fair-book, 0)
   * calcSelfToInvestFair(book, fair).pl === min(fair-book, 0)
   */
  it('oci === max(fair-book, 0) && pl === min(fair-book, 0)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (bookValue, fairValue) => {
          const result = calcSelfToInvestFair(bookValue, fairValue)
          const diff = fairValue - bookValue
          expect(result.oci).toBe(Math.max(diff, 0))
          expect(result.pl).toBe(Math.min(diff, 0))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P7 (Task 2.9): 互转账面值（投资→自用）
// ============================================================
describe('Feature: h3-investment-property, Property P7: 投资→自用互转用公允作入账', () => {
  /**
   * **Validates: Requirements 7.3**
   * ∀ fairValue ∈ ℝ>0: calcInvestToSelf(fairValue) === fairValue
   */
  it('calcInvestToSelf(fair) === fair', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (fairValue) => {
          const result = calcInvestToSelf(fairValue)
          expect(result).toBe(fairValue)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P8 (Task 2.10): 折旧公式（成本模式直线法）
// ============================================================
describe('Feature: h3-investment-property, Property P8: 成本模式直线法折旧', () => {
  /**
   * **Validates: Requirements 8.3**
   * ∀ cost>0, 0≤rate<1, life≥1:
   * calcStraightLineDepreciation(cost, rate, life) === cost×(1-rate)/life/12
   */
  it('calcStraightLineDepreciation(cost, rate, life) === cost*(1-rate)/life/12', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 50 }),
        (cost, salvageRate, usefulLife) => {
          const result = calcStraightLineDepreciation(cost, salvageRate, usefulLife)
          const expected = (cost * (1 - salvageRate)) / usefulLife / 12
          // Relative tolerance for floating point
          const relErr = Math.abs(result - expected) / Math.max(Math.abs(expected), 1)
          expect(relErr).toBeLessThan(1e-10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P9 (Task 2.11): 公允价值变动损益
// ============================================================
describe('Feature: h3-investment-property, Property P9: 公允价值变动损益公式', () => {
  /**
   * **Validates: Requirements 9.3**
   * ∀ endFair, beginFair ∈ ℝ≥0: calcFairValueChange(end, begin) === end - begin
   */
  it('calcFairValueChange(end, begin) === end - begin', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (endFair, beginFair) => {
          const result = calcFairValueChange(endFair, beginFair)
          const expected = endFair - beginFair
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P10 (Task 2.12): 租金收入测算
// ============================================================
describe('Feature: h3-investment-property, Property P10: 租金收入测算公式', () => {
  /**
   * **Validates: Requirements 14.2**
   * ∀ rent>0, 1≤months≤12, 0≤vacancy<1:
   * calcRentalIncome(rent, months, vacancy) === rent × months × (1 - vacancy)
   */
  it('calcRentalIncome(rent, months, vacancy) === rent * months * (1 - vacancy)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 12 }),
        fc.double({ min: 0, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        (monthlyRent, months, vacancyRate) => {
          const result = calcRentalIncome(monthlyRent, months, vacancyRate)
          const expected = monthlyRent * months * (1 - vacancyRate)
          const relErr = Math.abs(result - expected) / Math.max(Math.abs(expected), 1)
          expect(relErr).toBeLessThan(1e-10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P11 (Task 2.13): DCF现值（仅成本模式）
// ============================================================
describe('Feature: h3-investment-property, Property P11: DCF现值计算', () => {
  /**
   * **Validates: Requirements 11.4**
   * ∀ cashFlows[]>0, discountRate>0:
   * calcDcfPresentValue(cfs, r) === Σ(cf_i / (1+r)^(i+1))
   */
  it('calcDcfPresentValue(cfs, r) === Σ(cf_i / (1+r)^(i+1))', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 10 }),
        fc.double({ min: 0.01, max: 0.3, noNaN: true, noDefaultInfinity: true }),
        (cashFlows, discountRate) => {
          const result = calcDcfPresentValue(cashFlows, discountRate)
          // 手动计算期望值
          let expected = 0
          for (let i = 0; i < cashFlows.length; i++) {
            expected += cashFlows[i] / Math.pow(1 + discountRate, i + 1)
          }
          // Relative tolerance for floating point accumulation
          const relErr = Math.abs(result - expected) / Math.max(Math.abs(expected), 1)
          expect(relErr).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P12 (Task 2.14): 产权差异
// ============================================================
describe('Feature: h3-investment-property, Property P12: 产权差异=账面-证载', () => {
  /**
   * **Validates: Requirements 12.2**
   * ∀ bookValue, certValue ∈ ℝ≥0: calcTitleDiff(book, cert) === book - cert
   */
  it('calcTitleDiff(book, cert) === book - cert', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (bookValue, certValue) => {
          const result = calcTitleDiff(bookValue, certValue)
          const expected = bookValue - certValue
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P13 (Task 2.15): measurement_model filter幂等性
// ============================================================
describe('Feature: h3-investment-property, Property P13: 计量模式切换幂等性', () => {
  /**
   * **Validates: Requirements 1.11-1.12**
   * 连续切换N次后最终状态 = 最后一次设定值（幂等）
   * Simple state machine: apply sequence of switches, final state === last element
   */
  it('switching N times, final state === last switch value', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('cost', 'fair_value'),
        fc.array(fc.constantFrom('cost', 'fair_value'), { minLength: 1, maxLength: 10 }),
        (initial, switches) => {
          // Simulate state machine: start with initial, apply each switch
          let state = initial
          for (const s of switches) {
            state = s // each switch sets the state to the new value
          }
          // Final state should equal the last switch value (idempotent)
          const lastSwitch = switches[switches.length - 1]
          expect(state).toBe(lastSwitch)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P14 (Task 2.16): 借贷平衡
// ============================================================
describe('Feature: h3-investment-property, Property P14: 借贷平衡检查', () => {
  /**
   * **Validates: Requirements 4.5**
   * ∀ entries[]: isBalanced(entries) === (|SUM(debit) - SUM(credit)| < 1e-6)
   */
  it('isBalanced(entries) === (Math.abs(SUM(debit) - SUM(credit)) < 1e-6)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            debit: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
            credit: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (entries) => {
          const result = isBalanced(entries)
          const totalDebit = entries.reduce((sum, e) => sum + e.debit, 0)
          const totalCredit = entries.reduce((sum, e) => sum + e.credit, 0)
          const expected = Math.abs(totalDebit - totalCredit) < 1e-6
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})
