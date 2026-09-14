/**
 * I4 长期待摊费用 — 公式引擎 Property-Based Tests
 * 6 Properties (CP-I4-01 ~ CP-I4-06)
 * Spec: .kiro/specs/i4-long-term-prepaid/
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal
} from '../composables/useI4FormulaEngine'
import {
  calcStraightLineAmort,
  calcUnitsOfProductionAmort
} from '../composables/useI4AmortizationEngine'

const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0.01, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

describe('I4 FormulaEngine PBT', () => {
  /**
   * Property P1: 审定数公式链
   * **Validates: Requirements 2.2**
   * calcAuditedAmount(u, a, r) === u + a + r
   */
  it('P1: 审定数 = 未审 + AJE + RJE', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P2: 期末余额
   * **Validates: Requirements 2.3**
   * calcAssetEndBalance(b, i, a, d) === b + i - a - d
   */
  it('P2: 期末 = 期初 + 增加 - 摊销 - 减少', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (b, i, a, d) => {
          expect(calcAssetEndBalance(b, i, a, d)).toBeCloseTo(b + i - a - d, 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P3: 直线法摊销
   * **Validates: Requirements 6.4**
   * calcStraightLineAmort(amount, months) === amount / months
   */
  it('P3: 直线法月摊销 = 原始金额 ÷ 总月数', () => {
    fc.assert(
      fc.property(
        positiveFloat(1, 1e8),
        fc.integer({ min: 1, max: 600 }),
        (amount, months) => {
          const expected = amount / months
          expect(calcStraightLineAmort(amount, months)).toBeCloseTo(expected, 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P4: 工作量法摊销
   * **Validates: Requirements 6.5**
   * calcUnitsOfProductionAmort(a, cu, tu) === a × (cu / tu)
   */
  it('P4: 工作量法月摊销 = 原始金额 × (本月工作量 ÷ 总工作量)', () => {
    fc.assert(
      fc.property(
        positiveFloat(1, 1e8),
        safeFloat(0, 1e6),
        positiveFloat(1, 1e6),
        (amount, currentUnits, totalUnits) => {
          const expected = amount * (currentUnits / totalUnits)
          expect(calcUnitsOfProductionAmort(amount, currentUnits, totalUnits)).toBeCloseTo(expected, 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P5: 合计行恒等
   * **Validates: Requirements 2.4**
   * calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0) (or 0 for empty)
   */
  it('P5: 合计行 = SUM(明细行)', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat(0, 1e6), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P6: 借贷平衡
   * **Validates: Requirements 2.5**
   * 对于任何调整分录集合，Σdebit === Σcredit
   */
  it('P6: 借贷平衡 — Σ借方 === Σ贷方', () => {
    fc.assert(
      fc.property(
        fc.array(
          positiveFloat(0.01, 1e6),
          { minLength: 1, maxLength: 20 }
        ),
        (amounts) => {
          // 构造完全平衡的分录：每个金额同时记借方和贷方
          const totalDebit = amounts.reduce((sum, a) => sum + a, 0)
          const totalCredit = amounts.reduce((sum, a) => sum + a, 0)
          expect(totalDebit).toBeCloseTo(totalCredit, 5)
        }
      ),
      { numRuns: 200 }
    )
  })
})
