/**
 * I1 无形资产 — 公式引擎 Property-Based Tests
 * 12 Properties (CP-I1-01 ~ CP-I1-12)
 * Spec: .kiro/specs/i1-intangible-assets/
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  isBalanced,
  calcAllocTotal
} from '../composables/useI1FormulaEngine'
import {
  calcStraightLineAmort,
  calcAmortWithImpairment,
  calcDcfPresentValue,
  calcRecoverableAmount,
  calcImpairmentAmount
} from '../composables/useI1AmortizationEngine'

const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0.01, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

describe('I1 FormulaEngine PBT', () => {
  /**
   * Property P1: 审定数公式链
   * **Validates: Requirements 2.3**
   * calcAuditedAmount(u, a, r) === u + a + r
   */
  it('P1: 审定数 = 未审 + AJE + RJE', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        }
      )
    )
  })

  /**
   * Property P2: 资产类期末余额
   * **Validates: Requirements 2.4**
   * calcAssetEndBalance(b, d, c) === b + d - c
   */
  it('P2: 资产类期末 = 期初 + 借方 - 贷方', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (b, d, c) => {
          expect(calcAssetEndBalance(b, d, c)).toBeCloseTo(b + d - c, 5)
        }
      )
    )
  })

  /**
   * Property P3: 备抵类期末余额
   * **Validates: Requirements 2.5**
   * calcContraEndBalance(b, d, c) === b + c - d
   */
  it('P3: 备抵类期末 = 期初 + 贷方 - 借方', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (b, d, c) => {
          expect(calcContraEndBalance(b, d, c)).toBeCloseTo(b + c - d, 5)
        }
      )
    )
  })

  /**
   * Property P4: 三角勾稽恒等式
   * **Validates: Requirements 2.6**
   * 当 end = begin + increase - decrease 时，reconciliation === 0
   */
  it('P4: 三角勾稽差额 ≡ 0（当期末=期初+增加-减少）', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (begin, increase, decrease) => {
          const end = begin + increase - decrease
          expect(calcTriangleReconciliation(begin, increase, decrease, end)).toBeCloseTo(0, 5)
        }
      )
    )
  })

  /**
   * Property P5: 合计行恒等
   * **Validates: Requirements 2.7**
   * calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('P5: 合计行 = SUM(明细行)', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat(0, 1e6), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        }
      )
    )
  })

  /**
   * Property P6: 直线法摊销
   * **Validates: Requirements 11.4**
   * calcStraightLineAmort(cost, salvage, months) === (cost - salvage) / months
   */
  it('P6: 直线法月摊销 = (原值 - 残值) / 总月数', () => {
    fc.assert(
      fc.property(
        positiveFloat(100, 1e8),
        positiveFloat(0, 1e6),
        fc.float({ min: Math.fround(1), max: Math.fround(1200), noNaN: true, noDefaultInfinity: true }),
        (cost, salvageRaw, months) => {
          const salvage = Math.min(salvageRaw, cost * 0.9) // 残值 < 原值
          const expected = (cost - salvage) / months
          expect(calcStraightLineAmort(cost, salvage, months)).toBeCloseTo(expected, 5)
        }
      )
    )
  })

  /**
   * Property P7: 剩余年限法摊销（含减值）
   * **Validates: Requirements 11.5**
   * calcAmortWithImpairment(cost, salvage, accAmort, impairment, rem) === (cost-salvage-accAmort-impairment)/rem
   */
  it('P7: 含减值摊销 = (原值 - 残值 - 累计摊销 - 减值) / 剩余月数', () => {
    fc.assert(
      fc.property(
        positiveFloat(1000, 1e8),
        positiveFloat(0, 1e5),
        positiveFloat(0, 1e6),
        positiveFloat(0, 1e6),
        fc.float({ min: Math.fround(1), max: Math.fround(1200), noNaN: true, noDefaultInfinity: true }),
        (cost, salvage, accAmort, impairment, rem) => {
          const expected = (cost - salvage - accAmort - impairment) / rem
          expect(calcAmortWithImpairment(cost, salvage, accAmort, impairment, rem)).toBeCloseTo(expected, 5)
        }
      )
    )
  })

  /**
   * Property P8: DCF现值计算
   * **Validates: Requirements 13.2**
   * calcDcfPresentValue(cfs, r) === Σ(cf_i / (1+r)^(i+1))
   */
  it('P8: DCF现值 = Σ(CF_i / (1+r)^(i+1))', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: Math.fround(1), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 10 }),
        fc.float({ min: Math.fround(0.01), max: Math.fround(0.5), noNaN: true, noDefaultInfinity: true }),
        (cfs, r) => {
          let expected = 0
          for (let i = 0; i < cfs.length; i++) {
            expected += cfs[i] / Math.pow(1 + r, i + 1)
          }
          expect(calcDcfPresentValue(cfs, r)).toBeCloseTo(expected, 2)
        }
      )
    )
  })

  /**
   * Property P9: 可收回金额MAX选取
   * **Validates: Requirements 13.3**
   * calcRecoverableAmount(fv, dcf) === Math.max(fv, dcf)
   */
  it('P9: 可收回金额 = MAX(公允价值-处置费, DCF)', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9),
        (fv, dcf) => {
          expect(calcRecoverableAmount(fv, dcf)).toBe(Math.max(fv, dcf))
        }
      )
    )
  })

  /**
   * Property P10: 减值金额非负且≤账面
   * **Validates: Requirements 12.2**
   * calcImpairmentAmount(bv, ra) ∈ [0, bv]
   */
  it('P10: 减值金额 ∈ [0, 账面净值]', () => {
    fc.assert(
      fc.property(
        positiveFloat(1, 1e9),
        safeFloat(0, 1e9),
        (bv, ra) => {
          const result = calcImpairmentAmount(bv, ra)
          expect(result).toBeGreaterThanOrEqual(0)
          expect(result).toBeLessThanOrEqual(bv)
        }
      )
    )
  })

  /**
   * Property P11: 摊销分配合计=总额
   * **Validates: Requirements 11.7**
   * 各部门分配额之和 === total（精度0.01）
   */
  it('P11: 摊销分配合计 ≈ 总额', () => {
    fc.assert(
      fc.property(
        positiveFloat(100, 1e8),
        fc.array(positiveFloat(0.01, 100), { minLength: 1, maxLength: 10 }),
        (total, rawProportions) => {
          // 归一化比例
          const sum = rawProportions.reduce((a, b) => a + b, 0)
          const allocations = rawProportions.map(p => (p / sum) * total)
          const allocTotal = calcAllocTotal(allocations)
          expect(Math.abs(allocTotal - total)).toBeLessThanOrEqual(0.01)
        }
      )
    )
  })

  /**
   * Property P12: 借贷平衡
   * **Validates: Requirements 2.8**
   * isBalanced === (Σdebit === Σcredit)
   */
  it('P12: 借贷平衡 — Σ借方 === Σ贷方', () => {
    fc.assert(
      fc.property(
        fc.array(
          positiveFloat(0.01, 1e6),
          { minLength: 1, maxLength: 20 }
        ),
        (amounts) => {
          // 构造完全平衡的分录：每个金额同时记借和贷
          const entries = amounts.map(a => ({ debit: a, credit: a }))
          expect(isBalanced(entries)).toBe(true)
        }
      )
    )
  })
})
