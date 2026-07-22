import { describe, it, expect } from 'vitest'
import {
  calcBookUnitPrice,
  calcAuditorFairValue,
  calcFairValueDifference,
  calcIncomeApproachValue,
  calcImpliedCapRate,
  isWithinAcceptableRange,
  buildFairValueAuditNoteDraft,
  buildFairValueConclusionDraft,
  type FairValueReviewRow,
} from '../useH3FairValueReview'

function stubRow(partial: Partial<FairValueReviewRow>): FairValueReviewRow {
  return {
    rowId: 'r1',
    category: '',
    assetName: '',
    openingFairValue: 0,
    area: 0,
    bookUnitPrice: 0,
    endingBalance: 0,
    refUnitPrice: 0,
    refPriceSource: '',
    auditorFairValue: 0,
    difference: 0,
    diffReason: '',
    methodConsistent: '',
    indexRef: '',
    remark: '',
    discountRate: 0,
    rentAssumption: 0,
    capRate: 0,
    growthRate: 0.02,
    independentCalc: 0,
    indVsBookDiff: 0,
    withinRange: true,
    conclusion: '',
    appraisalValue: 0,
    bookValue: 0,
    marketRef: 0,
    ...partial,
  }
}

describe('useH3FairValueReview formulas', () => {
  it('账面单价 = 期末余额 ÷ 面积', () => {
    expect(calcBookUnitPrice(10_000_000, 500)).toBe(20_000)
    expect(calcBookUnitPrice(10_000_000, 0)).toBe(0)
  })

  it('复核公允价值 = 面积 × 参考单价', () => {
    expect(calcAuditorFairValue(500, 18_000)).toBe(9_000_000)
  })

  it('差异 = 期末余额 - 复核公允价值', () => {
    expect(calcFairValueDifference(10_000_000, 9_000_000)).toBe(1_000_000)
  })

  it('收益法独立测算: 年租金/(资本化率-增长率)', () => {
    const val = calcIncomeApproachValue(50_000, 0.05, 0.02)
    expect(val).toBeCloseTo(20_000_000, 0)
  })

  it('范围判断: ±10% 内为合理', () => {
    expect(isWithinAcceptableRange(5_200_000, 5_000_000)).toBe(true)
    expect(isWithinAcceptableRange(6_000_000, 5_000_000)).toBe(false)
  })

  it('隐含资本化率 = 年租金/物业价值 + 增长率', () => {
    const cap = calcImpliedCapRate(50_000, 10_000_000, 0.02)
    expect(cap).toBeCloseTo(0.08, 4)
  })
})

describe('审计说明/结论草稿', () => {
  it('差异超阈值时说明草稿列出物业明细', () => {
    const note = buildFairValueAuditNoteDraft({
      rows: [
        stubRow({
          assetName: '甲写字楼',
          endingBalance: 10_000_000,
          auditorFairValue: 7_000_000,
          difference: 3_000_000,
          refPriceSource: '中指指数',
          diffReason: '区位溢价',
        }),
      ],
      h31: {
        source: 'H3-1',
        sourceTotal: 10_000_000,
        h38Total: 10_000_000,
        diff: 0,
        matched: true,
        note: '勾稽一致',
      },
    })
    expect(note).toContain('甲写字楼')
    expect(note).toContain('差异率超过 20%')
    expect(note).toContain('中指指数')
    expect(note).toContain('勾稽一致')
  })

  it('无异常时结论草稿为 A', () => {
    const c = buildFairValueConclusionDraft({
      highDiffCount: 0,
      outOfRangeCount: 0,
      h31Matched: true,
      hasData: true,
    })
    expect(c.startsWith('A、')).toBe(true)
  })

  it('有差异时结论草稿为 B', () => {
    const c = buildFairValueConclusionDraft({
      highDiffCount: 1,
      outOfRangeCount: 0,
      h31Matched: true,
      hasData: true,
    })
    expect(c.startsWith('B、')).toBe(true)
  })

  it('无数据时结论草稿为 C', () => {
    const c = buildFairValueConclusionDraft({
      highDiffCount: 0,
      outOfRangeCount: 0,
      h31Matched: true,
      hasData: false,
    })
    expect(c.startsWith('C、')).toBe(true)
  })
})
