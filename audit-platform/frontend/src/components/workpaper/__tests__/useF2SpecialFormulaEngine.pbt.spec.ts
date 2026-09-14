/**
 * Property-Based Tests — F2 存货特殊组公式引擎
 *
 * Spec: .kiro/specs/f2-inventory-special/
 * Tasks: 2.2 ~ 2.13
 *
 * Property 1: 待发生成本=预计总成本-已发生成本
 * Property 2: 减值≥0
 * Property 3: 亏损判定=总成本>总收入
 * Property 4: 预计损失=(总成本-总收入)×(1-完工进度)
 * Property 5: 完工进度=已确认收入/预计总收入
 * Property 6: 产能利用率=实际/设计
 * Property 7: 价差率=(实际-参考)/参考
 * Property 8: 集中度=供应商/总额
 * Property 9: 期末=期初+增加-减少
 * Property 10: 小计=设备+建安+人工+其他
 * Property 11: 投入产出比=投入/产出
 * Property 12: 完成度=已完成/(总数-不适用)×100
 *
 * **Validates: Requirements 18.1~18.15, 3.2, 3.4, 5.2, 5.3, 5.5, 6.2, 6.4, 9.2, 10.4, 11.3, 13.2, 14.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcRemainingCost,
  calcImpairment,
  isLossContract,
  calcExpectedLoss,
  calcCompletionRate,
  calcCapacityUtilization,
  calcPriceDeviation,
  calcConcentrationRatio,
  calcEndBalance,
  calcSubtotalByCategory,
  calcInputOutputRatio,
  calcChecklistCompletion,
} from '../composables/useF2SpecialFormulaEngine'

// ─── Property 1 PBT: 待发生成本公式 ────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 1: 待发生成本=预计总成本-已发生成本', () => {
  /**
   * **Validates: Requirements 18.1, 5.3**
   *
   * ∀ totalCost, incurredCost ∈ [0, 1e9]:
   * calcRemainingCost(totalCost, incurredCost) === totalCost - incurredCost
   */
  it('待发生成本恒等于预计总成本减去已发生成本', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (totalCost, incurredCost) => {
          const result = calcRemainingCost(totalCost, incurredCost)
          const expected = totalCost - incurredCost
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 2 PBT: 减值公式非负性 ────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 2: 减值≥0', () => {
  /**
   * **Validates: Requirements 18.2, 5.5**
   *
   * ∀ bookValue, recoverableAmount ∈ [0, 1e9]:
   * calcImpairment(bookValue, recoverableAmount) >= 0
   */
  it('减值结果恒≥0（max(0, 账面-可收回)）', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (bookValue, recoverableAmount) => {
          const result = calcImpairment(bookValue, recoverableAmount)
          expect(result).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 3 PBT: 亏损判定一致性 ────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 3: 亏损判定=总成本>总收入', () => {
  /**
   * **Validates: Requirements 18.4, 6.2**
   *
   * ∀ totalRevenue, totalCost ∈ [0, 1e9]:
   * isLossContract(totalRevenue, totalCost) === (totalCost > totalRevenue)
   */
  it('亏损判定恒等于总成本>总收入', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (totalRevenue, totalCost) => {
          const result = isLossContract(totalRevenue, totalCost)
          const expected = totalCost > totalRevenue
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 4 PBT: 预计损失公式 ──────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 4: 预计损失=(总成本-总收入)×(1-完工进度)', () => {
  /**
   * **Validates: Requirements 18.5, 6.4**
   *
   * ∀ totalCost > totalRevenue, completionRate ∈ [0,1]:
   * calcExpectedLoss(totalRevenue, totalCost, completionRate) === (totalCost - totalRevenue) × (1 - completionRate)
   */
  it('亏损合同的预计损失=(总成本-总收入)×(1-完工进度)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1, noNaN: true }),
        (totalRevenue, costDelta, completionRate) => {
          // Ensure totalCost > totalRevenue by adding a positive delta
          const totalCost = totalRevenue + costDelta + 0.01
          const result = calcExpectedLoss(totalRevenue, totalCost, completionRate)
          const expected = (totalCost - totalRevenue) * (1 - completionRate)
          expect(result).toBeCloseTo(expected, 3)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 5 PBT: 完工进度范围 ──────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 5: 完工进度=已确认收入/预计总收入', () => {
  /**
   * **Validates: Requirements 18.6, 5.2**
   *
   * ∀ recognizedRevenue ∈ [0, 2e9], totalRevenue ∈ (0, 1e9]:
   * calcCompletionRate(recognizedRevenue, totalRevenue) === recognizedRevenue/totalRevenue
   */
  it('完工进度恒等于已确认收入/预计总收入', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 2e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (recognizedRevenue, totalRevenue) => {
          const result = calcCompletionRate(recognizedRevenue, totalRevenue)
          const expected = recognizedRevenue / totalRevenue
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 6 PBT: 产能利用率公式 ────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 6: 产能利用率=实际/设计', () => {
  /**
   * **Validates: Requirements 18.7, 9.2**
   *
   * ∀ actual, designed ∈ [0.1, 1e6]:
   * calcCapacityUtilization(actual, designed) === actual/designed
   */
  it('产能利用率恒等于实际产量/设计产能', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (actual, designed) => {
          const result = calcCapacityUtilization(actual, designed)
          const expected = actual / designed
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 7 PBT: 价差率公式 ────────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 7: 价差率=(实际-参考)/参考', () => {
  /**
   * **Validates: Requirements 18.9, 11.3**
   *
   * ∀ actualPrice ∈ ℝ, refPrice ∈ ℝ\{0}:
   * calcPriceDeviation(actualPrice, refPrice) === (actualPrice - refPrice)/refPrice
   */
  it('价差率恒等于(实际价格-参考价格)/参考价格', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (actualPrice, refPrice) => {
          const result = calcPriceDeviation(actualPrice, refPrice)
          const expected = (actualPrice - refPrice) / refPrice
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('负参考价格同样成立', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e6, max: -0.01, noNaN: true, noDefaultInfinity: true }),
        (actualPrice, refPrice) => {
          const result = calcPriceDeviation(actualPrice, refPrice)
          const expected = (actualPrice - refPrice) / refPrice
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 8 PBT: 集中度公式 ────────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 8: 集中度=供应商/总额×100', () => {
  /**
   * **Validates: Requirements 18.10, 13.2**
   *
   * ∀ supplierAmount, totalAmount ∈ (0, 1e9]:
   * calcConcentrationRatio(supplierAmount, totalAmount) === supplierAmount/totalAmount × 100
   */
  it('集中度恒等于供应商金额/采购总额×100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (supplierAmount, totalAmount) => {
          const result = calcConcentrationRatio(supplierAmount, totalAmount)
          const expected = (supplierAmount / totalAmount) * 100
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 9 PBT: 期末余额公式 ──────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 9: 期末=期初+增加-减少', () => {
  /**
   * **Validates: Requirements 18.13, 3.2**
   *
   * ∀ opening, increase, decrease ∈ [-1e9, 1e9]:
   * calcEndBalance(opening, increase, decrease) === opening + increase - decrease
   */
  it('期末余额恒等于期初+增加-减少', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (opening, increase, decrease) => {
          const result = calcEndBalance(opening, increase, decrease)
          const expected = opening + increase - decrease
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 10 PBT: 分类小计公式 ─────────────────────────────────────────

describe('Feature: f2-inventory-special, Property 10: 小计=设备+建安+人工+其他', () => {
  /**
   * **Validates: Requirements 18.12, 3.4**
   *
   * ∀ equipment, construction, labor, other ∈ [-1e9, 1e9]:
   * calcSubtotalByCategory(equipment, construction, labor, other) === equipment + construction + labor + other
   */
  it('分类小计恒等于设备材料+建安分包+人工+其他之和', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (equipment, construction, labor, other) => {
          const result = calcSubtotalByCategory(equipment, construction, labor, other)
          const expected = equipment + construction + labor + other
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 11 PBT: 投入产出比公式 ───────────────────────────────────────

describe('Feature: f2-inventory-special, Property 11: 投入产出比=投入/产出', () => {
  /**
   * **Validates: Requirements 18.15, 10.4**
   *
   * ∀ input, output ∈ [0.1, 1e6]:
   * calcInputOutputRatio(input, output) === input/output
   */
  it('投入产出比恒等于投入量/产出量', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (input, output) => {
          const result = calcInputOutputRatio(input, output)
          const expected = input / output
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 12 PBT: 核查完成度公式 ───────────────────────────────────────

describe('Feature: f2-inventory-special, Property 12: 完成度=已完成/(总数-不适用)×100', () => {
  /**
   * **Validates: Requirements 18.11, 14.3**
   *
   * ∀ completed ∈ [0,10], total ∈ [1,10], notApplicable ∈ [0, total-1]:
   * calcChecklistCompletion(completed, total, notApplicable) === completed/(total-notApplicable)×100
   */
  it('核查完成度恒等于已完成/(总数-不适用)×100', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }).chain((total) =>
          fc.tuple(
            fc.integer({ min: 0, max: 10 }),
            fc.constant(total),
            fc.integer({ min: 0, max: total - 1 }),
          ),
        ),
        ([completed, total, notApplicable]) => {
          const result = calcChecklistCompletion(completed, total, notApplicable)
          const expected = (completed / (total - notApplicable)) * 100
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
