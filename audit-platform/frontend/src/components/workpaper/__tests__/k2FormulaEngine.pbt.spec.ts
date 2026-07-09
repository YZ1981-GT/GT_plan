/**
 * K2 其他流动资产 — 公式引擎 + 摊销引擎 Property-Based Tests (CP-K2-01~06)
 *
 * 覆盖 useK2FormulaEngine + useK2AmortizationEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：1231其他流动资产（借方/资产类）
 *
 * Spec: .kiro/specs/k2-other-current-assets/design.md → Correctness Properties CP-K2-01~06
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
} from '../composables/useK2FormulaEngine'
import {
  calcStraightLineAmort,
  calcProgressAmort,
  calcAmortizedBalance,
} from '../composables/useK2AmortizationEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（货币范围）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0, max = 1e9) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K2 FormulaEngine + AmortizationEngine PBT', () => {
  // ═══ CP-K2-01: 审定数公式链 ═══
  // **Validates: Requirements 2.2**
  describe('Feature: k2-other-current-assets, Property CP-K2-01: 审定数公式链', () => {
    it('CP-K2-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K2-02: 资产类期末余额 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: k2-other-current-assets, Property CP-K2-02: 期末=期初+借-贷', () => {
    it('CP-K2-02: calcAssetEndBalance(b, dr, cr) === b + dr - cr', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, dr, cr) => {
          const result = calcAssetEndBalance(b, dr, cr)
          const expected = b + dr - cr
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K2-03: 直线法摊销 ═══
  // **Validates: Requirements 5.2**
  describe('Feature: k2-other-current-assets, Property CP-K2-03: 直线法摊销', () => {
    it('CP-K2-03: calcStraightLineAmort(cost, tp, cp) === cost / tp * cp', () => {
      fc.assert(
        fc.property(
          positiveFloat(0, 1e9),
          fc.integer({ min: 1, max: 1200 }),
          fc.integer({ min: 0, max: 1200 }),
          (cost, tp, cp) => {
            const result = calcStraightLineAmort(cost, tp, cp)
            const expected = (cost / tp) * cp
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K2-03b: totalPeriods=0 → 返回0（兜底）', () => {
      fc.assert(
        fc.property(positiveFloat(0, 1e9), fc.integer({ min: 0, max: 1200 }), (cost, cp) => {
          const result = calcStraightLineAmort(cost, 0, cp)
          expect(result).toBe(0)
        }),
      )
    })
  })

  // ═══ CP-K2-04: 进度法摊销 ═══
  // **Validates: Requirements 5.3**
  describe('Feature: k2-other-current-assets, Property CP-K2-04: 进度法摊销', () => {
    it('CP-K2-04: calcProgressAmort(cost, cur, prior) === cost * (cur - prior)', () => {
      fc.assert(
        fc.property(
          positiveFloat(0, 1e9),
          fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          (cost, a, b) => {
            // 确保 cur >= prior
            const cur = Math.max(a, b)
            const prior = Math.min(a, b)
            const result = calcProgressAmort(cost, cur, prior)
            const expected = cost * (cur - prior)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K2-04b: currentProgress < priorProgress → 返回0（进度回退兜底）', () => {
      fc.assert(
        fc.property(
          positiveFloat(0, 1e9),
          fc.double({ min: 0, max: 0.49, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: 0.5, max: 1, noNaN: true, noDefaultInfinity: true }),
          (cost, cur, prior) => {
            // cur < prior 一定成立
            const result = calcProgressAmort(cost, cur, prior)
            expect(result).toBe(0)
          },
        ),
      )
    })
  })

  // ═══ CP-K2-05: 摊余成本 ═══
  // **Validates: Requirements 5.4**
  describe('Feature: k2-other-current-assets, Property CP-K2-05: 摊余成本', () => {
    it('CP-K2-05: calcAmortizedBalance(cost, acc) === cost - acc', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (cost, acc) => {
          const result = calcAmortizedBalance(cost, acc)
          const expected = cost - acc
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K2-06: 合计行恒等 ═══
  // **Validates: Requirements 8.6**
  describe('Feature: k2-other-current-assets, Property CP-K2-06: 合计行恒等', () => {
    it('CP-K2-06: calcSubtotal(arr) === Σarr', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 20 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((sum, v) => sum + v, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K2-06b: 空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })
})
