/**
 * useK0FormulaEngine PBT — K0-5/K0-6 公式引擎属性测试
 *
 * 5 个 Property（fast-check）：
 * P1: calcBlockTotal — 区块合计 = Σ金额
 * P2: calcCheckRatio — 检查比例（除零→0）
 * P3: calcRowVariance — 行差异 = 账面 - 证据，自身差异=0
 * P4: calcReconcileDiff — 对账差异 = 本方 - 对方，自身差异=0
 * P5: isAbnormal — 异常判定 ⟺ 账面≠证据
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  calcBlockTotal,
  calcCheckRatio,
  calcRowVariance,
  calcReconcileDiff,
  isAbnormal,
  parseNum,
} from '../composables/useK0FormulaEngine'

/** 有限浮点数生成器（排除NaN/Infinity） */
const finiteFloat = fc.float({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })
const positiveFloat = fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true })

describe('useK0FormulaEngine PBT — Property 1: 区块合计公式', () => {
  /**
   * **Validates: Requirements 6.1, 2.7, 3.7**
   *
   * ∀ amounts ∈ ℝ*: calcBlockTotal(amounts) === Σ amounts
   * calcBlockTotal([]) === 0
   */
  it('P1: calcBlockTotal(amounts) === reduce sum, 空数组→0', () => {
    fc.assert(
      fc.property(
        fc.array(finiteFloat, { minLength: 0, maxLength: 50 }),
        (amounts) => {
          const result = calcBlockTotal(amounts)
          const expected = amounts.reduce((sum, v) => sum + parseNum(v), 0)
          // 浮点容差
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P1 边界: calcBlockTotal([]) === 0', () => {
    expect(calcBlockTotal([])).toBe(0)
  })
})

describe('useK0FormulaEngine PBT — Property 2: 检查比例公式', () => {
  /**
   * **Validates: Requirements 6.2, 2.3, 3.3**
   *
   * ∀ checked ∈ ℝ≥0, balance ∈ ℝ:
   *   calcCheckRatio(checked, balance) === (balance > 0 ? checked / balance : 0)
   */
  it('P2: calcCheckRatio — 除零安全 + 正常比例', () => {
    fc.assert(
      fc.property(
        positiveFloat,
        finiteFloat,
        (checked, balance) => {
          const result = calcCheckRatio(checked, balance)
          const b = parseNum(balance)
          if (b <= 0) {
            expect(result).toBe(0)
          } else {
            const expected = parseNum(checked) / b
            expect(result).toBeCloseTo(expected, 8)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P2 边界: 期末余额=0 → 0', () => {
    expect(calcCheckRatio(100, 0)).toBe(0)
    expect(calcCheckRatio(999, -5)).toBe(0)
  })

  it('P2 示例: calcCheckRatio(100, 200) === 0.5', () => {
    expect(calcCheckRatio(100, 200)).toBeCloseTo(0.5, 8)
  })
})

describe('useK0FormulaEngine PBT — Property 3: 行差异公式', () => {
  /**
   * **Validates: Requirements 6.3**
   *
   * ∀ book, evidence ∈ ℝ:
   *   calcRowVariance(book, evidence) === book - evidence
   *   calcRowVariance(v, v) === 0 (零差异恒等)
   */
  it('P3: calcRowVariance(book, evidence) === book - evidence', () => {
    fc.assert(
      fc.property(
        finiteFloat,
        finiteFloat,
        (book, evidence) => {
          const result = calcRowVariance(book, evidence)
          const expected = parseNum(book) - parseNum(evidence)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P3 零差异恒等: calcRowVariance(v, v) === 0', () => {
    fc.assert(
      fc.property(
        finiteFloat,
        (v) => {
          expect(calcRowVariance(v, v)).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })
})

describe('useK0FormulaEngine PBT — Property 4: 对账差异公式', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * ∀ self, other ∈ ℝ:
   *   calcReconcileDiff(self, other) === self - other
   *   calcReconcileDiff(v, v) === 0 (零差异恒等)
   */
  it('P4: calcReconcileDiff(self, other) === self - other', () => {
    fc.assert(
      fc.property(
        finiteFloat,
        finiteFloat,
        (self, other) => {
          const result = calcReconcileDiff(self, other)
          const expected = parseNum(self) - parseNum(other)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P4 零差异恒等: calcReconcileDiff(v, v) === 0', () => {
    fc.assert(
      fc.property(
        finiteFloat,
        (v) => {
          expect(calcReconcileDiff(v, v)).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P4 示例: calcReconcileDiff(100, 80) === 20', () => {
    expect(calcReconcileDiff(100, 80)).toBe(20)
  })
})

describe('useK0FormulaEngine PBT — Property 5: 异常判定', () => {
  /**
   * **Validates: Requirements 6.5, 2.7, 3.7**
   *
   * ∀ book, evidence ∈ ℝ:
   *   isAbnormal(calcRowVariance(book, evidence)) === (book ≠ evidence)
   */
  it('P5: isAbnormal(variance) ⟺ book ≠ evidence', () => {
    fc.assert(
      fc.property(
        finiteFloat,
        finiteFloat,
        (book, evidence) => {
          const variance = calcRowVariance(book, evidence)
          const result = isAbnormal(variance)
          const expected = parseNum(book) !== parseNum(evidence)
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('P5 边界: isAbnormal(0) === false', () => {
    expect(isAbnormal(0)).toBe(false)
  })

  it('P5 边界: isAbnormal(0.01) === true', () => {
    expect(isAbnormal(0.01)).toBe(true)
  })
})
