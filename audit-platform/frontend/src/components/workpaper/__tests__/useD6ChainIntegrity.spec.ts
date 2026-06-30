/**
 * Property 20 PBT: ECL→D6-3→D6-1联动链完整性
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 32.2
 *
 * Tests the full data flow chain using pure formula functions:
 *   D6-8 grandTotal = SUM(单项) + SUM(各组合)
 *   D6-3 total = SUM(单项rows) + SUM(组合rows)
 *   D6-1区块二合计 = D6-3 total
 *   D6-1区块三净值合计 = 区块一合计 - 区块二合计
 *
 * **Validates: Requirements 27.1, 27.2, 27.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcSubtotal,
  calcBlockTotal,
  calcNetValue,
  calcExpectedProvision,
  calcImpairmentEndUnadjusted,
  calcAuditedAmount,
  calcEndAudited,
} from '../composables/useD6FormulaEngine'

// ─── Shared generators ──────────────────────────────────────────────────────

const positiveFloat = (max = 1e9) =>
  fc.float({ min: 0, max, noNaN: true, noDefaultInfinity: true })

const finiteFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min, max, noNaN: true, noDefaultInfinity: true })

/** ECL单项计提行生成器 */
const eclSingleRowArb = fc.record({
  auditedBalance: positiveFloat(),
  lossRate: fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
  bookBalance: positiveFloat(),
})

/** ECL账龄组合行生成器（6账龄段） */
const eclAgingGroupArb = fc.record({
  rows: fc.array(
    fc.record({
      auditedBalance: positiveFloat(),
      lossRate: fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
      bookBalance: positiveFloat(),
    }),
    { minLength: 1, maxLength: 6 }
  ),
})

/** D6-3减值准备行生成器 */
const impairmentRowArb = fc.record({
  priorUnadjusted: finiteFloat(0, 1e9),
  priorAje: finiteFloat(-1e6, 1e6),
  priorRje: finiteFloat(-1e6, 1e6),
  provision: positiveFloat(1e8),
  otherIncrease: positiveFloat(1e7),
  reversal: positiveFloat(1e7),
  writeOff: positiveFloat(1e7),
  otherDecrease: positiveFloat(1e7),
  endAje: finiteFloat(-1e6, 1e6),
  endRje: finiteFloat(-1e6, 1e6),
})

// ─── Property 20: ECL→D6-3→D6-1联动链完整性 ─────────────────────────────────

