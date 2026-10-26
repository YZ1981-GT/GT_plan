/**
 * F1 Property 8 PBT：明细表余额计算公式链正确性
 *
 * 直接调用生产 `recalcRowFormulas`，验证权威 F1-2 模板口径：
 * - H = E + F + G
 * - O = E + M - N
 * - Q = O + P
 * - X = Q + V + W（模板 X 列原为 =O+V+W、漏了被审计单位重分类 P，spec
 *   oo-writeback-template-parity-closure R1 已修成 =Q+V+W）
 *
 * **Validates: Requirements 4.5, 4.6, 4.7, 13.3**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { recalcRowFormulas, type DetailRow } from '../composables/useF1Detail'

const detailInputArb = fc.record({
  priorUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAdjustment: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorReclass: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  debit: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  credit: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  entityReclass: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
})

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

function closeEnough(actual: number, expected: number): boolean {
  return Math.abs(actual - expected) <= 1e-6
}

describe('F1 Property 8：明细表余额计算公式链正确性', () => {
  it('生产公式对任意输入保持模板恒等式', () => {
    fc.assert(
      fc.property(detailInputArb, (input) => {
        const result = recalcRowFormulas(makeDetailRow(input))
        const expectedH = input.priorUnadjusted + input.priorAdjustment + input.priorReclass
        const expectedO = input.priorUnadjusted + input.debit - input.credit
        const expectedQ = expectedO + input.entityReclass
        const expectedX = expectedQ + input.endAje + input.endRje

        return (
          closeEnough(result.priorAudited, expectedH) &&
          closeEnough(result.endBalance, expectedO) &&
          closeEnough(result.endUnadjusted, expectedQ) &&
          closeEnough(result.endAudited, expectedX)
        )
      }),
      { numRuns: 5 },
    )
  })

  it('期初调整不进 O；被审计单位重分类进 Q 与 X；期末调整进 X', () => {
    const result = recalcRowFormulas(makeDetailRow({
      priorUnadjusted: 100,
      priorAdjustment: 20,
      priorReclass: -7,
      debit: 30,
      credit: 8,
      entityReclass: 11,
      endAje: -5,
      endRje: 13,
    }))

    expect(result.priorAudited).toBe(113)
    expect(result.endBalance).toBe(122)
    expect(result.endUnadjusted).toBe(133)
    // X = Q + V + W = 133 - 5 + 13；按旧模板 O 起算会得 130（少了重分类 11）
    expect(result.endAudited).toBe(141)
  })
})
