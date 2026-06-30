/**
 * useD7FormulaEngine Property-Based Tests
 *
 * 使用 fast-check 验证 D7 合同负债公式引擎的核心 correctness properties。
 * numRuns: 100，覆盖 Property 1/2/3/6/9/16/17。
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Tasks: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcCreditEndBalance,
  calcAuditedAmount,
  calcContractLiabilityTotal,
  calcSubtotal,
  isChangeRateExceeding,
  calcChangeAmount,
  calcChangeRate,
} from '../composables/useD7FormulaEngine'

// ─── Shared generator config ────────────────────────────────────────────────

const finiteFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min, max, noNaN: true, noDefaultInfinity: true })

// ─── Property 1: 贷方科目期末余额公式 ───────────────────────────────────────

describe('Property 1: 贷方科目期末余额公式', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 1: 贷方科目期末余额公式**
   *
   * For any 期初审定数(opening)、贷方发生额(credit)和借方发生额(debit)，
   * calcCreditEndBalance(opening, credit, debit) === opening + credit - debit
   *
   * **Validates: Requirements 1.4, 5.4, 11.3**
   */
  it('期末余额 = 期初 + 贷方发生 - 借方发生（贷方科目：贷增借减）', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(), finiteFloat(),
        (opening, credit, debit) => {
          const result = calcCreditEndBalance(opening, credit, debit)
          const expected = opening + credit - debit
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 2: 审定数 = 未审 + AJE + RJE ─────────────────────────────────

describe('Property 2: 审定数 = 未审 + AJE + RJE', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 2: 审定数 = 未审 + AJE + RJE**
   *
   * For any 三元组 (未审数, AJE净额, RJE净额)，
   * calcAuditedAmount(u, a, r) === u + a + r
   *
   * **Validates: Requirements 1.4, 2.3**
   */
  it('审定数 = 未审数 + AJE + RJE', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(), finiteFloat(),
        (unadjusted, aje, rje) => {
          const result = calcAuditedAmount(unadjusted, aje, rje)
          const expected = unadjusted + aje + rje
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 3: 合同负债合计 = 小计 - 非流动负债扣减 ───────────────────────

describe('Property 3: 合同负债合计 = 小计 - 非流动负债扣减', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 3: 合同负债合计 = 小计 - 非流动负债扣减**
   *
   * For any (小计, 非流动负债扣减额) 对，
   * calcContractLiabilityTotal(subtotal, deduction) === subtotal - deduction
   *
   * **Validates: Requirements 2.6**
   */
  it('合同负债合计 = 小计 - 计入其他非流动负债的合同负债', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(),
        (subtotal, deduction) => {
          const result = calcContractLiabilityTotal(subtotal, deduction)
          const expected = subtotal - deduction
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 6: 合计行 = SUM(明细行) ───────────────────────────────────────

describe('Property 6: 合计行 = SUM(明细行)', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 6: 合计行 = SUM(明细行)**
   *
   * For any 数值数组，calcSubtotal(arr) === arr.reduce((a,b) => a+b, 0)
   *
   * **Validates: Requirements 2.5, 5.5, 10.4, 11.6**
   */
  it('合计行 = 所有明细行之和', () => {
    fc.assert(
      fc.property(
        fc.array(finiteFloat(), { minLength: 1, maxLength: 30 }),
        (values) => {
          const result = calcSubtotal(values)
          const expected = values.reduce((a, b) => a + b, 0)
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 9: 变动率阈值高亮判定 ─────────────────────────────────────────

describe('Property 9: 变动率阈值高亮判定', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 9: 变动率阈值高亮判定**
   *
   * For any 变动率数值 r，isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)
   * 对于空串或'N/A'应返回 false。
   *
   * **Validates: Requirements 2.7**
   */
  it('数值型变动率：|r| > 0.3 时返回 true', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -10, max: 10, noNaN: true, noDefaultInfinity: true }),
        (rate) => {
          const result = isChangeRateExceeding(rate, 0.3)
          const expected = Math.abs(rate) > 0.3
          expect(result).toBe(expected)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('空串 → false', () => {
    expect(isChangeRateExceeding('', 0.3)).toBe(false)
  })

  it('N/A → false', () => {
    expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
  })
})

// ─── Property 16: 变动额与变动率计算 ────────────────────────────────────────

describe('Property 16: 变动额与变动率计算', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 16: 变动额与变动率计算**
   *
   * For any (期初审定prior, 期末审定current) 对：
   * - 变动额 = current - prior
   * - 变动率：prior=0 且 current=0 → ''；prior=0 且 current≠0 → 'N/A'；否则 → (current-prior)/prior
   *
   * **Validates: Requirements 2.4**
   */
  it('变动额 = current - prior', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(),
        (prior, current) => {
          const result = calcChangeAmount(prior, current)
          const expected = current - prior
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('变动率符合期初=0规则', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(),
        (prior, current) => {
          const rate = calcChangeRate(prior, current)

          if (prior === 0 && current === 0) {
            expect(rate).toBe('')
          } else if (prior === 0) {
            expect(rate).toBe('N/A')
          } else {
            const expectedRate = (current - prior) / prior
            expect(typeof rate).toBe('number')
            expect(Math.abs((rate as number) - expectedRate)).toBeLessThan(1e-6)
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 17: 变动率特殊情况边界 ────────────────────────────────────────

describe('Property 17: 变动率特殊情况边界', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 17: 变动率特殊情况边界**
   *
   * 当期初为0时不得产生除零错误：
   * - 期初=0且期末=0 → ''
   * - 期初=0且期末≠0 → 'N/A'
   * - isChangeRateExceeding 对非数值类型返回 false
   *
   * **Validates: Requirements 2.4, 2.7**
   */
  it('期初=0且期末=0 → 空串', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 0, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 0, noNaN: true, noDefaultInfinity: true }),
        (prior, current) => {
          // prior 和 current 都是 0（生成器约束）
          const rate = calcChangeRate(prior, current)
          expect(rate).toBe('')
        }
      ),
      { numRuns: 100 }
    )
  })

  it('期初=0且期末≠0 → N/A', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 0, noNaN: true, noDefaultInfinity: true }),
        finiteFloat().filter(v => v !== 0),
        (prior, current) => {
          const rate = calcChangeRate(prior, current)
          expect(rate).toBe('N/A')
        }
      ),
      { numRuns: 100 }
    )
  })

  it('isChangeRateExceeding 对非数值（空串/N/A）返回 false', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 10, noNaN: true, noDefaultInfinity: true }),
        (threshold) => {
          expect(isChangeRateExceeding('', threshold)).toBe(false)
          expect(isChangeRateExceeding('N/A', threshold)).toBe(false)
        }
      ),
      { numRuns: 100 }
    )
  })
})
