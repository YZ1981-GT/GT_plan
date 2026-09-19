/**
 * g7EquityMethodCalcModel unit tests — 多公司净资产 + 建议分录 + 比例归一
 */
import { describe, expect, it } from 'vitest'
import {
  buildSuggestedAdjustments,
  calcAdjustedEquityTotal,
  calcParentEquityTotal,
  calcShareOfAdjustedEquity,
  createNetAssetAdjustment,
  ensureNetAssetAdjustments,
  flattenNetAssetAdjustmentsForExport,
  hydrateNetAssetAdjustment,
  hydrateNetAssetAdjustmentsFromFlatRows,
  isAmountOverMateriality,
  mergeSuggestedIntoG73,
  normalizeOwnershipRatio,
  ownershipRatioToPercent,
  resolveUnexplainedCounterAccount,
  rollforwardEnd,
  syncAuditedNetAssetsFromAdjustment,
  toG73Entries,
  G714_PENNY_THRESHOLD,
  G714_SUGGESTED_SOURCE_KIND,
} from '../../g7-long-term-equity-method/calculation/g7EquityMethodCalcModel'
import type { EquityMethodCalcRow } from '../useG7EquityMethodFormData'

function emptyRow(name: string, overrides: Partial<EquityMethodCalcRow> = {}): EquityMethodCalcRow {
  return {
    id: `r-${name}`,
    seq: 1,
    investeeName: name,
    reportedNetProfit: 0,
    internalTransactionAdj: 0,
    fvDepreciationAdj: 0,
    accountingPolicyAdj: 0,
    otherAdj: 0,
    adjustedNetProfit: 0,
    investmentRatio: 0.3,
    equityShare: 0,
    confirmedIncome: 0,
    confirmedOci: 0,
    ociDifference: 0,
    confirmedOtherEquity: 0,
    otherEquityDifference: 0,
    incomeDifference: 0,
    ociChange: 0,
    ociShare: 0,
    otherEquityChange: 0,
    otherEquityShare: 0,
    dividendDistributed: 0,
    openingBalance: 0,
    closingBalance: 0,
    costOpening: 0,
    costChange: 0,
    costClosing: 0,
    pnlAdjOpening: 0,
    pnlAdjChange: 0,
    pnlAdjClosing: 0,
    ociBalOpening: 0,
    ociBalChange: 0,
    ociBalClosing: 0,
    otherEqBalOpening: 0,
    otherEqBalChange: 0,
    otherEqBalClosing: 0,
    auditedNetAssets: 0,
    shareOfAuditedNetAssets: 0,
    lteiBookBalance: 0,
    netAssetShareVariance: 0,
    g72OpeningTotal: 0,
    g72ClosingTotal: 0,
    openingReconVariance: 0,
    closingReconVariance: 0,
    goodwill: 0,
    cumulativeFvAdj: 0,
    impairment: 0,
    unexplainedVariance: 0,
    unexplainedNature: 'pending',
    varianceExplanation: '',
    auditConclusion: '无差异',
    ...overrides,
  }
}

describe('g7EquityMethodCalcModel net asset', () => {
  it('rollforwardEnd = begin + increase - decrease', () => {
    expect(rollforwardEnd({ begin: 100, increase: 20, decrease: 5 })).toBe(115)
  })

  it('calcAdjustedEquityTotal uses parent equity + FV - elim (excludes NCI)', () => {
    const adj = createNetAssetAdjustment('甲公司', 0.4)
    adj.shareCapital = { begin: 1000, increase: 0, decrease: 0 }
    adj.retainedEarnings = { begin: 500, increase: 100, decrease: 0 }
    adj.treasuryStock = { begin: 50, increase: 0, decrease: 0 }
    adj.nonControllingInterest = { begin: 0, increase: 200, decrease: 0 }
    adj.fvDiffAtAcquisition = { begin: 0, increase: 80, decrease: 0 }
    adj.unrealizedInternalElim = { begin: 0, increase: 30, decrease: 0 }
    expect(calcParentEquityTotal(adj, 'end')).toBe(1550)
    expect(calcAdjustedEquityTotal(adj, 'end')).toBe(1600)
    expect(calcShareOfAdjustedEquity(adj)).toBe(640)
  })

  it('ensureNetAssetAdjustments creates one per investee and syncs auditedNetAssets', () => {
    const rows = [emptyRow('甲'), emptyRow('乙'), emptyRow('甲', { seq: 2, id: 'r-甲2' })]
    const list = ensureNetAssetAdjustments(rows, [])
    expect(list).toHaveLength(2)
    expect(list.map((x) => x.investeeName)).toEqual(['甲', '乙'])

    list[0].shareCapital = { begin: 1000, increase: 0, decrease: 0 }
    list[0].ownershipRatio = 0.5
    syncAuditedNetAssetsFromAdjustment(rows[0], list[0])
    expect(rows[0].auditedNetAssets).toBe(1000)
    expect(rows[0].investmentRatio).toBe(0.3)

    const bare = emptyRow('丁', { investmentRatio: 0 })
    syncAuditedNetAssetsFromAdjustment(bare, list[0])
    expect(bare.investmentRatio).toBe(0.5)
  })

  it('hydrateNetAssetAdjustment restores snake_case fields', () => {
    const adj = hydrateNetAssetAdjustment({
      investee_name: '丙',
      ownership_ratio: 0.25,
      share_capital: { begin: 10, increase: 2, decrease: 1 },
    })
    expect(adj.investeeName).toBe('丙')
    expect(adj.ownershipRatio).toBe(0.25)
    expect(rollforwardEnd(adj.shareCapital)).toBe(11)
  })

  it('flatten/hydrate NA round-trips by investee + line item', () => {
    const adj = createNetAssetAdjustment('甲', 0.3)
    adj.shareCapital = { begin: 100, increase: 10, decrease: 0 }
    const flat = flattenNetAssetAdjustmentsForExport([adj])
    expect(flat.some((r) => r.lineItemKey === 'shareCapital' && r.begin === 100)).toBe(true)
    expect(flat[0].ownershipRatio).toBe(30)
    const restored = hydrateNetAssetAdjustmentsFromFlatRows(flat)
    expect(restored).toHaveLength(1)
    expect(restored[0].ownershipRatio).toBe(0.3)
    expect(rollforwardEnd(restored[0].shareCapital)).toBe(110)
  })
})

