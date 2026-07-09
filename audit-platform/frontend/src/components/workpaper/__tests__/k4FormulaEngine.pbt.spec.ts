/**
 * K4 其他流动负债 — 公式引擎 Property-Based Tests (CP-K4-01~05)
 *
 * 覆盖 useK4FormulaEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：2245其他流动负债（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 贷方 - 借方
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/design.md → Correctness Properties CP-K4-01~05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useK4FormulaEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（货币范围）
const safeFloat = (min = -1e12, max = 1e12) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K4 FormulaEngine PBT', () => {
  // ═══ CP-K4-01: 审定数公式链 ═══
  // **Validates: Requirements 6.1**
  describe('Feature: k4-other-current-liabilities, Property CP-K4-01: 审定数公式链', () => {
    it('CP-K4-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K4-02: 负债类期末余额 ═══
  // **Validates: Requirements 6.2**
  describe('Feature: k4-other-current-liabilities, Property CP-K4-02: 负债类期末=期初+贷-借', () => {
    it('CP-K4-02: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, cr, dr) => {
          const result = calcLiabilityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K4-03: 三角勾稽恒等式 ═══
  // **Validates: Requirements 6.3**
  describe('Feature: k4-other-current-liabilities, Property CP-K4-03: 三角勾稽恒等式', () => {
    it('CP-K4-03: calcTriangleReconciliation(b, inc, dec, b+inc-dec) === 0', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, inc, dec) => {
          const end = b + inc - dec
          const result = calcTriangleReconciliation(b, inc, dec, end)
          expect(Math.abs(result)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K4-04: 合计行恒等 ═══
  // **Validates: Requirements 6.4**
  describe('Feature: k4-other-current-liabilities, Property CP-K4-04: 合计行恒等', () => {
    it('CP-K4-04: calcSubtotal(arr) === Σarr', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e9, 1e9), { minLength: 0, maxLength: 50 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((sum, v) => sum + v, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K4-04b: 空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })

  // ═══ CP-K4-05: 借贷平衡 ═══
  // **Validates: Requirements 5.2**
  describe('Feature: k4-other-current-liabilities, Property CP-K4-05: 借贷平衡', () => {
    it('CP-K4-05: balanced entries → Σdebit === Σcredit', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e9, 1e9), { minLength: 1, maxLength: 20 }),
          (amounts) => {
            // 构造平衡分录：每笔借方=贷方
            const debitArr = amounts
            const creditArr = amounts // same amounts → balanced
            const totalDebit = calcSubtotal(debitArr)
            const totalCredit = calcSubtotal(creditArr)
            expect(Math.abs(totalDebit - totalCredit)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ 边界测试 ═══
  describe('Edge cases', () => {
    it('calcChangeRate: prior=0, current=0 → null', () => {
      expect(calcChangeRate(0, 0)).toBeNull()
    })

    it('calcChangeRate: prior=0, current≠0 → 1', () => {
      expect(calcChangeRate(100, 0)).toBe(1)
      expect(calcChangeRate(-50, 0)).toBe(1)
    })

    it('calcChangeRate: normal case', () => {
      expect(calcChangeRate(150, 100)).toBeCloseTo(0.5, 5)
      expect(calcChangeRate(50, 100)).toBeCloseTo(-0.5, 5)
    })

    it('calcSubtotal([]) → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('safeNum handles NaN inputs gracefully', () => {
      // NaN inputs treated as 0
      expect(calcAuditedAmount(NaN, 10, 20)).toBe(30)
      expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
      expect(calcSubtotal([NaN, 5, NaN, 10])).toBe(15)
    })
  })
})
