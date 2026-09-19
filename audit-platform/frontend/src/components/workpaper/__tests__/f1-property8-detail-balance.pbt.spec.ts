/**
 * F1 Property 8 PBT: 明细表余额计算公式链正确性
 *
 * 验证明细表F1-2核心公式链：
 * - 期初审定余额 = 期初未审 + 期初账项调整 + 期初重分类调整 (H = E + F + G)
 * - 期末余额 = 期初审定余额 + 借方发生 - 贷方发生 (O = H + M - N，借方科目)
 * - 期末未审余额 = 期末余额 + 被审计单位重分类调整 (Q = O + P)
 * - 审定数 = 期末未审余额 + 账项调整 + 重分类调整 (X = Q + V + W)
 *
 * **Validates: Requirements 4.5, 4.6, 4.7, 13.3**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import {
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
} from '../composables/useF1FormulaEngine'
import { recalcRowFormulas, type DetailRow } from '../composables/useF1Detail'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 明细表行的可编辑字段生成器 */
const detailInputArb = fc.record({
  priorUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAdjustment: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorReclass: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  debit: fc.float({ min: 0, max: 1e9, noNaN: true }),
  credit: fc.float({ min: 0, max: 1e9, noNaN: true }),
  entityReclass: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
})

/** 构造完整 DetailRow 用于 recalcRowFormulas */
function makeDetailRow(input: {
  priorUnadjusted: number
  priorAdjustment: number
  priorReclass: number
  debit: number
  credit: number
  entityReclass: number
  endAje: number
  endRje: number
}): DetailRow {
  const emptyAging = { within1: 0, y1to2: 0, y2to3: 0, over3: 0 }
  return {
    rowId: 'test-row',
    customerName: 'Test',
    companyCode: '',
    nature: '',
    relationType: '非关联方',
    priorUnadjusted: input.priorUnadjusted,
    priorAdjustment: input.priorAdjustment,
    priorReclass: input.priorReclass,
    priorAudited: 0,
    agingPrior: { ...emptyAging },
    debit: input.debit,
    credit: input.credit,
    endBalance: 0,
    entityReclass: input.entityReclass,
    endUnadjusted: 0,
    agingCurrent: { ...emptyAging },
    endAje: input.endAje,
    endRje: input.endRje,
    endAudited: 0,
    agingAudited: { ...emptyAging },
    isConfirmed: '',
    postPeriodSettlement: 0,
    remark: '',
  }
}

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 8: 明细表余额计算公式链正确性', () => {
  it('calcPriorAudited(E, F, G) === E + F + G', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const result = calcPriorAudited(input.priorUnadjusted, input.priorAdjustment, input.priorReclass)
        const expected = input.priorUnadjusted + input.priorAdjustment + input.priorReclass
        return Math.abs(result - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * O = H + M - N（借方科目 / 预付账款）
   */
  it('calcEndBalance(H, debit, credit) === H + debit - credit', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const H = calcPriorAudited(input.priorUnadjusted, input.priorAdjustment, input.priorReclass)
        const result = calcEndBalance(H, input.debit, input.credit)
        const expected = H + input.debit - input.credit
        return Math.abs(result - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('calcEndUnadjusted(O, P) === O + P', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const H = calcPriorAudited(input.priorUnadjusted, input.priorAdjustment, input.priorReclass)
        const O = calcEndBalance(H, input.debit, input.credit)
        const result = calcEndUnadjusted(O, input.entityReclass)
        const expected = O + input.entityReclass
        return Math.abs(result - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('calcEndAudited(Q, V, W) === Q + V + W', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const H = calcPriorAudited(input.priorUnadjusted, input.priorAdjustment, input.priorReclass)
        const O = calcEndBalance(H, input.debit, input.credit)
        const Q = calcEndUnadjusted(O, input.entityReclass)
        const result = calcEndAudited(Q, input.endAje, input.endRje)
        const expected = Q + input.endAje + input.endRje
        return Math.abs(result - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('recalcRowFormulas 完整公式链一致性（借方科目 O=H+M-N）', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const row = makeDetailRow(input)
        const result = recalcRowFormulas(row)

        const expectedH = input.priorUnadjusted + input.priorAdjustment + input.priorReclass
        const expectedO = expectedH + input.debit - input.credit
        const expectedQ = expectedO + input.entityReclass
        const expectedX = expectedQ + input.endAje + input.endRje

        return (
          Math.abs(result.priorAudited - expectedH) < 1e-6 &&
          Math.abs(result.endBalance - expectedO) < 1e-6 &&
          Math.abs(result.endUnadjusted - expectedQ) < 1e-6 &&
          Math.abs(result.endAudited - expectedX) < 1e-6
        )
      }),
      { numRuns: 100 },
    )
  })
})
