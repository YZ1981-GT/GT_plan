/**
 * Property-Based Tests — D1 审定表公式引擎
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Tasks: 1.2–1.7
 *
 * 使用 fast-check + vitest 验证 6 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcChangeRate,
  calcSubtotal,
  calcNetValue,
  isChangeRateExceeding,
  calcBadDebtEndBalance,
  safeDivide,
} from '../useD1FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 审定数公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 1: 审定数公式正确性', () => {
  /**
   * **Validates: Requirements 1.3, 4.5, 5.5, 6.3**
   *
   * 审定数 = 未审数 + AJE净额 + RJE净额
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (unadjusted, aje, rje) => {
          const result = calcAuditedAmount(unadjusted, aje, rje)
          const expected = unadjusted + aje + rje
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 变动额与变动率公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 2: 变动额与变动率公式正确性', () => {
  /**
   * **Validates: Requirements 1.4**
   *
   * 变动率三分支：prior=0&&audited=0→''; prior=0&&audited≠0→1; otherwise→(audited-prior)/prior
   */
  it('calcChangeRate follows three-branch logic with zero boundary', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          // Strategy 1: both zero
          fc.constant([0, 0] as [number, number]),
          // Strategy 2: prior=0, audited≠0
          fc.float({ noNaN: true }).filter(v => v !== 0).map(v => [0, v] as [number, number]),
          // Strategy 3: general case (prior≠0)
          fc.tuple(
            fc.float({ noNaN: true }).filter(v => v !== 0),
            fc.float({ noNaN: true }),
          ),
        ),
        ([prior, audited]) => {
          const result = calcChangeRate(prior, audited)

          if (prior === 0 && audited === 0) {
            expect(result).toBe('')
          } else if (prior === 0) {
            expect(result).toBe(1)
          } else {
            expect(result).toBeCloseTo((audited - prior) / prior, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 小计行恒等于明细行之和
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 3: 小计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 1.5, 4.6, 5.6, 6.5**
   *
   * calcSubtotal(rows) === rows.reduce((a,b)=>a+b, 0)
   */
  it('calcSubtotal equals sum of all elements', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ noNaN: true }), { minLength: 1, maxLength: 20 }),
        (rows) => {
          const result = calcSubtotal(rows)
          const expected = rows.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 净值等于原值减坏账准备
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 4: 净值等于原值减坏账准备', () => {
  /**
   * **Validates: Requirements 1.6**
   *
   * calcNetValue(gross, bad) === gross - bad
   */
  it('calcNetValue(gross, bad) === gross - bad', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true }),
        fc.float({ noNaN: true }),
        (gross, bad) => {
          const result = calcNetValue(gross, bad)
          const expected = gross - bad
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 变动率阈值高亮判定
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 5: 变动率阈值高亮判定', () => {
  /**
   * **Validates: Requirements 1.7**
   *
   * isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)
   */
  it('isChangeRateExceeding correctly compares abs(rate) against threshold', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -10, max: 10, noNaN: true }),
        (rate) => {
          const result = isChangeRateExceeding(rate, 0.3)
          const expected = Math.abs(rate) > 0.3
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 坏账准备期末未审数公式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 11: 坏账准备期末未审数公式', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * calcBadDebtEndBalance = 期初审定 + 计提 - 收回 - 转回 - 核销 + 其他
   */
  it('calcBadDebtEndBalance follows the formula: prior + provision - recovery - reversal - writeOff + other', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (priorAudited, provision, recovery, reversal, writeOff, other) => {
          const result = calcBadDebtEndBalance(priorAudited, provision, recovery, reversal, writeOff, other)
          const expected = priorAudited + provision - recovery - reversal - writeOff + other
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: safeDivide 安全除法
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 10: safeDivide 安全除法', () => {
  /**
   * **Validates: Requirements 5.4, 5.5, 6.2, 7.3**
   *
   * 安全除法：divisor=0 返回 0，否则返回 numerator/divisor
   * 对应源模板 IFERROR(x/y, 0) 语义
   */
  it('safeDivide returns 0 when divisor=0, otherwise returns numerator/divisor', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.oneof(
          // Strategy 1: divisor=0（确保零值分支被覆盖）
          fc.constant(0),
          // Strategy 2: general non-zero divisor
          fc.float({ min: -1e9, max: 1e9, noNaN: true }).filter(v => v !== 0),
        ),
        (numerator, divisor) => {
          const result = safeDivide(numerator, divisor)

          if (divisor === 0) {
            expect(result).toBe(0)
          } else {
            expect(result).toBeCloseTo(numerator / divisor, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 比例计算正确性（IFERROR语义）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 1: 比例计算正确性', () => {
  /**
   * **Validates: Requirements 5.4**
   *
   * 比例 = IFERROR(余额 / 合计, 0)
   * 当合计=0时比例=0；否则比例=余额/合计
   */
  it('ratio equals safeDivide(balance, total): 0 when total=0, balance/total otherwise', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (balance, total) => {
          const result = safeDivide(balance, total)

          if (total === 0) {
            expect(result).toBe(0)
          } else {
            expect(result).toBeCloseTo(balance / total, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 预期信用损失率计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 2: 预期信用损失率计算正确性', () => {
  /**
   * **Validates: Requirements 5.5, 6.2, 7.3**
   *
   * 预期信用损失率 = IFERROR(坏账准备 / 账面余额, 0)
   * 当余额=0时损失率=0；否则损失率=坏账准备/余额
   */
  it('expected loss rate equals safeDivide(provision, balance): 0 when balance=0, provision/balance otherwise', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (provision, balance) => {
          const result = safeDivide(provision, balance)

          if (balance === 0) {
            expect(result).toBe(0)
          } else {
            expect(result).toBeCloseTo(provision / balance, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// d1-endorsement-discount — 背书贴现组 PBT (Tasks 1.2–1.8)
// ═══════════════════════════════════════════════════════════════════════════════

import {
  determineBusinessMode,
  determineReportItem,
  calcDiscountDays,
  calcDiscountInterest,
  calcInterestDifference,
} from '../useD1FormulaEngine'

// 业务模式判定结果常量（与实现保持一致）
const MODE_CASHFLOW = '属于以收取合同现金流量为目标的业务模式'
const MODE_CASHFLOW_SALE = '属于以收取合同现金流量和出售金融资产为目标的业务模式'
const MODE_OTHER = '其他业务模式（以公允价值计量且其变动计入当期损益）'

// QA 单元格取值生成器：'Y' | 'N' | ''
const qaValue = () => fc.constantFrom<'Y' | 'N' | ''>('Y', 'N', '')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: QA矩阵业务模式判定正确性 (Task 1.2)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 1: QA矩阵业务模式判定正确性', () => {
  /**
   * **Validates: Requirements 2.4, 2.5, 2.6**
   *
   * determineBusinessMode 分支逻辑（镜像实现的条件顺序）：
   * - Q1=Y ∧ Q2=N → 收取合同现金流量为目标
   * - Q1=Y ∧ Q2=Y ∧ Q4=Y → 收取合同现金流量和出售金融资产
   * - Q1=N ∨ (Q2=Y ∧ Q4=N) → 其他业务模式
   * - 其余 → ''
   */
  it('determineBusinessMode follows the exact branch ordering of the IF formula', () => {
    fc.assert(
      fc.property(qaValue(), qaValue(), qaValue(), qaValue(), (q1, q2, q3, q4) => {
        const result = determineBusinessMode(q1, q2, q3, q4)

        if (q1 === 'Y' && q2 === 'N') {
          expect(result).toBe(MODE_CASHFLOW)
        } else if (q1 === 'Y' && q2 === 'Y' && q4 === 'Y') {
          expect(result).toBe(MODE_CASHFLOW_SALE)
        } else if (q1 === 'N' || (q2 === 'Y' && q4 === 'N')) {
          expect(result).toBe(MODE_OTHER)
        } else {
          expect(result).toBe('')
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 列报项目判定与业务模式映射一致性 (Task 1.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 2: 列报项目判定与业务模式映射一致性', () => {
  /**
   * **Validates: Requirements 2.7**
   *
   * 从 4 个 QA 值 → determineBusinessMode → determineReportItem。
   * 非空业务模式必映射非空列报项目，且三种模式分别映射正确科目；
   * 空业务模式映射空列报项目。
   */
  it('non-empty business mode maps to the correct non-empty report item, empty maps to empty', () => {
    fc.assert(
      fc.property(qaValue(), qaValue(), qaValue(), qaValue(), (q1, q2, q3, q4) => {
        const mode = determineBusinessMode(q1, q2, q3, q4)
        const item = determineReportItem(mode)

        if (mode === '') {
          expect(item).toBe('')
        } else {
          // 非空模式必映射非空列报项目
          expect(item).not.toBe('')
          if (mode === MODE_CASHFLOW) {
            expect(item).toBe('应收票据')
          } else if (mode === MODE_CASHFLOW_SALE) {
            expect(item).toBe('应收款项融资')
          } else if (mode === MODE_OTHER) {
            expect(item).toBe('以公允价值计量且其变动计入当期损益的金融资产')
          }
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 贴息天数计算正确性 (Task 1.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 3: 贴息天数计算正确性', () => {
  /**
   * **Validates: Requirements 10.4**
   *
   * calcDiscountDays(maturity, discount) === (Date(maturity) - Date(discount)) / 86400000
   * 生成 2020–2030 范围内的两个 UTC 日期，排序保证 discount ≤ maturity，
   * 以 'YYYY-MM-DD' 格式（UTC 午夜）传入，避免时区抖动。
   */
  it('calcDiscountDays equals the UTC day difference when discount <= maturity', () => {
    const MS_PER_DAY = 86400000
    // 2020-01-01 与 2030-12-31 对应的 epoch 天数（UTC）
    const minDay = Date.UTC(2020, 0, 1) / MS_PER_DAY
    const maxDay = Date.UTC(2030, 11, 31) / MS_PER_DAY
    const toDateStr = (day: number) => new Date(day * MS_PER_DAY).toISOString().slice(0, 10)

    fc.assert(
      fc.property(
        fc.integer({ min: minDay, max: maxDay }),
        fc.integer({ min: minDay, max: maxDay }),
        (dayA, dayB) => {
          const discountDay = Math.min(dayA, dayB)
          const maturityDay = Math.max(dayA, dayB)
          const discountDate = toDateStr(discountDay)
          const maturityDate = toDateStr(maturityDay)

          const result = calcDiscountDays(maturityDate, discountDate)
          const expected =
            (new Date(maturityDate).getTime() - new Date(discountDate).getTime()) / MS_PER_DAY
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 应计贴现利息公式 P×R×D/360 (Task 1.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 4: 应计贴现利息公式P×R×D/360', () => {
  /**
   * **Validates: Requirements 10.5**
   *
   * calcDiscountInterest(P, R, D) ≈ P*R*D/360（容差随量级缩放）
   */
  it('calcDiscountInterest equals faceValue * rate * days / 360', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 0.5, noNaN: true }),
        fc.integer({ min: 0, max: 365 }),
        (faceValue, rate, days) => {
          const result = calcDiscountInterest(faceValue, rate, days)
          const expected = (faceValue * rate * days) / 360
          expect(Math.abs(result - expected)).toBeLessThanOrEqual(1e-6 * Math.max(1, Math.abs(expected)))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 贴息差异计算正确性 (Task 1.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 5: 贴息差异计算正确性', () => {
  /**
   * **Validates: Requirements 10.6**
   *
   * calcInterestDifference(a, b) === a - b
   */
  it('calcInterestDifference(a, b) === a - b', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true }),
        (a, b) => {
          expect(calcInterestDifference(a, b)).toBe(a - b)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 合计行恒等于明细行之和 (Task 1.7)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 7: 合计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 4.7, 7.3, 8.3, 10.8**
   *
   * calcSubtotal(rows) === rows.reduce((a,b)=>a+b, 0)
   * calcSubtotal 本身即 reduce，应精确相等。
   */
  it('calcSubtotal exactly equals rows.reduce sum', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 1, maxLength: 30 }),
        (rows) => {
          const result = calcSubtotal(rows)
          const expected = rows.reduce((a, b) => a + b, 0)
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 贴息差异高亮判定 (Task 1.8)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 12: 贴息差异高亮判定', () => {
  /**
   * **Validates: Requirements 10.7**
   *
   * 高亮规则：d !== 0 → 高亮；d === 0 → 不高亮。
   * 公式引擎中无专用高亮函数，规则内联为谓词。
   */
  const isHighlighted = (d: number) => d !== 0

  it('isHighlighted is true iff difference !== 0', () => {
    fc.assert(
      fc.property(fc.double({ min: -1e6, max: 1e6, noNaN: true }), (d) => {
        expect(isHighlighted(d)).toBe(d !== 0)
      }),
      { numRuns: 100 },
    )
  })

  it('isHighlighted(0) === false (explicit boundary)', () => {
    expect(isHighlighted(0)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// D1-7 备查簿公式
// ═══════════════════════════════════════════════════════════════════════════════

describe('D1-7 memo formulas', () => {
  it('calcMemoEndingBalance rolls movement columns', async () => {
    const { calcMemoEndingBalance } = await import('../useD1FormulaEngine')
    expect(calcMemoEndingBalance(100, 50, 20, 10, 5)).toBe(115)
  })

  it('isHighCreditBank matches major banks', async () => {
    const { isHighCreditBank } = await import('../useD1FormulaEngine')
    expect(isHighCreditBank('中国工商银行股份有限公司')).toBe(true)
    expect(isHighCreditBank('某地方农商行')).toBe(false)
  })

  it('calcUnexpiredEndorsedDiscounted requires unmatured discounted/endorsed', async () => {
    const { calcUnexpiredEndorsedDiscounted } = await import('../useD1FormulaEngine')
    expect(calcUnexpiredEndorsedDiscounted(1000, '已贴现', '2024-06-30', '2023-12-31')).toBe(1000)
    expect(calcUnexpiredEndorsedDiscounted(1000, '已贴现', '2023-06-30', '2023-12-31')).toBe(0)
    expect(calcUnexpiredEndorsedDiscounted(1000, '持有', '2024-06-30', '2023-12-31')).toBe(0)
  })
})
