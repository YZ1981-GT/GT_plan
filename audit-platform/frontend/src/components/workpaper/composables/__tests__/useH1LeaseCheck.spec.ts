/**
 * H1-19 经营租出 + H1-18 关联交易 公式单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  calcLeaseMonths,
  calcMonthsInFiscalYear,
  recalcOperatingRow,
  buildOperatingLeaseNoteDraft,
  mapOperatingToDisclosureRows,
  type OperatingLeaseRow,
  emptyRelatedPartyRow,
  recalcRelatedPartyRow,
  buildH7SourceFingerprint,
  buildH8SourceFingerprint,
  applyH7SourceToRow,
  applyH8SourceToRow,
  detectSourceDrift,
  aggregateH12CategoryTotals,
  fillCategoryTotalsFromDetail,
  matchH10Detail,
  isLikelyInConsolidationScope,
  needsEntryDiffRemark,
  buildAdjustmentSuggestionDraft,
  reconcileA7Disclosure,
} from '../useH1LeaseCheck'

function baseRow(partial: Partial<OperatingLeaseRow> = {}): OperatingLeaseRow {
  return {
    rowId: 'ol-test',
    seq: 1,
    assetName: '厂房A',
    assetCategory: '房屋建筑物',
    specModel: '',
    lessee: '承租方X',
    leaseStart: '2024-01-01',
    leaseEnd: '2026-12-31',
    contractAmount: 360_000,
    monthsThisYear: 12,
    originalCost: 1_200_000,
    accumDep: 200_000,
    depYears: 20,
    residualRate: 5,
    netValue: 1_000_000,
    monthlyDep: 0,
    expectedDep: 0,
    bookedDep: 0,
    depDiff: 0,
    monthlyRent: 0,
    expectedRent: 0,
    bookedRent: 0,
    incomeDiff: 0,
    contractIndex: '',
    contractNo: '',
    deposit: 0,
    renewalTerms: '',
    earlyTermination: '',
    isRelatedParty: 'N',
    hasChanged: 'N',
    accountTreatment: '',
    leaseTerm: 0,
    annualRent: 0,
    totalRentIncome: 0,
    depAlloc: 0,
    maintenanceCost: 0,
    netIncome: 0,
    returnRate: 0,
    marketRent: 0,
    rentDiff: 0,
    conclusion: '',
    remark: '',
    ...partial,
  }
}

describe('calcLeaseMonths', () => {
  it('calculates inclusive calendar months', () => {
    expect(calcLeaseMonths('2024-01-01', '2024-12-31')).toBe(12)
    expect(calcLeaseMonths('2024-01-01', '2026-12-31')).toBe(36)
  })

  it('returns 0 for invalid range', () => {
    expect(calcLeaseMonths('', '2024-12-31')).toBe(0)
    expect(calcLeaseMonths('2025-01-01', '2024-01-01')).toBe(0)
  })
})

describe('calcMonthsInFiscalYear', () => {
  it('full year overlap returns 12', () => {
    expect(calcMonthsInFiscalYear('2024-01-01', '2026-12-31', 2025)).toBe(12)
  })

  it('partial year overlap from mid-year', () => {
    expect(calcMonthsInFiscalYear('2024-06-01', '2026-05-31', 2024)).toBe(7)
  })

  it('no overlap returns 0', () => {
    expect(calcMonthsInFiscalYear('2022-01-01', '2022-12-31', 2025)).toBe(0)
  })
})

describe('buildOperatingLeaseNoteDraft / mapOperatingToDisclosureRows', () => {
  it('draft mentions zero diffs when clean', () => {
    const row = baseRow({ bookedDep: 57000, bookedRent: 120000 })
    recalcOperatingRow(row)
    const draft = buildOperatingLeaseNoteDraft([row], 2025)
    expect(draft).toContain('共 1 项')
    expect(draft).toContain('未见重大差异')
  })

  it('maps disclosure rows with net value and source remark', () => {
    const row = baseRow({ assetName: '厂房A', netValue: 1_000_000, contractIndex: 'H1-19-1' })
    recalcOperatingRow(row)
    const disc = mapOperatingToDisclosureRows([row])
    expect(disc).toHaveLength(1)
    expect(disc[0].name).toBe('厂房A')
    expect(disc[0].amount).toBe(1_000_000)
    expect(disc[0].remark).toBe('来源:H1-19')
    expect(disc[0].description).toContain('索引:H1-19-1')
  })
})

describe('recalcOperatingRow (致同 H1-19)', () => {
  it('computes monthlyDep = cost×(1−residual)/years/12', () => {
    const row = baseRow({ bookedDep: 47500, bookedRent: 120000 })
    recalcOperatingRow(row)
    expect(row.monthlyDep).toBeCloseTo(4750, 5)
    expect(row.expectedDep).toBeCloseTo(57000, 5)
    expect(row.depDiff).toBeCloseTo(9500, 5)
  })

  it('avoids DIV/0 when depYears is 0', () => {
    const row = baseRow({ depYears: 0, monthsThisYear: 12 })
    recalcOperatingRow(row)
    expect(row.monthlyDep).toBe(0)
    expect(row.expectedDep).toBe(0)
  })

  it('derives monthlyRent from contractAmount / leaseTerm', () => {
    const row = baseRow({ contractAmount: 360_000, bookedRent: 120_000 })
    recalcOperatingRow(row)
    expect(row.leaseTerm).toBe(36)
    expect(row.monthlyRent).toBeCloseTo(10_000, 5)
    expect(row.expectedRent).toBeCloseTo(120_000, 5)
    expect(row.incomeDiff).toBeCloseTo(0, 5)
  })

  it('computes returnRate = netIncome / originalCost × 100', () => {
    const row = baseRow({
      contractAmount: 360_000,
      maintenanceCost: 5_000,
      marketRent: 100_000,
    })
    recalcOperatingRow(row)
    expect(row.annualRent).toBeCloseTo(120_000, 5)
    expect(row.depAlloc).toBeCloseTo(57_000, 5)
    expect(row.netIncome).toBeCloseTo(58_000, 5)
    expect(row.returnRate).toBeCloseTo(58_000 / 1_200_000 * 100, 5)
    expect(row.rentDiff).toBeCloseTo(20_000, 5)
  })

  it('accepts residualRate as decimal 0.05', () => {
    const row = baseRow({ residualRate: 0.05 })
    recalcOperatingRow(row)
    expect(row.monthlyDep).toBeCloseTo(4750, 5)
  })
})

describe('recalcRelatedPartyRow (H1-18)', () => {
  it('sale: netValue and disposalGain and priceDiffRate', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    row.originalCost = 1000
    row.accumDep = 300
    row.impairment = 50
    row.transAmount = 700
    row.appraisedValue = 650
    recalcRelatedPartyRow(row)
    expect(row.netValue).toBe(650)
    expect(row.disposalGain).toBe(50)
    expect(row.priceDiffRate).toBeCloseTo((700 - 650) / 650 * 100, 5)
    expect(row.entryDiff).toBe(0)
  })

  it('purchase: entryDiff = bookValue - transAmount', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    row.transAmount = 100
    row.bookValue = 115
    row.categoryTotal = 1000
    recalcRelatedPartyRow(row)
    expect(row.entryDiff).toBe(15)
    expect(row.similarRatio).toBeCloseTo(10, 5)
    expect(row.disposalGain).toBe(0)
  })

  it('h10Diff = disposalGain - h10Gain', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    row.originalCost = 100
    row.accumDep = 40
    row.transAmount = 70
    row.h10Gain = 55
    recalcRelatedPartyRow(row)
    expect(row.netValue).toBe(60)
    expect(row.disposalGain).toBe(10)
    expect(row.h10Diff).toBe(-45)
  })
})

describe('source drift / import mapping', () => {
  it('fingerprint changes when source amount changes', () => {
    const src = {
      rowId: 'a1', name: '设备', originalCost: 100, contractAmount: 100,
      relatedPartyName: '甲', acquisitionDate: '2025-01-01',
    }
    const fp1 = buildH7SourceFingerprint(src)
    const fp2 = buildH7SourceFingerprint({ ...src, originalCost: 120 })
    expect(fp1).not.toBe(fp2)
  })

  it('detectSourceDrift finds changed and deleted sources', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    applyH7SourceToRow(row, {
      rowId: 's1', name: 'A', originalCost: 100, contractAmount: 100,
      relatedPartyName: 'P', acquisitionDate: '2025-01-01',
    })
    const driftedAmt = detectSourceDrift(
      [row],
      [{
        rowId: 's1', name: 'A', originalCost: 999, contractAmount: 100,
        relatedPartyName: 'P', acquisitionDate: '2025-01-01',
      }],
      [],
    )
    expect(driftedAmt).toHaveLength(1)

    const driftedMissing = detectSourceDrift([row], [], [])
    expect(driftedMissing).toHaveLength(1)
  })

  it('applyH8 maps disposal fields', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    const src = {
      rowId: 'd1', name: '车', assetNo: 'V1', originalCost: 200, accDep: 50,
      impairment: 10, disposalIncome: 120, relatedPartyName: '乙', disposalDate: '2025-06-01',
    }
    applyH8SourceToRow(row, src)
    expect(row.assetNo).toBe('V1')
    expect(row.netValue).toBe(140)
    expect(row.disposalGain).toBe(-20)
    expect(row.sourceFingerprint).toBe(buildH8SourceFingerprint(src))
  })
})

describe('H1-2 category totals / H10 match / A7', () => {
  it('aggregateH12CategoryTotals sums increase/decrease by category', () => {
    const rows = [
      { category: '机器设备', originalCostIncrease: 100, originalCostDecrease: 0 },
      { category: '机器设备', originalCostIncrease: 50, originalCostDecrease: 20 },
      { category: '房屋建筑物', originalCostIncrease: 0, originalCostDecrease: 80 },
    ]
    expect(aggregateH12CategoryTotals(rows, '购入').get('机器设备')).toBe(150)
    expect(aggregateH12CategoryTotals(rows, '出售').get('房屋建筑物')).toBe(80)
  })

  it('fillCategoryTotalsFromDetail sets similarRatio', () => {
    const rp = emptyRelatedPartyRow(1, '购入')
    rp.assetCategory = '机器设备'
    rp.transAmount = 30
    const n = fillCategoryTotalsFromDetail([rp], [
      { category: '机器设备', originalCostIncrease: 100, originalCostDecrease: 0 },
    ])
    expect(n).toBe(1)
    expect(rp.categoryTotal).toBe(100)
    expect(rp.similarRatio).toBeCloseTo(30, 5)
  })

  it('matchH10Detail prefers sourceRowRef then assetNo then unique name', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    row.sourceRowId = 'src-9'
    row.assetNo = 'NO-1'
    row.name = '同名设备'
    const h10 = [
      { sourceRowRef: 'src-9', disposalGainLoss: 11, assetName: '其他' },
      { assetNo: 'NO-1', disposalGainLoss: 22, assetName: '同名设备' },
      { assetName: '同名设备', disposalGainLoss: 33 },
      { assetName: '同名设备', disposalGainLoss: 44 },
    ]
    expect(matchH10Detail(row, h10)?.disposalGainLoss).toBe(11)
    row.sourceRowId = ''
    expect(matchH10Detail(row, h10)?.disposalGainLoss).toBe(22)
    row.assetNo = ''
    expect(matchH10Detail(row, h10)).toBeNull()
  })

  it('isLikelyInConsolidationScope / needsEntryDiffRemark / reconcileA7', () => {
    expect(isLikelyInConsolidationScope('全资子公司')).toBe(true)
    expect(isLikelyInConsolidationScope('联营企业')).toBe(false)

    const row = emptyRelatedPartyRow(1, '购入')
    row.transAmount = 100
    row.bookValue = 120
    recalcRelatedPartyRow(row)
    expect(needsEntryDiffRemark(row, 10)).toBe(true)
    row.remark = '含运费'
    expect(needsEntryDiffRemark(row, 10)).toBe(false)

    expect(reconcileA7Disclosure(100, 100).status).toBe('ok')
    expect(reconcileA7Disclosure(100, 80).status).toBe('mismatch')
    expect(reconcileA7Disclosure(100, null).status).toBe('no-a7')
  })

  it('buildAdjustmentSuggestionDraft mentions unfair pricing', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    row.counterparty = '甲'
    row.name = '设备'
    row.transAmount = 200
    row.appraisedValue = 100
    recalcRelatedPartyRow(row)
    const draft = buildAdjustmentSuggestionDraft([row], 10, 10)
    expect(draft).toContain('定价差异率')
    expect(draft).toContain('甲')
  })
})
