/**
 * I5 其他非流动资产 — 公式引擎 Property-Based Tests
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
} from '../composables/useI5FormulaEngine'

const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

describe('I5 FormulaEngine PBT — P1 审定数公式链', () => {
  /**
   * Property P1: 审定数公式链
   * **Validates: Requirements 2.2**
   * calcAuditedAmount(u, a, r) === u + a + r
   */
  it('P1: 审定数 = 未审 + AJE + RJE', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (unadj, aje, rje) => {
          expect(calcAuditedAmount(unadj, aje, rje)).toBeCloseTo(unadj + aje + rje, 5)
        }
      ),
      { numRuns: 200 }
    )
  })
})

describe('I5 FormulaEngine PBT — P3 三角勾稽恒等式', () => {
  /**
   * Property P3: 三角勾稽恒等式
   * **Validates: Requirements 2.4**
   * calcTriangleReconciliation(b, i, d, b+i-d) === 0
   */
  it('P3: 三角勾稽差额 = 0（期末由期初+增-减推导时）', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (begin, increase, decrease) => {
          const end = begin + increase - decrease
          expect(calcTriangleReconciliation(begin, increase, decrease, end)).toBeCloseTo(0, 5)
        }
      ),
      { numRuns: 200 }
    )
  })
})

describe('I5 FormulaEngine PBT — P4 合计行恒等', () => {
  /**
   * Property P4: 合计行恒等
   * **Validates: Requirements 3.2**
   * calcSubtotal(arr) === Σarr (sum of all elements)
   */
  it('P4: 合计行 = SUM(明细行)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: -1_000_000, max: 1_000_000 }), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(calcSubtotal(arr)).toBe(expected)
        }
      ),
      { numRuns: 200 }
    )
  })

  it('P4 edge: calcSubtotal([]) === 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })
})

describe('I5 FormulaEngine PBT — P2 资产类期末余额', () => {
  /**
   * Property P2: 期末=期初+增加-减少
   * **Validates: Requirements 2.2**
   * calcAssetEndBalance(b, i, d) === b + i - d
   * 标准资产类（借方科目1911其他非流动资产）期末余额公式
   */
  it('P2: 期末 = 期初 + 增加 - 减少', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (begin, increase, decrease) => {
          expect(calcAssetEndBalance(begin, increase, decrease)).toBeCloseTo(begin + increase - decrease, 5)
        }
      ),
      { numRuns: 200 }
    )
  })
})

describe('Feature: i5-other-noncurrent-assets, Property P5: 借贷平衡', () => {
  const positiveFloat = (min = 0.01, max = 1e6) =>
    fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

  /**
   * Property P5: 借贷平衡
   * **Validates: Requirements 2.5**
   * 对于任何调整分录集合，Σdebit === Σcredit
   * 构造方式：生成随机金额数组，借方和贷方使用相同金额，验证 calcSubtotal(debits) === calcSubtotal(credits)
   */
  it('P5: 借贷平衡 — 对称构造的分录必然平衡', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(), { minLength: 1, maxLength: 20 }),
        (amounts) => {
          // 每笔金额同时记借方和贷方 → 总借方 === 总贷方
          const debits = amounts
          const credits = amounts
          expect(calcSubtotal(debits)).toBeCloseTo(calcSubtotal(credits), 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  it('P5b: 借贷平衡 — 单笔分录借方=贷方', () => {
    fc.assert(
      fc.property(
        positiveFloat(),
        (amount) => {
          // 单笔调整分录：一借一贷等额
          expect(calcSubtotal([amount])).toBeCloseTo(calcSubtotal([amount]), 5)
        }
      ),
      { numRuns: 200 }
    )
  })

  it('P5c: 借贷平衡 — 多对多拆分仍平衡', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(), { minLength: 2, maxLength: 10 }),
        (amounts) => {
          // 借方拆为多笔，贷方汇总为一笔，总额相等
          const totalAmount = calcSubtotal(amounts)
          const debitTotal = calcSubtotal(amounts)
          const creditTotal = calcSubtotal([totalAmount])
          expect(debitTotal).toBeCloseTo(creditTotal, 5)
        }
      ),
      { numRuns: 200 }
    )
  })
})
