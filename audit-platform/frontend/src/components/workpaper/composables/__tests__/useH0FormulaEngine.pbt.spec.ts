/**
 * Property-Based Tests — H0-5 替代程序公式引擎 (fast-check)
 *
 * Spec: .kiro/specs/h0-confirmation/
 * Task: 2.1 (P1~P4)
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P4。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBlockTotal,
  calcCheckRatio,
  calcRowVariance,
  isAbnormal,
  parseNum,
} from '../../confirmation/alternativeH05/composables/useH0FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 有限浮点数（排除 NaN/Infinity），模拟实际金额范围 */
const arbAmount = fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true })

/** 金额数组（0~20 个元素，覆盖空数组边界） */
const arbAmounts = fc.array(arbAmount, { minLength: 0, maxLength: 20 })

/** 正数余额（balance > 0），用于 P2 正除数场景 */
const arbPositiveBalance = fc.float({ min: Math.fround(0.01), max: 1e6, noNaN: true, noDefaultInfinity: true })

// ═══════════════════════════════════════════════════════════════════════════════
// Property P1: calcBlockTotal(amounts) === Σ amounts；[] → 0
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: confirmation-alternative-h05, Property P1: 区块合计', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * For any finite number array:
   * - calcBlockTotal(amounts) ≈ Σ amounts (浮点精度内)
   * - calcBlockTotal([]) === 0
   */

  it('P1a: calcBlockTotal(amounts) equals sum of amounts', () => {
    fc.assert(
      fc.property(arbAmounts, (amounts) => {
        const expected = amounts.reduce((s, v) => s + v, 0)
        expect(calcBlockTotal(amounts)).toBeCloseTo(expected, 5)
      }),
    )
  })

  it('P1b: calcBlockTotal([]) returns 0', () => {
    expect(calcBlockTotal([])).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property P2: calcCheckRatio(checked, balance) === balance>0 ? checked/balance : 0
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: confirmation-alternative-h05, Property P2: 检查比例（除零→0）', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * For any checked and balance:
   * - balance ≤ 0 → returns 0
   * - balance > 0 → returns checked / balance
   */

  it('P2a: returns 0 when balance <= 0', () => {
    fc.assert(
      fc.property(
        arbAmount,
        fc.float({ min: -1e6, max: 0, noNaN: true, noDefaultInfinity: true }),
        (checked, balance) => {
          expect(calcCheckRatio(checked, balance)).toBe(0)
        },
      ),
    )
  })

  it('P2b: returns checked / balance when balance > 0', () => {
    fc.assert(
      fc.property(arbAmount, arbPositiveBalance, (checked, balance) => {
        expect(calcCheckRatio(checked, balance)).toBeCloseTo(checked / balance, 10)
      }),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property P3: calcRowVariance(book, evidence) === book − evidence；calcRowVariance(v,v) === 0
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: confirmation-alternative-h05, Property P3: 行差异与零差异恒等', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * For any book and evidence:
   * - calcRowVariance(book, evidence) ≈ book - evidence
   * - calcRowVariance(v, v) === 0 (恒等性)
   */

  it('P3a: calcRowVariance(book, evidence) equals book - evidence', () => {
    fc.assert(
      fc.property(arbAmount, arbAmount, (book, evidence) => {
        expect(calcRowVariance(book, evidence)).toBeCloseTo(book - evidence, 5)
      }),
    )
  })

  it('P3b: calcRowVariance(v, v) === 0 (identity)', () => {
    fc.assert(
      fc.property(arbAmount, (v) => {
        expect(calcRowVariance(v, v)).toBe(0)
      }),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property P4: isAbnormal(calcRowVariance(b,e)) === (b ≠ e)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: confirmation-alternative-h05, Property P4: 异常判定', () => {
  /**
   * **Validates: Requirements 5.4**
   *
   * For any book and evidence:
   * - isAbnormal(calcRowVariance(b, e)) === (b ≠ e)
   * - isAbnormal(0) === false
   * - isAbnormal(non-zero) === true
   */

  it('P4a: isAbnormal(calcRowVariance(b, e)) === (b ≠ e)', () => {
    fc.assert(
      fc.property(arbAmount, arbAmount, (b, e) => {
        const variance = calcRowVariance(b, e)
        expect(isAbnormal(variance)).toBe(b !== e)
      }),
    )
  })

  it('P4b: isAbnormal(0) === false', () => {
    expect(isAbnormal(0)).toBe(false)
  })

  it('P4c: isAbnormal(non-zero) === true', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }).filter(v => v !== 0),
        (v) => {
          expect(isAbnormal(v)).toBe(true)
        },
      ),
    )
  })
})

// ─── parseNum 边界 (辅助函数验证) ────────────────────────────────────────────

describe('parseNum boundary', () => {
  it('maps non-finite/non-number inputs to 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
  })

  it('passes through valid numbers', () => {
    expect(parseNum(42)).toBe(42)
    expect(parseNum(-3.14)).toBeCloseTo(-3.14)
    expect(parseNum(0)).toBe(0)
  })
})
