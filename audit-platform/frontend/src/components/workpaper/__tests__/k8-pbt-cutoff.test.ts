/**
 * K8 销售费用 — 合计行恒等 + 跨期判断确定性 Property-Based Tests (CP-K8-06, CP-K8-07)
 *
 * CP-K8-06: calcSubtotal(arr) === Σarr（合计行恒等）
 * CP-K8-07: sourceDate/bookDate分属不同会计期间 → isCrossPeriod=true（跨期判断确定性）
 *
 * 使用 fast-check 验证数学正确性与业务逻辑确定性。
 * Spec: .kiro/specs/k8-selling-expenses/design.md → Correctness Properties CP-K8-06~07
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useK8FormulaEngine'
import { isCrossPeriod } from '../composables/useK8CutoffEngine'

describe('K8 PBT: 合计行恒等 + 跨期判断确定性', () => {
  // ═══ CP-K8-06: 合计行恒等 ═══
  // **Validates: Requirements 9.6**
  describe('Feature: k8-selling-expenses, Property CP-K8-06: 合计行恒等', () => {
    const safeFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: -1e6,
      max: 1e6,
    })

    it('CP-K8-06: calcSubtotal(arr) === arr.reduce((s,v) => s + v, 0)', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat, { maxLength: 20 }),
          (arr) => {
            const expected = arr.reduce((s, v) => s + v, 0)
            expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 200 },
      )
    })
  })

  // ═══ CP-K8-07: 跨期判断确定性 ═══
  // **Validates: Requirements 5.4, 9.7**
  describe('Feature: k8-selling-expenses, Property CP-K8-07: 跨期判断确定性', () => {
    // --- 确定性示例测试 ---
    it('CP-K8-07 示例: 同月 → isCrossPeriod = false', () => {
      expect(isCrossPeriod('2025-12-28', '2025-12-30', '2025-12-31')).toBe(false)
    })

    it('CP-K8-07 示例: 不同月(source跨月) → isCrossPeriod = true', () => {
      expect(isCrossPeriod('2026-01-02', '2025-12-30', '2025-12-31')).toBe(true)
    })

    it('CP-K8-07 示例: 不同年(book跨年) → isCrossPeriod = true', () => {
      expect(isCrossPeriod('2025-12-15', '2026-01-03', '2025-12-31')).toBe(true)
    })

    // --- fast-check Property: 两日期不同 year+month → isCrossPeriod = true ---
    it('CP-K8-07 Property: 两日期分属不同 year+month → isCrossPeriod = true', () => {
      const yearArb = fc.integer({ min: 2020, max: 2026 })
      const monthArb = fc.integer({ min: 1, max: 12 })
      const dayArb = fc.integer({ min: 1, max: 28 })

      fc.assert(
        fc.property(
          yearArb, monthArb, dayArb,
          yearArb, monthArb, dayArb,
          (y1, m1, d1, y2, m2, d2) => {
            // 前置条件：确保两日期不在同一 year+month
            fc.pre(y1 !== y2 || m1 !== m2)

            const sourceDate = `${y1}-${String(m1).padStart(2, '0')}-${String(d1).padStart(2, '0')}`
            const bookDate = `${y2}-${String(m2).padStart(2, '0')}-${String(d2).padStart(2, '0')}`
            const periodEnd = '2025-12-31'

            expect(isCrossPeriod(sourceDate, bookDate, periodEnd)).toBe(true)
          },
        ),
        { numRuns: 200 },
      )
    })
  })
})
