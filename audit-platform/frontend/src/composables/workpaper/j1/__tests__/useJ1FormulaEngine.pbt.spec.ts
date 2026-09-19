/**
 * Property-Based Tests — J1 应付职工薪酬 公式引擎 + 薪酬测算引擎
 *
 * 覆盖 CP-J1-01 ~ CP-J1-08 共 8 个性质测试
 * 科目2211应付职工薪酬（贷方/负债类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/j1-employee-compensation/ Tasks 2.3 ~ 2.10
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcMonthlyTotal,
  calcSubtotal,
  calcChangeRate,
  validateAllocationClosure,
} from '../useJ1FormulaEngine'
import {
  calcSalaryEstimate,
  calcInsuranceEstimate,
} from '../useJ1SalaryCalc'

// ═══════════════════════════════════════════════════════════════════
// CP-J1-01: 审定数公式链
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-01: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.2**
   *
   * 审定数 = 未审数 + AJE + RJE，对任意三元组成立
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-02: 负债类贷方期末余额
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-02: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * 负债类期末 = 期初 + 贷方(增加) - 借方(减少)
   * ⚠️ 与资产类(期初+借-贷)方向相反！
   */
  it('calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, credit, debit) => {
          expect(calcLiabilityEndBalance(begin, credit, debit)).toBeCloseTo(begin + credit - debit, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-03: 月度合计=SUM(1月~12月)
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-03: 月度合计=SUM(1月~12月)', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * 月度合计严格等于12个月值之和
   */
  it('calcMonthlyTotal(months) === months.reduce((a,b)=>a+b,0)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 12, maxLength: 12 },
        ),
        (months) => {
          const expected = months.reduce((a, b) => a + b, 0)
          expect(calcMonthlyTotal(months)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-04: 工资测算=人数×均薪×月数
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-04: 工资测算公式', () => {
  /**
   * **Validates: Requirements 4.6**
   *
   * 工资测算 = 人数 × 月均薪资 × 月数
   * 生成器约束：headcount∈[1,10000], avgSalary∈[1000,100000], months∈[1,12]
   */
  it('calcSalaryEstimate(h, s, m) === h × s × m', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        fc.double({ min: 1000, max: 100000, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 12 }),
        (headcount, avgSalary, months) => {
          expect(calcSalaryEstimate(headcount, avgSalary, months))
            .toBeCloseTo(headcount * avgSalary * months, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-05: 社保测算=基数×比例×月数
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-05: 社保测算公式', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * 社保测算 = 缴费基数 × 缴纳比例 × 月数
   * 生成器约束：base>0, rate∈(0,0.5), months∈[1,12]
   */
  it('calcInsuranceEstimate(base, rate, m) === base × rate × m', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1000, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.5, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 12 }),
        (base, rate, months) => {
          expect(calcInsuranceEstimate(base, rate, months))
            .toBeCloseTo(base * rate * months, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-06: 分配闭合恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-06: 分配闭合恒等', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * 分配闭合 = Σ各费用科目分配 === 薪酬总额
   * 生成器：N个分配项(>0), total=Σ分配项 → isValid === true
   */
  it('validateAllocationClosure(items, Σitems).isValid === true', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 0.01, max: 1e7, noNaN: true, noDefaultInfinity: true }),
          { minLength: 2, maxLength: 8 },
        ),
        (items) => {
          const total = items.reduce((s, v) => s + v, 0)
          const result = validateAllocationClosure(items, total)
          expect(result.isValid).toBe(true)
          expect(Math.abs(result.difference)).toBeLessThan(0.01)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('validateAllocationClosure detects imbalance when total mismatches', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          { minLength: 2, maxLength: 8 },
        ),
        fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (items, offset) => {
          const total = items.reduce((s, v) => s + v, 0)
          // 故意制造不平衡（offset > 0.01保证）
          const wrongTotal = total + offset
          const result = validateAllocationClosure(items, wrongTotal)
          if (offset >= 0.01) {
            expect(result.isValid).toBe(false)
          }
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-07: 合计行恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-07: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.5**
   *
   * calcSubtotal(arr) === Σarr
   * 对任意长度数组成立
   */
  it('calcSubtotal(arr) === sum of all elements', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 0, maxLength: 20 },
        ),
        (arr) => {
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// CP-J1-08: 变动率公式正确性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: j1-employee-compensation, Property CP-J1-08: 变动率公式正确性', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * 变动率 = (本期-上期)/上期 × 100
   * 生成器约束：prior > 0（避免除零特殊处理影响断言）
   */
  it('calcChangeRate(c, p) === (c-p)/p × 100 when p > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (current, prior) => {
          const expected = ((current - prior) / prior) * 100
          expect(calcChangeRate(current, prior)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('calcChangeRate returns 0 when both current=0 and prior=0', () => {
    expect(calcChangeRate(0, 0)).toBe(0)
  })

  it('calcChangeRate returns 100 when prior=0 and current!=0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (current) => {
          expect(calcChangeRate(current, 0)).toBe(100)
        },
      ),
      { numRuns: 200 },
    )
  })
})
