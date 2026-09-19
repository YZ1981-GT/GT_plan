/**
 * F1 Property 7 PBT: 审定表公式链正确性
 *
 * 验证审定表核心公式：
 * - 审定数 === 未审 + 账项调整 + 重分类调整
 * - 变动额 === 期末审定 - 期初审定
 * - 按性质合计 === 各性质行之和
 * - 按账龄合计 === 各账龄行之和
 *
 * **Validates: Requirements 2.3, 2.4, 2.10**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcChangeAmount,
  calcSubtotal,
} from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 审定表行生成器（单行含完整字段） */
const adjudicationRowArb = fc.record({
  priorUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  currentUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  currentAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  currentRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
})

/** 多行（按性质分类，1~5行） */
const natureRowsArb = fc.array(adjudicationRowArb, { minLength: 1, maxLength: 5 })

/** 固定4行（按账龄分类） */
const agingRowsArb = fc.tuple(
  adjudicationRowArb,
  adjudicationRowArb,
  adjudicationRowArb,
  adjudicationRowArb,
)

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 7: 审定表公式链正确性', () => {
  /**
   * **Property 7a: 审定数 === 未审 + 账项调整 + 重分类调整**
   *
   * 对任意 (unadjusted, aje, rje)，calcAuditedAmount 应返回三者之和。
   * 适用于期初审定和期末审定。
   *
   * **Validates: Requirements 2.3**
   */
  it('审定数 === 未审 + AJE + RJE（期初和期末均适用）', () => {
    fc.assert(
      fc.property(adjudicationRowArb, (row) => {
        const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
        const expectedPrior = row.priorUnadjusted + row.priorAje + row.priorRje

        const currentAudited = calcAuditedAmount(row.currentUnadjusted, row.currentAje, row.currentRje)
        const expectedCurrent = row.currentUnadjusted + row.currentAje + row.currentRje

        return (
          Math.abs(priorAudited - expectedPrior) < 1e-6 &&
          Math.abs(currentAudited - expectedCurrent) < 1e-6
        )
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 7b: 变动额 === 期末审定 - 期初审定**
   *
   * 对任意审定表行，changeAmount 应等于期末审定数减期初审定数。
   *
   * **Validates: Requirements 2.4**
   */
  it('变动额 === 期末审定 - 期初审定', () => {
    fc.assert(
      fc.property(adjudicationRowArb, (row) => {
        const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
        const currentAudited = calcAuditedAmount(row.currentUnadjusted, row.currentAje, row.currentRje)
        const changeAmount = calcChangeAmount(currentAudited, priorAudited)
        const expected = currentAudited - priorAudited
        return Math.abs(changeAmount - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 7c: 按性质合计 === 各性质行审定数之和**
   *
   * 对任意多行数据，合计行 currentAudited 应等于各行 currentAudited 之和。
   *
   * **Validates: Requirements 2.4, 2.10**
   */
  it('按性质合计的审定数 === 各性质行审定数之和', () => {
    fc.assert(
      fc.property(natureRowsArb, (rows) => {
        const auditedValues = rows.map(r =>
          calcAuditedAmount(r.currentUnadjusted, r.currentAje, r.currentRje),
        )
        const subtotal = calcSubtotal(auditedValues)
        const expected = auditedValues.reduce((sum, v) => sum + v, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 7d: 按账龄合计 === 各账龄行审定数之和**
   *
   * 固定4行账龄分类，合计行应等于4行审定数之和。
   *
   * **Validates: Requirements 2.10**
   */
  it('按账龄合计的审定数 === 4个账龄行审定数之和', () => {
    fc.assert(
      fc.property(agingRowsArb, ([r1, r2, r3, r4]) => {
        const values = [r1, r2, r3, r4].map(r =>
          calcAuditedAmount(r.currentUnadjusted, r.currentAje, r.currentRje),
        )
        const subtotal = calcSubtotal(values)
        const expected = values.reduce((sum, v) => sum + v, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 7e: 变动额公式链一致性**
   *
   * 合计行变动额 === SUM各行变动额
   *
   * **Validates: Requirements 2.4**
   */
  it('合计行变动额 === SUM(各行变动额)', () => {
    fc.assert(
      fc.property(natureRowsArb, (rows) => {
        // 各行变动额
        const changeAmounts = rows.map(r => {
          const prior = calcAuditedAmount(r.priorUnadjusted, r.priorAje, r.priorRje)
          const current = calcAuditedAmount(r.currentUnadjusted, r.currentAje, r.currentRje)
          return calcChangeAmount(current, prior)
        })

        // 合计行变动额（通过合计审定数计算）
        const totalPrior = calcSubtotal(rows.map(r =>
          calcAuditedAmount(r.priorUnadjusted, r.priorAje, r.priorRje),
        ))
        const totalCurrent = calcSubtotal(rows.map(r =>
          calcAuditedAmount(r.currentUnadjusted, r.currentAje, r.currentRje),
        ))
        const totalChange = calcChangeAmount(totalCurrent, totalPrior)

        // SUM各行变动额
        const sumChanges = calcSubtotal(changeAmounts)

        return Math.abs(totalChange - sumChanges) < 1e-6
      }),
      { numRuns: 100 },
    )
  })
})