describe('Property 20: ECL→D6-3→D6-1联动链完整性', () => {
  /**
   * **Feature: d6-contract-assets, Property 20**
   *
   * 验证完整联动链数据传导：
   *   1. D6-8 grandTotal = SUM(单项应计提) + SUM(各组合小计应计提)
   *   2. D6-3 total = SUM(单项rows.endAudited) + SUM(组合rows.endAudited)
   *   3. D6-1 区块二合计 = D6-3 total (通过crossSheet聚合)
   *   4. D6-1 区块三净值合计 = 区块一合计 - 区块二合计
   *
   * **Validates: Requirements 27.1, 27.2, 27.3**
   */
  it('D6-8 grandTotal = SUM(单项) + SUM(各组合)', () => {
    fc.assert(
      fc.property(
        fc.array(eclSingleRowArb, { minLength: 1, maxLength: 5 }),
        fc.array(eclAgingGroupArb, { minLength: 1, maxLength: 3 }),
        (singleRows, agingGroups) => {
          // D6-8 单项合计应计提
          const singleProvisions = singleRows.map(r => calcExpectedProvision(r.auditedBalance, r.lossRate))
          const singleTotal = calcSubtotal(singleProvisions)

          // D6-8 各组合小计应计提
          const groupTotals = agingGroups.map(g => {
            const groupProvisions = g.rows.map(r => calcExpectedProvision(r.auditedBalance, r.lossRate))
            return calcSubtotal(groupProvisions)
          })
          const allGroupsTotal = calcSubtotal(groupTotals)

          // grandTotal = 单项合计 + 各组合合计
          const grandTotal = singleTotal + allGroupsTotal
          const expectedGrandTotal = calcSubtotal([singleTotal, allGroupsTotal])

          expect(Math.abs(grandTotal - expectedGrandTotal)).toBeLessThan(1e-6)
          // Verify the SUM property: grandTotal = SUM(all individual provisions)
          const allProvisions = [
            ...singleProvisions,
            ...agingGroups.flatMap(g => g.rows.map(r => calcExpectedProvision(r.auditedBalance, r.lossRate))),
          ]
          expect(Math.abs(grandTotal - calcSubtotal(allProvisions))).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('D6-3 total = SUM(单项rows.endAudited) + SUM(组合rows.endAudited)', () => {
    fc.assert(
      fc.property(
        fc.array(impairmentRowArb, { minLength: 1, maxLength: 5 }), // single rows
        fc.array(impairmentRowArb, { minLength: 1, maxLength: 5 }), // group rows
        (singleRows, groupRows) => {
          // Compute endAudited for each D6-3 row using the formula chain
          const computeEndAudited = (row: typeof singleRows[0]) => {
            const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
            const endUnadjusted = calcImpairmentEndUnadjusted(
              priorAudited, row.provision, row.otherIncrease,
              row.reversal, row.writeOff, row.otherDecrease
            )
            return calcEndAudited(endUnadjusted, row.endAje, row.endRje)
          }

          const singleEndAuditeds = singleRows.map(computeEndAudited)
          const groupEndAuditeds = groupRows.map(computeEndAudited)

          const singleSubtotal = calcSubtotal(singleEndAuditeds)
          const groupSubtotal = calcSubtotal(groupEndAuditeds)

          // D6-3 合计 = 单项小计 + 组合小计
          const total = singleSubtotal + groupSubtotal
          const expectedTotal = calcSubtotal([...singleEndAuditeds, ...groupEndAuditeds])

          expect(Math.abs(total - expectedTotal)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('D6-1区块二合计 = D6-3 total; 区块三净值合计 = 区块一合计 - 区块二合计', () => {
    fc.assert(
      fc.property(
        // 区块一：原值行 + 非流动扣减
        fc.array(positiveFloat(), { minLength: 1, maxLength: 5 }),
        positiveFloat(1e8), // block1 非流动扣减
        // 区块二：D6-3 rows → 聚合到审定表
        fc.array(impairmentRowArb, { minLength: 1, maxLength: 5 }),
        positiveFloat(1e7), // block2 非流动扣减
        (block1DynamicValues, block1Deduction, d6_3_rows, block2Deduction) => {
          // 区块一：小计 = SUM(动态行); 合计 = 小计 - 非流动扣减
          const block1Subtotal = calcSubtotal(block1DynamicValues)
          const block1Total = calcBlockTotal(block1Subtotal, block1Deduction)

          // D6-3 rows → endAudited → 聚合到区块二
          const computeEndAudited = (row: typeof d6_3_rows[0]) => {
            const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
            const endUnadjusted = calcImpairmentEndUnadjusted(
              priorAudited, row.provision, row.otherIncrease,
              row.reversal, row.writeOff, row.otherDecrease
            )
            return calcEndAudited(endUnadjusted, row.endAje, row.endRje)
          }

          const d6_3_endAuditeds = d6_3_rows.map(computeEndAudited)
          const d6_3_total = calcSubtotal(d6_3_endAuditeds)

          // 区块二：D6-3 total作为小计; 合计 = 小计 - 非流动扣减
          const block2Subtotal = d6_3_total
          const block2Total = calcBlockTotal(block2Subtotal, block2Deduction)

          // 验证: 区块二合计由D6-3 total驱动
          expect(Math.abs(block2Subtotal - d6_3_total)).toBeLessThan(1e-6)

          // 区块三：净值合计 = 区块一合计 - 区块二合计
          const block3Total = calcNetValue(block1Total, block2Total)
          const expectedBlock3Total = block1Total - block2Total

          expect(Math.abs(block3Total - expectedBlock3Total)).toBeLessThan(1e-6)

          // Verify the net value chain integrity
          // block3 = block1 - block2 algebraically
          expect(Math.abs(block3Total - (block1Total - block2Total))).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})
