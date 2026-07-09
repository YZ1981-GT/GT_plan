/**
 * Property-Based Tests — H2 在建工程公式引擎 + 利息资本化引擎
 *
 * Spec: .kiro/specs/h2-construction-in-progress/ Tasks 2.3 ~ 2.14
 * Framework: fast-check (fc.assert + fc.property)
 * numRuns: 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleWithTransfer,
  calcSubtotal,
  calcCompletionRate,
  calcCostDiffRate,
  calcOverdueDays,
  calcTransferCondition,
  isBalanced,
} from '../composables/useH2FormulaEngine'
import {
  calcWeightedCapRate,
  calcSpecialLoanCap,
  calcDcfPresentValue,
} from '../composables/useH2InterestCapEngine'

// ============================================================
// P1 (Task 2.3): 审定数公式链
// ============================================================
describe('Feature: h2-construction-in-progress, Property P1: 审定数公式链正确性', () => {
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
// P2 (Task 2.4): 资产类期末余额
// ============================================================
describe('Feature: h2-construction-in-progress, Property P2: 资产类期末余额公式', () => {
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
// P3 (Task 2.5): 在建工程三角勾稽（含转固扣减）
// ============================================================
describe('Feature: h2-construction-in-progress, Property P3: 在建工程三角勾稽含转固扣减', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ begin, increase, decrease, transfer ∈ ℝ≥0, end=begin+increase-decrease-transfer:
   * calcTriangleWithTransfer(begin, increase, decrease, transfer, end) === 0
   */
  it('calcTriangleWithTransfer(b, i, d, t, b+i-d-t) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, increase, decrease, transfer) => {
          const end = begin + increase - decrease - transfer
          const result = calcTriangleWithTransfer(begin, increase, decrease, transfer, end)
          expect(Math.abs(result)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P4 (Task 2.6): 合计行恒等
// ============================================================
describe('Feature: h2-construction-in-progress, Property P4: 合计行恒等于明细行之和', () => {
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
// P5 (Task 2.7): 完工率公式正确性
// ============================================================
describe('Feature: h2-construction-in-progress, Property P5: 完工率公式正确性', () => {
  /**
   * **Validates: Requirements 5.2**
   * ∀ accumulated>0, budget>0: calcCompletionRate(acc, bud) === acc/bud×100
   */
  it('calcCompletionRate(acc, bud) === acc / bud * 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (accumulated, budget) => {
          const result = calcCompletionRate(accumulated, budget)
          const expected = (accumulated / budget) * 100
          expect(Math.abs(result! - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P6 (Task 2.8): 加权资本化率计算（无专门借款）
// ============================================================
describe('Feature: h2-construction-in-progress, Property P6: 加权资本化率计算正确性', () => {
  /**
   * **Validates: Requirements 10.4**
   * ∀ loans[]: calcWeightedCapRate(loans) === Σ(p×r×d/365) / Σ(p×d/365)
   */
  it('calcWeightedCapRate(loans) === Σ(p×r×d/365) / Σ(p×d/365)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            principal: fc.double({ min: 1e4, max: 1e9, noNaN: true, noDefaultInfinity: true }),
            rate: fc.double({ min: 0.01, max: 0.2, noNaN: true, noDefaultInfinity: true }),
            days: fc.integer({ min: 1, max: 365 }),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (loans) => {
          const result = calcWeightedCapRate(loans)
          // 手动计算期望值
          let numerator = 0
          let denominator = 0
          for (const loan of loans) {
            const weight = loan.principal * loan.days / 365
            numerator += weight * loan.rate
            denominator += weight
          }
          const expected = denominator === 0 ? 0 : numerator / denominator
          expect(Math.abs(result - expected)).toBeLessThan(1e-10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P7 (Task 2.9): 专门借款利息资本化公式
// ============================================================
describe('Feature: h2-construction-in-progress, Property P7: 专门借款利息资本化公式', () => {
  /**
   * **Validates: Requirements 10.5**
   * ∀ interest>0, idleIncome≥0: calcSpecialLoanCap(interest, idle) === interest - idle
   */
  it('calcSpecialLoanCap(interest, idle) === interest - idle', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (interest, idleIncome) => {
          const result = calcSpecialLoanCap(interest, idleIncome)
          const expected = interest - idleIncome
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P8 (Task 2.10): 工程造价差异率
// ============================================================
describe('Feature: h2-construction-in-progress, Property P8: 工程造价差异率公式', () => {
  /**
   * **Validates: Requirements 8.2**
   * ∀ actual>0, budget>0: calcCostDiffRate(actual, budget) === (actual-budget)/budget×100
   */
  it('calcCostDiffRate(actual, budget) === (actual - budget) / budget * 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (actual, budget) => {
          const result = calcCostDiffRate(actual, budget)
          const expected = ((actual - budget) / budget) * 100
          expect(Math.abs(result! - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P9 (Task 2.11): 转固条件判定（CAS4五条件全满足）
// ============================================================
describe('Feature: h2-construction-in-progress, Property P9: CAS4转固五条件全满足判定', () => {
  /**
   * **Validates: Requirements 6.2**
   * ∀ conditions: boolean[5]: calcTransferCondition(conds) === conds.every(c => c)
   */
  it('calcTransferCondition(conds) === conds.every(c => c)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.boolean(), { minLength: 5, maxLength: 5 }),
        (conditions) => {
          const result = calcTransferCondition(conditions)
          const expected = conditions.every(c => c)
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P10 (Task 2.12): 借贷平衡检查
// ============================================================
describe('Feature: h2-construction-in-progress, Property P10: 借贷平衡检查', () => {
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

// ============================================================
// P11 (Task 2.13): DCF现值
// ============================================================
describe('Feature: h2-construction-in-progress, Property P11: DCF现值计算正确性', () => {
  /**
   * **Validates: Requirements 12.4**
   * ∀ cashFlows[]>0, discountRate>0: calcDcfPresentValue(cfs, r) === Σ(cf_i/(1+r)^(i+1))
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
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P12 (Task 2.14): 工期超期判定
// ============================================================
describe('Feature: h2-construction-in-progress, Property P12: 工期超期判定正确性', () => {
  /**
   * **Validates: Requirements 5.5**
   * ∀ actual ≥ planned (dates): calcOverdueDays(actual, planned) === daysDiff(actual, planned) && result >= 0
   */
  it('calcOverdueDays(actual, planned) === daysDiff && result >= 0', () => {
    // 使用整数天偏移量生成日期，避免 fc.date 可能产生 Invalid Date
    const dateArb = fc.integer({ min: 0, max: 3650 }).map(offset => {
      const base = new Date('2020-01-01')
      base.setDate(base.getDate() + offset)
      return base.toISOString().slice(0, 10)
    })

    fc.assert(
      fc.property(
        dateArb,
        dateArb,
        (dateStr1, dateStr2) => {
          // 确保 actual >= planned
          const actualStr = dateStr1 >= dateStr2 ? dateStr1 : dateStr2
          const plannedStr = dateStr1 >= dateStr2 ? dateStr2 : dateStr1

          const result = calcOverdueDays(actualStr, plannedStr)

          // 手动计算期望天数差
          const actualParsed = new Date(actualStr)
          const plannedParsed = new Date(plannedStr)
          const diffMs = actualParsed.getTime() - plannedParsed.getTime()
          const expected = Math.floor(diffMs / (1000 * 60 * 60 * 24))

          expect(result).toBe(expected)
          expect(result).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
