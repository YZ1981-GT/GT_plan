/**
 * I2 开发支出 — 公式引擎 Property-Based Tests
 * 10 Properties (P1 ~ P10)
 * Spec: .kiro/specs/i2-development-expenditure/
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcDebitCreditBalance,
  calcImpairmentValid,
  calcDateDiffDays,
  isCrossPeriod,
  calcTransferConsistency,
} from '../composables/useI2FormulaEngine'
import {
  evaluateCapitalization,
  calcResearchTotal,
  type CAS6Condition,
} from '../composables/useI2CapitalizationEngine'

const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0.01, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

describe('I2 FormulaEngine PBT', () => {
  /**
   * Property P1: 审定数公式链
   * **Validates: Requirements 2.3**
   * calcAuditedAmount(u, a, r) === u + a + r
   */
  it('P1: 审定数 = 未审 + AJE + RJE', () => {
    fc.assert(
      fc.property(
        safeFloat(), safeFloat(), safeFloat(),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        }
      )
    )
  })

  /**
   * Property P2: 资产类期末余额（1717）
   * **Validates: Requirements 2.4**
   * calcAssetEndBalance(b, d, c) === b + d - c
   */
  it('P2: 资产类期末 = 期初 + 借方 - 贷方', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (b, d, c) => {
          expect(calcAssetEndBalance(b, d, c)).toBeCloseTo(b + d - c, 5)
        }
      )
    )
  })

  /**
   * Property P3: 三角勾稽恒等式
   * **Validates: Requirements 2.5**
   * 当 end = begin + increase - decrease 时，reconciliation === 0
   */
  it('P3: 三角勾稽差额 ≡ 0（当期末=期初+增加-减少）', () => {
    fc.assert(
      fc.property(
        safeFloat(0, 1e9), safeFloat(0, 1e9), safeFloat(0, 1e9),
        (begin, increase, decrease) => {
          const end = begin + increase - decrease
          expect(calcTriangleReconciliation(begin, increase, decrease, end)).toBeCloseTo(0, 5)
        }
      )
    )
  })

  /**
   * Property P4: CAS6五条件逻辑正确性
   * **Validates: Requirements 5.1**
   * - 全yes → isMet=true
   * - 任一no → isMet=false
   * - na不影响判断结果
   */
  it('P4: CAS6五条件 — 全yes满足/任一no不满足/na不影响', () => {
    const conditionResult = fc.constantFrom('yes' as const, 'no' as const, 'na' as const)

    fc.assert(
      fc.property(
        conditionResult, conditionResult, conditionResult, conditionResult, conditionResult,
        (r1, r2, r3, r4, r5) => {
          const conditions: CAS6Condition[] = [
            { id: 1, name: '技术可行性', result: r1, evidence: '' },
            { id: 2, name: '完成意图', result: r2, evidence: '' },
            { id: 3, name: '使用或出售能力', result: r3, evidence: '' },
            { id: 4, name: '未来经济利益', result: r4, evidence: '' },
            { id: 5, name: '资源充足', result: r5, evidence: '' },
          ]

          const result = evaluateCapitalization(conditions)
          const results = [r1, r2, r3, r4, r5]
          const hasNo = results.some(r => r === 'no')
          const hasYes = results.some(r => r === 'yes')
          const allNa = results.every(r => r === 'na')

          if (hasNo) {
            // 任一no → 不满足
            expect(result.isMet).toBe(false)
          } else if (allNa) {
            // 全na → 不满足（无正面证据）
            expect(result.isMet).toBe(false)
          } else if (hasYes && !hasNo) {
            // 有yes无no → 满足
            expect(result.isMet).toBe(true)
          }
        }
      )
    )
  })

  /**
   * Property P5: 研发总额=费用化+资本化
   * **Validates: Requirements 9.1**
   * calcResearchTotal(e, c) === e + c for e≥0, c≥0
   */
  it('P5: 研发总额 = I6费用化 + I2资本化', () => {
    fc.assert(
      fc.property(
        positiveFloat(0, 1e9), positiveFloat(0, 1e9),
        (expense, capitalized) => {
          expect(calcResearchTotal(expense, capitalized)).toBeCloseTo(expense + capitalized, 5)
        }
      )
    )
  })

  /**
   * Property P6: 合计行恒等
   * **Validates: Requirements 2.6**
   * calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('P6: 合计行 = SUM(明细行)', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat(0, 1e6), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        }
      )
    )
  })

  /**
   * Property P7: 借贷平衡
   * **Validates: Requirements 2.7**
   * 同数组借贷 → isBalanced=true；不同数组 → isBalanced=(sum相等)
   */
  it('P7: 借贷平衡 — 同数组必平衡', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 20 }),
        (amounts) => {
          // 同数组作为借方和贷方 → 必定平衡
          const result = calcDebitCreditBalance(amounts, amounts)
          expect(result.isBalanced).toBe(true)
        }
      )
    )
  })

  it('P7b: 借贷平衡 — 不同数组按合计判断', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 10 }),
        fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 10 }),
        (debits, credits) => {
          const result = calcDebitCreditBalance(debits, credits)
          const sumD = debits.reduce((a, b) => a + b, 0)
          const sumC = credits.reduce((a, b) => a + b, 0)
          const expectedBalanced = Math.abs(sumD - sumC) < 1e-6
          expect(result.isBalanced).toBe(expectedBalanced)
        }
      )
    )
  })

  /**
   * Property P8: 减值金额∈[0,账面]
   * **Validates: Requirements 12.2**
   * calcImpairmentValid(imp, bv) === true when imp ∈ [0, bv]
   */
  it('P8: 减值金额 ∈ [0, 账面] 时有效', () => {
    fc.assert(
      fc.property(
        positiveFloat(1, 1e9),
        (bookValue) => {
          // 生成 impairment ∈ [0, bookValue]
          return fc.assert(
            fc.property(
              fc.float({ min: 0, max: Math.fround(bookValue), noNaN: true, noDefaultInfinity: true }),
              (impairment) => {
                expect(calcImpairmentValid(impairment, bookValue)).toBe(true)
              }
            )
          )
        }
      )
    )
  })

  it('P8b: 减值金额超出账面时无效', () => {
    fc.assert(
      fc.property(
        positiveFloat(1, 1e6),
        positiveFloat(0.01, 1e6),
        (bookValue, extra) => {
          const impairment = bookValue + extra
          expect(calcImpairmentValid(impairment, bookValue)).toBe(false)
        }
      )
    )
  })

  /**
   * Property P9: 截止测试日期差
   * **Validates: Requirements 7.3**
   * |recordDate - documentDate| ≤ threshold → 不跨期
   */
  it('P9: 日期差≤阈值 → 不跨期', () => {
    fc.assert(
      fc.property(
        fc.date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') }),
        fc.integer({ min: 0, max: 30 }),
        fc.integer({ min: 1, max: 30 }),
        (baseDate, offsetDays, threshold) => {
          // documentDate = baseDate ± offsetDays
          const documentDate = new Date(baseDate.getTime() + offsetDays * 86400000)
          const diffDays = calcDateDiffDays(baseDate, documentDate)

          expect(diffDays).toBe(offsetDays)

          if (diffDays <= threshold) {
            expect(isCrossPeriod(baseDate, documentDate, threshold)).toBe(false)
          } else {
            expect(isCrossPeriod(baseDate, documentDate, threshold)).toBe(true)
          }
        }
      )
    )
  })

  /**
   * Property P10: 转入I1金额一致性
   * **Validates: Requirements 9.4**
   * sum(transfers) === auditedTotal → 差额为0
   */
  it('P10: 转入I1明细合计 = 审定表转无形列', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 20 }),
        (transfers) => {
          const total = transfers.reduce((a, b) => a + b, 0)
          // 当审定表列值 === sum(transfers) 时，差额应为0
          expect(calcTransferConsistency(transfers, total)).toBeCloseTo(0, 5)
        }
      )
    )
  })

  it('P10b: 转入明细与审定表不一致时差额非零', () => {
    fc.assert(
      fc.property(
        fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 20 }),
        positiveFloat(0.01, 1e6),
        (transfers, discrepancy) => {
          const total = transfers.reduce((a, b) => a + b, 0)
          const wrongTotal = total + discrepancy
          const diff = calcTransferConsistency(transfers, wrongTotal)
          expect(Math.abs(diff)).toBeGreaterThan(0)
        }
      )
    )
  })
})
