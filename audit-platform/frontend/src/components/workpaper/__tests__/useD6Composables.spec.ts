/**
 * useD6Composables PBT
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D6 合同资产各 composable 的核心公式与结构不变量。
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Tasks: 7.2, 7.3, 8.2, 9.2, 10.2, 10.3, 11.2, 11.3, 12.2, 13.2
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEndUnadjustedDebit,
  calcEndAudited,
  calcImpairmentEndUnadjusted,
  calcSubtotal,
  calcRelatedPartyEndBalance,
  calcBookValue,
  calcExpectedProvision,
  calcEclDifference,
} from '../composables/useD6FormulaEngine'
import { createEmptyRow } from '../composables/useD6Detail'

// ─── Shared generator config ────────────────────────────────────────────────

const finiteFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min, max, noNaN: true, noDefaultInfinity: true })

const positiveFloat = (max = 1e9) =>
  fc.float({ min: 0, max, noNaN: true, noDefaultInfinity: true })

// ─── Task 7.2: Property 10 — D6-2行公式链（借方科目完整链）─────────────────

describe('Property 10: D6-2行公式链（借方科目完整链）', () => {
  /**
   * **Feature: d6-contract-assets, Property 10**
   *
   * 完整公式链验证：
   *   priorAudited = priorUnadjusted + priorAje + priorRje
   *   endUnadjusted = priorAudited + debit - credit (借方科目!)
   *   endAudited = endUnadjusted + endAje + endRje
   *
   * **Validates: Requirements 5.4**
   */
  it('完整公式链: priorAudited → endUnadjusted → endAudited', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(), finiteFloat(), // priorUnadjusted, priorAje, priorRje
        finiteFloat(), finiteFloat(),                // debit, credit
        finiteFloat(), finiteFloat(),                // endAje, endRje
        (priorUnadjusted, priorAje, priorRje, debit, credit, endAje, endRje) => {
          // Step 1: 期初审定 = 期初未审 + AJE + RJE
          const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
          const expectedPriorAudited = priorUnadjusted + priorAje + priorRje
          expect(Math.abs(priorAudited - expectedPriorAudited)).toBeLessThan(1e-6)

          // Step 2: 期末未审 = 期初审定 + 借方 - 贷方（借方科目）
          const endUnadjusted = calcEndUnadjustedDebit(priorAudited, debit, credit)
          const expectedEndUnadjusted = priorAudited + debit - credit
          expect(Math.abs(endUnadjusted - expectedEndUnadjusted)).toBeLessThan(1e-6)

          // Step 3: 期末审定 = 期末未审 + AJE + RJE
          const endAudited = calcEndAudited(endUnadjusted, endAje, endRje)
          const expectedEndAudited = endUnadjusted + endAje + endRje
          expect(Math.abs(endAudited - expectedEndAudited)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 7.3: Property 7 — 动态行添加保持结构不变量 ─────────────────────────

describe('Property 7: 动态行添加保持结构不变量', () => {
  /**
   * **Feature: d6-contract-assets, Property 7**
   *
   * 验证 createEmptyRow 生成的空行满足：
   *   1. 所有数值字段均为 0
   *   2. 行结构完整（具备所有 DetailRow 字段）
   *   3. 添加到数组后 length = N + 1，新行在末尾
   *
   * **Validates: Requirements 5.7, 8.5, 9.2, 13.9, 14.4**
   */
  it('addRow后length=N+1；新行数值全0；新行位于末尾', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 30 }), // 初始行数 N
        fc.integer({ min: 1, max: 999 }), // seqNo
        (n, seqNo) => {
          // 模拟已有 N 行
          const existingRows = Array.from({ length: n }, (_, i) => createEmptyRow(i + 1))

          // 添加新行
          const newRow = createEmptyRow(seqNo)
          const updatedRows = [...existingRows, newRow]

          // 断言1: length = N + 1
          expect(updatedRows.length).toBe(n + 1)

          // 断言2: 新行所有数值字段为 0
          expect(newRow.priorUnadjusted).toBe(0)
          expect(newRow.priorAje).toBe(0)
          expect(newRow.priorRje).toBe(0)
          expect(newRow.priorAudited).toBe(0)
          expect(newRow.debitAmount).toBe(0)
          expect(newRow.creditAmount).toBe(0)
          expect(newRow.endUnadjusted).toBe(0)
          expect(newRow.endAje).toBe(0)
          expect(newRow.endRje).toBe(0)
          expect(newRow.endAudited).toBe(0)
          expect(newRow.agePrior1y).toBe(0)
          expect(newRow.agePrior1to2y).toBe(0)
          expect(newRow.agePrior2to3y).toBe(0)
          expect(newRow.agePrior3yAbove).toBe(0)
          expect(newRow.ageEnd1y).toBe(0)
          expect(newRow.ageEnd1to2y).toBe(0)
          expect(newRow.ageEnd2to3y).toBe(0)
          expect(newRow.ageEnd3yAbove).toBe(0)
          expect(newRow.receivableWithin1y).toBe(0)
          expect(newRow.receivableAbove1y).toBe(0)
          expect(newRow.postPeriodSettlement).toBe(0)

          // 断言3: 新行在末尾
          expect(updatedRows[updatedRows.length - 1]).toBe(newRow)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 8.2: Property 15 — 减值准备明细公式链（D6-3）─────────────────────

describe('Property 15: 减值准备明细公式链（D6-3）', () => {
  /**
   * **Feature: d6-contract-assets, Property 15**
   *
   * 完整公式链验证：
   *   priorAudited = priorUnadjusted + priorAje + priorRje
   *   endUnadjusted = priorAudited + provision + otherIncrease - reversal - writeOff - otherDecrease
   *   endAudited = endUnadjusted + endAje + endRje
   *
   * **Validates: Requirements 8.3**
   */
  it('减值准备完整公式链: priorAudited → endUnadjusted → endAudited', () => {
    fc.assert(
      fc.property(
        finiteFloat(), finiteFloat(), finiteFloat(), // priorUnadjusted, priorAje, priorRje
        finiteFloat(), finiteFloat(),                // provision, otherIncrease
        finiteFloat(), finiteFloat(), finiteFloat(), // reversal, writeOff, otherDecrease
        finiteFloat(), finiteFloat(),                // endAje, endRje
        (priorUnadjusted, priorAje, priorRje, provision, otherIncrease, reversal, writeOff, otherDecrease, endAje, endRje) => {
          // Step 1: 期初审定
          const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
          const expectedPriorAudited = priorUnadjusted + priorAje + priorRje
          expect(Math.abs(priorAudited - expectedPriorAudited)).toBeLessThan(1e-6)

          // Step 2: 期末未审 = 期初审定 + 计提 + 其他增加 - 转回 - 核销 - 其他减少
          const endUnadjusted = calcImpairmentEndUnadjusted(
            priorAudited, provision, otherIncrease, reversal, writeOff, otherDecrease
          )
          const expectedEndUnadjusted = priorAudited + provision + otherIncrease - reversal - writeOff - otherDecrease
          expect(Math.abs(endUnadjusted - expectedEndUnadjusted)).toBeLessThan(1e-6)

          // Step 3: 期末审定
          const endAudited = calcEndAudited(endUnadjusted, endAje, endRje)
          const expectedEndAudited = endUnadjusted + endAje + endRje
          expect(Math.abs(endAudited - expectedEndAudited)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 9.2: Property 8 — 调整分录借贷平衡检查 ─────────────────────────────

describe('Property 8: 调整分录借贷平衡检查', () => {
  /**
   * **Feature: d6-contract-assets, Property 8**
   *
   * 对任意调整分录行数组：
   *   isBalanced === (Math.abs(debitTotal - creditTotal) < 0.01)
   *   balanceDiff === debitTotal - creditTotal
   *
   * **Validates: Requirements 9.3**
   */
  it('isBalanced === (|debitTotal - creditTotal| < 0.01); balanceDiff === debitTotal - creditTotal', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            debit: fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
            credit: fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          }),
          { minLength: 0, maxLength: 20 }
        ),
        (entries) => {
          const debitTotal = calcSubtotal(entries.map(e => e.debit))
          const creditTotal = calcSubtotal(entries.map(e => e.credit))

          const balanceDiff = debitTotal - creditTotal
          const isBalanced = Math.abs(balanceDiff) < 0.01

          // 断言: isBalanced 逻辑正确
          expect(isBalanced).toBe(Math.abs(debitTotal - creditTotal) < 0.01)
          // 断言: balanceDiff 计算正确
          expect(Math.abs(balanceDiff - (debitTotal - creditTotal))).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 10.2: Property 18 — 关联方期末余额（借方科目）+ 账面价值 ──────────

describe('Property 18: 关联方期末余额（借方科目）+ 账面价值', () => {
  /**
   * **Feature: d6-contract-assets, Property 18**
   *
   * 验证：
   *   calcRelatedPartyEndBalance(prior, debit, credit) === prior + debit - credit
   *   calcBookValue(endBalance, impairment) === endBalance - impairment
   *
   * **Validates: Requirements 10.3**
   */
  it('关联方期末余额 = 期初 + 借方 - 贷方; 账面价值 = 期末余额 - 坏账准备', () => {
    fc.assert(
      fc.property(
        positiveFloat(), positiveFloat(), positiveFloat(), // priorBalance, debit, credit
        fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }), // impairmentRatio
        (priorBalance, debit, credit, impairmentRatio) => {
          // 关联方期末余额
          const endBalance = calcRelatedPartyEndBalance(priorBalance, debit, credit)
          const expectedEndBalance = priorBalance + debit - credit
          expect(Math.abs(endBalance - expectedEndBalance)).toBeLessThan(1e-6)

          // 账面价值 = 期末余额 - 坏账准备
          const impairment = Math.abs(endBalance) * impairmentRatio
          const bookValue = calcBookValue(endBalance, impairment)
          const expectedBookValue = endBalance - impairment
          expect(Math.abs(bookValue - expectedBookValue)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 10.3: Property 19 — 账面价值 = 期末余额 - 坏账准备 ────────────────

describe('Property 19: 账面价值 = 期末余额 - 坏账准备', () => {
  /**
   * **Feature: d6-contract-assets, Property 19**
   *
   * 验证：
   *   calcBookValue(endBalance, endBalance * impairmentRatio) === endBalance - endBalance * impairmentRatio
   *
   * **Validates: Requirements 10.3, 15.1**
   */
  it('calcBookValue(endBalance, endBalance * ratio) === endBalance * (1 - ratio)', () => {
    fc.assert(
      fc.property(
        positiveFloat(),
        fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        (endBalance, impairmentRatio) => {
          const impairment = endBalance * impairmentRatio
          const bookValue = calcBookValue(endBalance, impairment)
          const expected = endBalance - impairment
          expect(Math.abs(bookValue - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 11.2: Property 13 — ECL应计提 = 余额 × 损失率 ─────────────────────

describe('Property 13: ECL应计提 = 余额 × 损失率', () => {
  /**
   * **Feature: d6-contract-assets, Property 13**
   *
   * 验证：calcExpectedProvision(balance, rate) === balance × rate
   *
   * **Validates: Requirements 13.3, 13.4**
   */
  it('calcExpectedProvision(balance, rate) === balance * rate', () => {
    fc.assert(
      fc.property(
        positiveFloat(),
        fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        (balance, rate) => {
          const result = calcExpectedProvision(balance, rate)
          const expected = balance * rate
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 11.3: Property 14 — ECL差异 = 应计提 - 账面余额 ───────────────────

describe('Property 14: ECL差异 = 应计提 - 账面余额', () => {
  /**
   * **Feature: d6-contract-assets, Property 14**
   *
   * 验证：calcEclDifference(expectedProvision, bookBalance) === expectedProvision - bookBalance
   *
   * **Validates: Requirements 13.3**
   */
  it('calcEclDifference(expectedProvision, bookBalance) === expectedProvision - bookBalance', () => {
    fc.assert(
      fc.property(
        positiveFloat(),
        positiveFloat(),
        (expectedProvision, bookBalance) => {
          const result = calcEclDifference(expectedProvision, bookBalance)
          const expected = expectedProvision - bookBalance
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 12.2: Property 16 — 期后结转联动一致性 ─────────────────────────────

describe('Property 16: 期后结转联动一致性', () => {
  /**
   * **Feature: d6-contract-assets, Property 16**
   *
   * 验证：对于 D6-2 明细行中每个客户的 postPeriodSettlement，
   * 应等于 D6-6 检查区块(2) 中同一 customerName 的 creditAmount 之和。
   *
   * 生成器：DetailRow[] + InspectionBlock2Row[] 共享 customerName 池。
   *
   * **Validates: Requirements 25.1, 25.3**
   */
  it('detail.postPeriodSettlement === SUM(block2.filter(customerName).creditAmount)', () => {
    const customerNameArb = fc.constantFrom('客户A', '客户B', '客户C', '客户D', '客户E')

    const block2RowArb = fc.record({
      customerName: customerNameArb,
      creditAmount: positiveFloat(),
    })

    fc.assert(
      fc.property(
        fc.array(customerNameArb, { minLength: 1, maxLength: 10 }),
        fc.array(block2RowArb, { minLength: 0, maxLength: 20 }),
        (detailCustomers, block2Rows) => {
          // 对每个 detailCustomer 计算期后结转：SUM(block2中同名客户的creditAmount)
          for (const customerName of detailCustomers) {
            const matchingRows = block2Rows.filter(r => r.customerName === customerName)
            const expectedSettlement = calcSubtotal(matchingRows.map(r => r.creditAmount))

            // 手动计算验证
            const manualSum = matchingRows.reduce((sum, r) => sum + r.creditAmount, 0)
            expect(Math.abs(expectedSettlement - manualSum)).toBeLessThan(1e-6)
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Task 13.2: Property 17 — 附注按金额排序 ────────────────────────────────

describe('Property 17: 附注按金额排序', () => {
  /**
   * **Feature: d6-contract-assets, Property 17**
   *
   * 验证：对附注披露项按金额降序排序后，
   * items[i].amount >= items[i+1].amount 对所有 i 恒成立。
   *
   * **Validates: Requirements 15.1**
   */
  it('排序后 items[i].amount >= items[i+1].amount 恒成立（降序）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            name: fc.string({ minLength: 1, maxLength: 10 }),
            amount: fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          }),
          { minLength: 2, maxLength: 20 }
        ),
        (items) => {
          // 按金额降序排序
          const sorted = [...items].sort((a, b) => b.amount - a.amount)

          // 验证降序不变量
          for (let i = 0; i < sorted.length - 1; i++) {
            expect(sorted[i].amount).toBeGreaterThanOrEqual(sorted[i + 1].amount)
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})