describe('ownership ratio normalize', () => {
  it('converts percent >1 to fraction', () => {
    expect(normalizeOwnershipRatio(30)).toBe(0.3)
    expect(normalizeOwnershipRatio(0.3)).toBe(0.3)
    expect(ownershipRatioToPercent(0.3)).toBe(30)
  })
})

describe('g7EquityMethodCalcModel suggested AJE', () => {
  it('aligns highlight and suggestion thresholds when materiality unset', () => {
    expect(isAmountOverMateriality(0.01, 0)).toBe(true)
    expect(isAmountOverMateriality(G714_PENNY_THRESHOLD, 0)).toBe(false)
    expect(isAmountOverMateriality(10, 20)).toBe(false)
    expect(isAmountOverMateriality(21, 20)).toBe(true)
  })

  it('skips penny noise when materiality unset', () => {
    expect(buildSuggestedAdjustments([emptyRow('甲', { incomeDifference: 0.004 })], 0)).toHaveLength(0)
    expect(buildSuggestedAdjustments([emptyRow('甲', { incomeDifference: 0.01 })], 0)).toHaveLength(2)
  })

  it('posts ⑩ by default; ⑮ pending does not post', () => {
    const rows = [
      emptyRow('甲', { incomeDifference: 100, unexplainedVariance: -50, unexplainedNature: 'pending' }),
    ]
    const lines = buildSuggestedAdjustments(rows, 0)
    expect(lines).toHaveLength(2)
    expect(lines.every((l) => l.source === 'incomeDifference')).toBe(true)
  })

  it('posts ⑮ only when nature maps to an account', () => {
    const rows = [
      emptyRow('甲', {
        incomeDifference: 0,
        unexplainedVariance: -50,
        unexplainedNature: 'impairment',
      }),
    ]
    const lines = buildSuggestedAdjustments(rows, 0)
    expect(lines).toHaveLength(2)
    expect(lines.some((l) => l.accountCode === '1512')).toBe(true)
    expect(resolveUnexplainedCounterAccount('impairment')?.code).toBe('1512')
  })

  it('can force-disable unexplained postings', () => {
    const rows = [
      emptyRow('甲', {
        incomeDifference: 10,
        unexplainedVariance: 50,
        unexplainedNature: 'investmentIncome',
      }),
    ]
    expect(buildSuggestedAdjustments(rows, 0, { includeUnexplainedVariance: false })).toHaveLength(2)
  })

  it('respects materiality level (skip under threshold)', () => {
    const rows = [emptyRow('甲', { incomeDifference: 10, unexplainedVariance: 5 })]
    expect(buildSuggestedAdjustments(rows, 20)).toHaveLength(0)
    expect(buildSuggestedAdjustments(rows, 8)).toHaveLength(2)
  })

  it('mergeSuggestedIntoG73 only replaces sourceKind drafts, keeps manual G7-14 refs', () => {
    const existing = [
      { seq: 1, description: '手工分录', accountCode: '1511', debitAmount: 1, creditAmount: 0, indexRef: '' },
      {
        seq: 2,
        description: '索引参见 G7-14',
        accountCode: '1511',
        debitAmount: 3,
        creditAmount: 0,
        indexRef: 'G7-14',
        remark: '人工确认',
      },
      {
        seq: 3,
        description: '【G7-14】旧建议',
        accountCode: '1511',
        debitAmount: 9,
        creditAmount: 0,
        indexRef: 'G7-14',
        sourceKind: G714_SUGGESTED_SOURCE_KIND,
        remark: `sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
      },
      {
        seq: 4,
        description: '【G7-13】廉价购买',
        accountCode: '1511',
        debitAmount: 5,
        creditAmount: 0,
        indexRef: 'G7-13',
        sourceKind: 'g7-13-bargain-suggested',
        remark: 'sourceKind=g7-13-bargain-suggested',
      },
    ]
    const suggested = toG73Entries(
      buildSuggestedAdjustments([emptyRow('甲', { incomeDifference: 20 })], 0),
    )
    const merged = mergeSuggestedIntoG73(existing, suggested)
    expect(merged.some((r) => r.description === '手工分录')).toBe(true)
    expect(merged.some((r) => r.description === '索引参见 G7-14')).toBe(true)
    expect(merged.some((r) => r.description === '【G7-13】廉价购买')).toBe(true)
    expect(merged.filter((r) => r.sourceKind === G714_SUGGESTED_SOURCE_KIND)).toHaveLength(2)
    expect(merged.every((r, i) => r.seq === i + 1)).toBe(true)
  })
})
