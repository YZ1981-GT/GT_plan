/**
 * G7-13 投资成本测试模型 — hydrate / recalc / G7-5 FV / 校验 / 廉价购买
 */
import { describe, it, expect } from 'vitest'
import {
  buildBargainSuggestedAdjustments,
  createEmptyInvestmentCostRow,
  extractNetAssetFvFromG75,
  hydrateInvestmentCostRows,
  parseInvestmentCostRowsPayload,
  recalcInvestmentCostRow,
  validateInvestmentCostRows,
} from '../g7InvestmentCostModel'

describe('g7InvestmentCostModel', () => {
  it('parse flat array / {rows} / string envelope', () => {
    expect(parseInvestmentCostRowsPayload([{ investeeName: 'A' }])).toHaveLength(1)
    expect(parseInvestmentCostRowsPayload({ rows: [{ investeeName: 'B' }] })).toHaveLength(1)
    expect(parseInvestmentCostRowsPayload(JSON.stringify([{ investeeName: 'C' }]))).toHaveLength(1)
    expect(parseInvestmentCostRowsPayload({ conclusion: 'x' })).toHaveLength(0)
  })

  it('recalc: initialCost / share / difference / nature', () => {
    const row = createEmptyInvestmentCostRow(1, '联营甲')
    row.consideration = 1000
    row.directCosts = 50
    row.netAssetFairValue = 3000
    row.investmentRatio = 0.3
    recalcInvestmentCostRow(row)
    expect(row.initialCost).toBe(1050)
    expect(row.shareOfNetAssets).toBe(900)
    expect(row.difference).toBe(150)
    expect(row.differenceNature).toBe('商誉')
  })

  it('recalc: negative difference → 营业外收入', () => {
    const row = createEmptyInvestmentCostRow(1, '联营乙')
    row.consideration = 500
    row.directCosts = 0
    row.netAssetFairValue = 3000
    row.investmentRatio = 0.3
    recalcInvestmentCostRow(row)
    expect(row.difference).toBe(-400)
    expect(row.differenceNature).toBe('营业外收入')
  })

  it('recalc: percent investmentRatio normalized to fraction', () => {
    const row = createEmptyInvestmentCostRow(1, '联营丙')
    row.consideration = 100
    row.netAssetFairValue = 1000
    row.investmentRatio = 30
    recalcInvestmentCostRow(row)
    expect(row.investmentRatio).toBe(0.3)
    expect(row.shareOfNetAssets).toBe(300)
  })

  it('hydrate flat rows and recalculates formulas', () => {
    const rows = hydrateInvestmentCostRows([
      {
        investeeName: '联营丁',
        investeeId: 'd1',
        consideration: 200,
        directCosts: 10,
        netAssetFairValue: 1000,
        investmentRatio: 0.4,
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].investeeId).toBe('d1')
    expect(rows[0].initialCost).toBe(210)
    expect(rows[0].shareOfNetAssets).toBe(400)
    expect(rows[0].difference).toBe(-190)
  })

  it('hydrate accepts page envelope {rows, conclusion}', () => {
    const rows = hydrateInvestmentCostRows({
      rows: [{ investeeName: 'E', consideration: 1, netAssetFairValue: 10, investmentRatio: 0.5 }],
      conclusion: 'ok',
    })
    expect(rows[0].shareOfNetAssets).toBe(5)
  })

  it('extractNetAssetFvFromG75 prefers audited equity/net assets', () => {
    const entries = extractNetAssetFvFromG75({
      groups: [{
        investeeName: '联营甲',
        investeeId: 'a1',
        rows: [
          { reportItem: '净利润', currentAmount: 10, auditStatus: '已审' },
          { reportItem: '所有者权益（净资产）', currentAmount: 5000, auditStatus: '已审' },
        ],
      }],
    })
    expect(entries).toHaveLength(1)
    expect(entries[0].bookNetAssets).toBe(5000)
    expect(entries[0].audited).toBe(true)
  })

  it('validate: missing ratio / nature mismatch / fv detail', () => {
    const row = createEmptyInvestmentCostRow(1, '联营戊')
    row.consideration = 100
    row.netAssetFairValue = 200
    row.investmentRatio = 0
    row.difference = 100
    row.differenceNature = '营业外收入'
    row.adjustedNetAssets = 200
    row.adjustedShareOfNetAssets = 50
    row.fvAdjustmentDetail = ''
    const issues = validateInvestmentCostRows([row])
    expect(issues.some(i => i.code === 'missing-ratio')).toBe(true)
    expect(issues.some(i => i.code === 'nature-mismatch-goodwill')).toBe(true)
    expect(issues.some(i => i.code === 'fv-detail-empty')).toBe(true)
  })

  it('recalc: adjustedShareOfNetAssets = adjustedNetAssets × ratio', () => {
    const row = createEmptyInvestmentCostRow(1, '联营庚')
    row.consideration = 100
    row.netAssetFairValue = 1000
    row.investmentRatio = 0.3
    row.adjustedNetAssets = 1200
    recalcInvestmentCostRow(row)
    expect(row.shareOfNetAssets).toBe(300)
    expect(row.adjustedShareOfNetAssets).toBe(360)
  })

  it('recalc: clears adjustedShare when adjustedNetAssets empty', () => {
    const row = createEmptyInvestmentCostRow(1, '联营辛')
    row.investmentRatio = 0.4
    row.adjustedNetAssets = 0
    row.adjustedShareOfNetAssets = 999
    recalcInvestmentCostRow(row)
    expect(row.adjustedShareOfNetAssets).toBe(0)
  })

  it('buildBargainSuggestedAdjustments: debit 1511 / credit 6301 balanced', () => {
    const row = createEmptyInvestmentCostRow(1, '联营己')
    row.difference = -250
    const lines = buildBargainSuggestedAdjustments([row])
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('1511')
    expect(lines[0].debitAmount).toBe(250)
    expect(lines[1].accountCode).toBe('6301')
    expect(lines[1].creditAmount).toBe(250)
    expect(lines[0].sourceKind).toBe('g7-13-bargain-suggested')
  })
})
