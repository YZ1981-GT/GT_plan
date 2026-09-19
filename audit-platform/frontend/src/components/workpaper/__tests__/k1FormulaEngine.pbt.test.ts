/**
 * K1 其他应收款 — 公式引擎 Property-Based Tests (CP-K1-01~09)
 *
 * 覆盖 useK1FormulaEngine + useK1ECLEngine + useK1BadDebtCalcEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：1221其他应收款（借方/资产类）+ 坏账准备（贷方/备抵类）
 *
 * Spec: .kiro/specs/k1-other-receivables/design.md → Correctness Properties CP-K1-01~09
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcBadDebtEnd,
  calcNetValue,
  calcProportion,
  calcSubtotal,
} from '../composables/useK1FormulaEngine'
import { determineStage } from '../composables/useK1ECLEngine'
import { calcECL } from '../composables/useK1BadDebtCalcEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K1 FormulaEngine PBT', () => {
  // ═══ CP-K1-01: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: k1-other-receivables, Property CP-K1-01: 审定数公式链', () => {
    it('CP-K1-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K1-02: 资产类期末=期初+借-贷 ═══
  // **Validates: Requirements 2.4**
  describe('Feature: k1-other-receivables, Property CP-K1-02: 资产类期末=期初+借-贷', () => {
    it('CP-K1-02: calcAssetEndBalance(b, dr, cr) === b + dr - cr', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, dr, cr) => {
          const result = calcAssetEndBalance(b, dr, cr)
          const expected = b + dr - cr
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K1-03: 备抵类期末=期初+贷-借 ═══
  // **Validates: Requirements 2.5**
  describe('Feature: k1-other-receivables, Property CP-K1-03: 备抵类期末=期初+贷-借', () => {
    it('CP-K1-03: calcContraEndBalance(b, cr, dr) === b + cr - dr', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, cr, dr) => {
          const result = calcContraEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K1-04: 期末坏账=期初+计提-转回-核销 ═══
  // **Validates: Requirements 4.2**
  describe('Feature: k1-other-receivables, Property CP-K1-04: 期末坏账=期初+计提-转回-核销', () => {
    it('CP-K1-04: calcBadDebtEnd(b, p, rev, wo) === b + p - rev - wo', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), safeFloat(), (b, p, rev, wo) => {
          const result = calcBadDebtEnd(b, p, rev, wo)
          const expected = b + p - rev - wo
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K1-05: 账面净值=应收-坏账 ═══
  // **Validates: Requirements 2.6**
  describe('Feature: k1-other-receivables, Property CP-K1-05: 账面净值=应收-坏账', () => {
    it('CP-K1-05: calcNetValue(rec, bd) === rec - bd', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (rec, bd) => {
          const result = calcNetValue(rec, bd)
          const expected = rec - bd
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K1-06: ECL=EAD×PD×LGD ═══
  // **Validates: Requirements 6.2**
  describe('Feature: k1-other-receivables, Property CP-K1-06: ECL=EAD×PD×LGD', () => {
    it('CP-K1-06: calcECL(ead, pd, lgd) === ead × pd × lgd (ead≥0, pd∈[0,1], lgd∈[0,1])', () => {
      fc.assert(
        fc.property(
          positiveFloat(0, 1e9),
          fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          (ead, pd, lgd) => {
            const result = calcECL(ead, pd, lgd)
            const expected = ead * pd * lgd
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ CP-K1-07: 阶段判定∈{1,2,3} 且 imp=true→3 ═══
  // **Validates: Requirements 5.2**
  describe('Feature: k1-other-receivables, Property CP-K1-07: 阶段判定确定性', () => {
    it('CP-K1-07a: determineStage结果∈{1,2,3}', () => {
      fc.assert(
        fc.property(fc.boolean(), fc.boolean(), (isImpaired, significantIncrease) => {
          const result = determineStage(isImpaired, significantIncrease)
          expect([1, 2, 3]).toContain(result)
        }),
      )
    })

    it('CP-K1-07b: isImpaired=true → Stage 3', () => {
      fc.assert(
        fc.property(fc.boolean(), (significantIncrease) => {
          const result = determineStage(true, significantIncrease)
          expect(result).toBe(3)
        }),
      )
    })

    it('CP-K1-07c: !isImpaired && significantIncrease → Stage 2', () => {
      const result = determineStage(false, true)
      expect(result).toBe(2)
    })

    it('CP-K1-07d: !isImpaired && !significantIncrease → Stage 1', () => {
      const result = determineStage(false, false)
      expect(result).toBe(1)
    })
  })

  // ═══ CP-K1-08: 账龄合计恒等 ═══
  // **Validates: Requirements 3.5**
  describe('Feature: k1-other-receivables, Property CP-K1-08: 账龄合计恒等', () => {
    it('CP-K1-08: calcSubtotal(agingBuckets) === Σ agingBuckets', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 20 }),
          (buckets) => {
            const result = calcSubtotal(buckets)
            const expected = buckets.reduce((a, b) => a + b, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ CP-K1-09: 占比=单项/合计 ═══
  // **Validates: Requirements 4.3**
  describe('Feature: k1-other-receivables, Property CP-K1-09: 占比=单项/合计', () => {
    it('CP-K1-09: calcProportion(item, total) === item/total (total>0)', () => {
      fc.assert(
        fc.property(
          safeFloat(-1e9, 1e9),
          positiveFloat(0.01, 1e9),
          (item, total) => {
            const result = calcProportion(item, total)
            const expected = item / total
            expect(result).not.toBeNull()
            expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K1-09b: calcProportion(item, 0) === null (total≤0返回null)', () => {
      fc.assert(
        fc.property(safeFloat(), (item) => {
          expect(calcProportion(item, 0)).toBeNull()
        }),
      )
    })
  })
})
