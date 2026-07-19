import { describe, expect, it } from 'vitest'
import {
  createSameControlMergerRow,
  createSameControlReverseRow,
  createSameControlStepRow,
  describeCapitalReserveAdjustment,
  extractSameControlInvesteesFromG7Judgment,
  extractSubsidiaryNamesFromG72,
  extractSubsidiaryNamesFromG74,
  normalizeSameControlRows,
  recalcSameControlMergerRow,
  summarizeSameControlSteps,
  syncMergerRowsFromSameControlNames,
  validateSameControlRows,
} from '../g7SameControlModel'

describe('G7-8 source-aligned model', () => {
  it('calculates one-step merger formulas exactly as the source workbook', () => {
    const row = createSameControlMergerRow(1, '公司1')
    row.ownerEquityBookValue = 100
    row.ownershipRatio = 0.32
    row.cashConsideration = 2
    row.nonCashAssetBookValue = 2
    row.debtBookValue = 3
    row.contingentConsideration = 3
    recalcSameControlMergerRow(row)

    expect(row.initialInvestmentCost).toBe(32)
    expect(row.totalConsideration).toBe(10)
    expect(row.capitalReserveRetainedEarningsAdjustment).toBe(22)
    expect(describeCapitalReserveAdjustment(22, 'merger')).toContain('贷记')
  })

  it('calculates step-acquisition summary including prior holding book value', () => {
    const first = createSameControlStepRow('p', 'P公司', 1)
    first.purchaseRatio = 0.01
    first.consideration = 1
    first.netAssetsBookValue = 22
    first.priorInvestmentAdjustments = 22
    first.priorHoldingBookValue = 10
    first.isPackageDeal = '否'
    first.notPackageBasis = '各次交易独立定价'

    const second = createSameControlStepRow('p', 'P公司', 2)
    second.purchaseRatio = 0.02
    second.consideration = 3
    second.netAssetsBookValue = 44
    second.priorInvestmentAdjustments = 4
    second.priorHoldingBookValue = 10
    second.isPackageDeal = '否'

    const [summary] = summarizeSameControlSteps([first, second])
    expect(summary.cumulativeRatio).toBe(0.03)
    expect(summary.cumulativeConsideration).toBe(4)
    expect(summary.priorHoldingBookValue).toBe(10)
    expect(summary.cumulativePriorAdjustments).toBe(26)
    expect(summary.mergerDateNetAssets).toBe(44)
    expect(summary.initialInvestmentCost).toBe(1.32)
    // ⑥ = 4 + 10 + 26 - 1.32 = 38.68
    expect(summary.capitalReserveRetainedEarningsAdjustment).toBe(38.68)
    expect(summary.adjustmentHint).toContain('冲减')
  })

  it('keeps legacy step formula when prior holding book value is absent', () => {
    const first = createSameControlStepRow('p', 'P公司', 1)
    first.purchaseRatio = 0.01
    first.consideration = 1
    first.netAssetsBookValue = 22
    first.priorInvestmentAdjustments = 22
    const second = createSameControlStepRow('p', 'P公司', 2)
    second.purchaseRatio = 0.02
    second.consideration = 3
    second.netAssetsBookValue = 44
    second.priorInvestmentAdjustments = 4
    const [summary] = summarizeSameControlSteps([first, second])
    expect(summary.capitalReserveRetainedEarningsAdjustment).toBe(28.68)
  })

  it('migrates the legacy simplified row without reversing the source difference', () => {
    const [row] = normalizeSameControlRows([{
      id: 'legacy',
      investeeName: '旧公司',
      acquireeNetAssets: 100,
      shareholdingRatio: 0.32,
      consideration: 10,
      differenceHandling: '调整资本公积',
    }])
    expect(row.section).toBe('merger')
    if (row.section !== 'merger') throw new Error('unexpected section')
    expect(row.initialInvestmentCost).toBe(32)
    expect(row.totalConsideration).toBe(10)
    expect(row.capitalReserveRetainedEarningsAdjustment).toBe(22)
  })

  it('validates mutual exclusion, policy consistency, package deal, and roster cross-checks', () => {
    const merger = createSameControlMergerRow(1, '公司A')
    merger.ownerEquityBookValue = 100
    merger.ownershipRatio = 0.6
    merger.cashConsideration = 70
    merger.accountingPolicyConsistent = '否'
    merger.availableCapitalReserve = 1
    recalcSameControlMergerRow(merger)

    const step = createSameControlStepRow('a', '公司A', 1)
    step.purchaseRatio = 0.6
    step.isPackageDeal = '是'

    const reverse = createSameControlReverseRow(1)
    reverse.transactionContent = '发行股份取得控制'

    const issues = validateSameControlRows([merger, step, reverse], {
      sameControlInvestees: ['公司B'],
      detailInvestees: ['公司B'],
      basicInfoInvestees: ['公司B'],
    })
    expect(issues.some(issue => issue.message.includes('同时出现在一次合并与分步合并'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('会计政策不一致'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('一揽子交易'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('可用资本公积'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('G7-7'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('G7-2/G7-4'))).toBe(true)
    expect(issues.some(issue => issue.message.includes('反向购买'))).toBe(true)
  })

  it('extracts and syncs same-control investees from G7-7 / G7-2 / G7-4', () => {
    expect(extractSameControlInvesteesFromG7Judgment({
      decision: {
        investeeName: '甲子公司',
        relationshipType: '控制',
        combinationType: '同一控制下企业合并',
      },
    })).toEqual(['甲子公司'])
    expect(extractSubsidiaryNamesFromG72([
      { section: 'cost', investeeName: '子1' },
      { section: 'equity', investeeName: '联营1' },
    ])).toEqual(['子1'])
    expect(extractSubsidiaryNamesFromG74([
      { groupType: 'subsidiary', investeeName: '子2' },
      { groupType: 'associate', investeeName: '联营2' },
    ])).toEqual(['子2'])

    const synced = syncMergerRowsFromSameControlNames([], ['甲子公司', '甲子公司'])
    expect(synced.added).toBe(1)
    expect(synced.rows[0].investeeName).toBe('甲子公司')
  })
})
