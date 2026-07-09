/**
 * Property-Based Tests — J2 设定受益计划 公式引擎 + 精算引擎
 *
 * 覆盖 CP-J2-01 ~ CP-J2-07 共 7 个性质测试
 * 科目2221长期应付职工薪酬（贷方/负债类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/ Tasks 2.3 ~ 2.9
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../useJ2FormulaEngine'
import {
  calcInterestCost,
  calcNetLiability,
  calcEndDBO,
  validateAssumptions,
} from '../useJ2ActuarialEngine'

// ═══════════════════════════════════════════════════════════════════
// CP-J2-01: 审定数公式链
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-01: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.2**
   *
   * 审定数 = 未审数 + AJE + RJE，对任意三元组成立
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-02: 负债类贷方期末余额
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-02: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * 负债类期末 = 期初 + 贷方(增加) - 借方(减少)
   * ⚠️ 与资产类(期初+借-贷)方向相反！
   */
  it('calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, credit, debit) => {
          expect(calcLiabilityEndBalance(begin, credit, debit)).toBeCloseTo(begin + credit - debit, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-03: 利息成本公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-03: 利息成本公式', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * 利息成本 = 期初DBO × 折现率
   * 生成器约束：beginDBO > 0, discountRate ∈ (0.01, 0.10)
   */
  it('calcInterestCost(dbo, rate) === dbo × rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1000, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.10, noNaN: true, noDefaultInfinity: true }),
        (beginDBO, discountRate) => {
          expect(calcInterestCost(beginDBO, discountRate)).toBeCloseTo(beginDBO * discountRate, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-04: 净负债公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-04: 净负债公式', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * 净负债 = DBO - 计划资产公允价值
   * 正值=净负债，负值=净资产
   */
  it('calcNetLiability(dbo, pa) === dbo - pa', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (dbo, planAssets) => {
          expect(calcNetLiability(dbo, planAssets)).toBeCloseTo(dbo - planAssets, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-05: DBO期末完整公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-05: DBO期末完整公式', () => {
  /**
   * **Validates: Requirements 4.1**
   *
   * DBO期末 = 期初 + 服务成本 + 利息 + 损失 - 利得 - 已支付
   * 六要素分解完整性
   */
  it('calcEndDBO(b, s, i, l, g, p) === b + s + i + l - g - p', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (beginDBO, serviceCost, interestCost, loss, gain, payments) => {
          const expected = beginDBO + serviceCost + interestCost + loss - gain - payments
          expect(calcEndDBO(beginDBO, serviceCost, interestCost, loss, gain, payments))
            .toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-06: 合计行恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-06: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.5**
   *
   * calcSubtotal(arr) === Σarr
   * 对任意长度数组成立
   */
  it('calcSubtotal(arr) === sum of all elements', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 0, maxLength: 20 },
        ),
        (arr) => {
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J2-07: 精算假设范围校验
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j2-defined-benefit-plan, Property CP-J2-07: 精算假设范围校验', () => {
  /**
   * **Validates: Requirements 4.5**
   *
   * 合理范围内的假设 → isValid === true
   * 超出范围的假设（≤0 或 ≥1） → isValid === false
   */
  it('assumptions within (0,1) are valid; outside are invalid', () => {
    fc.assert(
      fc.property(
        // 合理范围内的精算假设
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        (discountRate, salaryGrowthRate, mortalityRate, turnoverRate) => {
          const result = validateAssumptions({
            discountRate,
            salaryGrowthRate,
            mortalityRate,
            turnoverRate,
          })
          // 所有假设在 (0, 1) 范围内，isValid 应为 true
          expect(result.isValid).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('assumptions at boundary (<=0 or >=1) are invalid', () => {
    fc.assert(
      fc.property(
        // 至少一个超出范围的假设（discountRate <= 0）
        fc.double({ min: -1, max: 0, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        (discountRate, salaryGrowthRate, mortalityRate, turnoverRate) => {
          const result = validateAssumptions({
            discountRate,
            salaryGrowthRate,
            mortalityRate,
            turnoverRate,
          })
          expect(result.isValid).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('assumptions >= 1 are invalid', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 10, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true, noDefaultInfinity: true }),
        (discountRate, salaryGrowthRate, mortalityRate, turnoverRate) => {
          const result = validateAssumptions({
            discountRate,
            salaryGrowthRate,
            mortalityRate,
            turnoverRate,
          })
          expect(result.isValid).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })
})
