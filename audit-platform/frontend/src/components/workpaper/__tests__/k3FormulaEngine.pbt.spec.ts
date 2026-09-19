/**
 * K3 其他应付款 — 公式引擎 Property-Based Tests (CP-K3-01~06)
 *
 * 覆盖 useK3FormulaEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：2241其他应付款（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 贷方 - 借方
 *
 * Spec: .kiro/specs/k3-other-payables/design.md → Correctness Properties CP-K3-01~06
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcProportion,
  calcSubtotal,
} from '../composables/useK3FormulaEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（货币范围）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 1e-6, max = 1e9) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K3 FormulaEngine PBT', () => {
  // ═══ CP-K3-01: 审定数公式链 ═══
  // **Validates: Requirements 9.1**
  describe('Feature: k3-other-payables, Property CP-K3-01: 审定数公式链', () => {
    it('CP-K3-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K3-02: 负债类期末余额 ═══
  // **Validates: Requirements 9.2**
  describe('Feature: k3-other-payables, Property CP-K3-02: 负债类期末=期初+贷-借', () => {
    it('CP-K3-02: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, cr, dr) => {
          const result = calcLiabilityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K3-03: 三角勾稽恒等式 ═══
  // **Validates: Requirements 9.3**
  describe('Feature: k3-other-payables, Property CP-K3-03: 三角勾稽恒等式', () => {
    it('CP-K3-03: calcTriangleReconciliation(b, inc, dec, b+inc-dec) === 0', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, inc, dec) => {
          const end = b + inc - dec
          const result = calcTriangleReconciliation(b, inc, dec, end)
          expect(Math.abs(result)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K3-04: 账龄合计恒等 ═══
  // **Validates: Requirements 9.5**
  describe('Feature: k3-other-payables, Property CP-K3-04: 账龄合计恒等', () => {
    it('CP-K3-04: calcSubtotal(agingBuckets) === ΣagingBuckets', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 6 }),
          (agingBuckets) => {
            const result = calcSubtotal(agingBuckets)
            const expected = agingBuckets.reduce((sum, v) => sum + v, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K3-04b: 空账龄 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })

  // ═══ CP-K3-05: 占比公式 ═══
  // **Validates: Requirements 9.4**
  describe('Feature: k3-other-payables, Property CP-K3-05: 占比=单项/合计', () => {
    it('CP-K3-05: calcProportion(item, total) === item/total (total>0)', () => {
      fc.assert(
        fc.property(safeFloat(), positiveFloat(), (item, total) => {
          const result = calcProportion(item, total)
          const expected = item / total
          expect(result).not.toBeNull()
          expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
        }),
      )
    })

    it('CP-K3-05b: total=0 → null（避免除零）', () => {
      fc.assert(
        fc.property(safeFloat(), (item) => {
          const result = calcProportion(item, 0)
          expect(result).toBeNull()
        }),
      )
    })
  })

  // ═══ CP-K3-06: 合计行恒等 ═══
  // **Validates: Requirements 9.5**
  describe('Feature: k3-other-payables, Property CP-K3-06: 合计行恒等', () => {
    it('CP-K3-06: calcSubtotal(arr) === Σarr', () => {
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

    it('CP-K3-06b: 空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })
})
