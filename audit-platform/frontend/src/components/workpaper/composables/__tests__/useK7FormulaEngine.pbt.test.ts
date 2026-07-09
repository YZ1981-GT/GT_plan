/**
 * K7 递延收益 — Property-Based Testing (CP-K7-01, CP-K7-02, CP-K7-06)
 *
 * 覆盖 useK7FormulaEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 *
 * Spec: .kiro/specs/k7-deferred-income/design.md → Correctness Properties CP-K7-01~02, CP-K7-06
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../useK7FormulaEngine'

describe('useK7FormulaEngine PBT', () => {
  // 安全浮点生成器（避免 NaN/Infinity，32-bit bounds）
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K7-01: 审定数公式链 ═══
  // **Validates: Requirements 7.1**
  it('Property CP-K7-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, safeFloat, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K7-02: 负债类期末余额 ═══
  // **Validates: Requirements 7.2**
  it('Property CP-K7-02: calcLiabilityEndBalance(b, rec, am) === b + rec - am', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, safeFloat, (b, rec, am) => {
        expect(calcLiabilityEndBalance(b, rec, am)).toBeCloseTo(b + rec - am, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K7-06: 合计行恒等 ═══
  // **Validates: Requirements 7.6**
  it('Property CP-K7-06: calcSubtotal(arr) === arr.reduce((s, v) => s + v, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat, { minLength: 0, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
