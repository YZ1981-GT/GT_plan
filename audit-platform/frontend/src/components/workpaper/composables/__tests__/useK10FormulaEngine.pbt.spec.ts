/**
 * K10 其他收益 — Property-Based Testing (CP-K10-01 ~ CP-K10-06)
 *
 * 覆盖 useK10FormulaEngine + useK10GrantReconcileEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 *
 * Spec: .kiro/specs/k10-other-income/design.md → Correctness Properties CP-K10-01~06
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcYoYChange,
  calcSubtotal,
} from '../useK10FormulaEngine'
import {
  calcTotalRecognized,
  isConsistentWithK7,
} from '../useK10GrantReconcileEngine'

describe('useK10FormulaEngine PBT', () => {
  // 安全浮点生成器（避免 NaN/Infinity，32-bit bounds）
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K10-01: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  it('Property CP-K10-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, safeFloat, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 5 },
    )
  })

  // ═══ CP-K10-02: 损益类发生额（贷-借） ═══
  // **Validates: Requirements 2.4**
  it('Property CP-K10-02: calcIncomeStatementOccurrence(cr, dr) === cr - dr', () => {
    // 生成器：creditOcc≥0, debitOcc≥0
    const posFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e9),
    })

    fc.assert(
      fc.property(posFloat, posFloat, (cr, dr) => {
        expect(calcIncomeStatementOccurrence(cr, dr)).toBeCloseTo(cr - dr, 5)
      }),
      { numRuns: 5 },
    )
  })
})

describe('useK10GrantReconcileEngine PBT', () => {
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K10-03: 合计计入 ═══
  // **Validates: Requirements 4.2**
  it('Property CP-K10-03: calcTotalRecognized(direct, deferred) === direct + deferred', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, (direct, deferred) => {
        expect(calcTotalRecognized(direct, deferred)).toBeCloseTo(direct + deferred, 5)
      }),
      { numRuns: 5 },
    )
  })

  // ═══ CP-K10-04: 与K7一致性判断 ═══
  // **Validates: Requirements 4.3**
  it('Property CP-K10-04: isConsistentWithK7(a, b) === (Math.abs(a - b) < 0.01)', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, (a, b) => {
        const expected = Math.abs(a - b) < 0.01
        expect(isConsistentWithK7(a, b)).toBe(expected)
      }),
      { numRuns: 5 },
    )
  })
})

describe('useK10FormulaEngine PBT (continued)', () => {
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K10-05: 同比变动率 ═══
  // **Validates: Requirements 7.6**
  it('Property CP-K10-05: calcYoYChange(cur, prior) === (cur - prior) / prior', () => {
    // 生成器：current∈R, prior≠0
    const nonZeroFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: Math.fround(-1e9),
      max: Math.fround(1e9),
    }).filter((v) => Math.abs(v) > 1e-6)

    fc.assert(
      fc.property(safeFloat, nonZeroFloat, (cur, prior) => {
        const actual = calcYoYChange(cur, prior)
        const expected = (cur - prior) / prior
        expect(actual).not.toBeNull()
        expect(actual!).toBeCloseTo(expected, 4)
      }),
      { numRuns: 5 },
    )
  })

  // ═══ CP-K10-06: 合计行恒等 ═══
  // **Validates: Requirements 7.7**
  it('Property CP-K10-06: calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat, { minLength: 0, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 5 },
    )
  })
})
