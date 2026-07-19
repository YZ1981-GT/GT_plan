import { describe, expect, it } from 'vitest'
import {
  applyFinancialInfoToG714Payload,
  applyG72EquityToG714Payload,
  applyG74InvesteesToG714Payload,
  applyGoodwillFvDetailsToRows,
  applyInternalElimToG714Payload,
  applyInvestmentCostToG714Payload,
  applyPolicyAdjToG714Payload,
  addGoodwillFvDetail,
  buildG714SyncPreview,
  loadEquityInvesteeNames,
  loadEquityInvestees,
  loadSubsidiaryInvestees,
  matchInvestee,
  parseChecklistJson,
  pickDefinedNum,
  removeGoodwillFvDetail,
  stampLastCrossSheetSync,
} from '../g7EquityMethodCrossSheet'

describe('g7EquityMethodCrossSheet', () => {
  it('parses checklist json string', () => {
    expect(parseChecklistJson('{"a":1}')).toEqual({ a: 1 })
    expect(parseChecklistJson('{bad')).toBeNull()
  })

  it('pickDefinedNum treats 0 as valid and skips empty', () => {
    expect(pickDefinedNum(0, 5000)).toBe(0)
    expect(pickDefinedNum(null, undefined, '', 5000)).toBe(5000)
    expect(pickDefinedNum(undefined, 0, 100)).toBe(0)
  })

  it('loads equity investee names from G7-4 rows', () => {
    const names = loadEquityInvesteeNames(JSON.stringify([
      { investeeName: '子A', groupType: 'subsidiary', accountingMethod: '成本法' },
      { investeeName: '联营B', groupType: 'associate', accountingMethod: '权益法' },
      { investeeName: '合营C', groupType: 'joint_venture', accountingMethod: '权益法' },
      { investeeName: '联营B', groupType: 'associate', accountingMethod: '权益法' },
    ]))
    expect(names).toEqual(['联营B', '合营C'])
  })

  it('loads equity investees with G7-4 row id as investeeId', () => {
    const investees = loadEquityInvestees([
      { id: 'id-sub', investeeName: '子A', groupType: 'subsidiary', accountingMethod: '成本法' },
      { id: 'id-b', investeeName: '联营B', groupType: 'associate', accountingMethod: '权益法' },
      { id: 'id-c', investeeName: '合营C', groupType: 'joint_venture', accountingMethod: '权益法' },
      { id: 'id-b', investeeName: '联营B-改名', groupType: 'associate', accountingMethod: '权益法' },
    ])
    expect(investees).toEqual([
      { name: '联营B', investeeId: 'id-b' },
      { name: '合营C', investeeId: 'id-c' },
    ])
  })

  it('applyG74InvesteesToG714Payload creates rows and backfills investeeId', () => {
    const existing = {
      groups: [{
        investeeName: '联营B',
        rows: [{
          id: '1', investeeName: '联营B',
          reportedNetProfit: 100, internalTransactionAdj: 0, fvDepreciationAdj: 0,
          accountingPolicyAdj: 0, otherAdj: 0, investmentRatio: 0.3,
          confirmedIncome: 0, dividendDistributed: 0, openingBalance: 0,
          ociChange: 0, otherEquityChange: 0, goodwill: 0, cumulativeFvAdj: 0,
          impairment: 0, costOpening: 0, costChange: 0, pnlAdjOpening: 0, pnlAdjChange: 0,
          ociBalOpening: 0, otherEqBalOpening: 0, auditedNetAssets: 0,
        }],
      }],
      rows: [],
    }
    const result = applyG74InvesteesToG714Payload(existing, [
      { id: 'inv-b', investeeName: '联营B', groupType: 'associate', accountingMethod: '权益法' },
      { id: 'inv-c', investeeName: '合营C', groupType: 'joint_venture', accountingMethod: '权益法' },
    ])
    expect(result.ok).toBe(true)
    expect(result.payload.groups).toHaveLength(2)
    const b = result.payload.groups.find((g: any) => g.investeeName === '联营B')
    const c = result.payload.groups.find((g: any) => g.investeeName === '合营C')
    expect(b.investeeId).toBe('inv-b')
    expect(b.rows[0].investeeId).toBe('inv-b')
    expect(b.rows[0].reportedNetProfit).toBe(100)
    expect(c.investeeId).toBe('inv-c')
    expect(c.rows[0].investeeId).toBe('inv-c')
  })

  it('loads subsidiary investees for G7-10 with percent→fraction conversion', () => {
    const opts = loadSubsidiaryInvestees([
      {
        investeeName: '子A',
        groupType: 'subsidiary',
        directHoldingRatio: 60,
        indirectHoldingRatio: 10,
        investmentAmount: 8_000_000,
        ratioScale: 'percent',
      },
      { investeeName: '联营B', groupType: 'associate', directHoldingRatio: 30 },
    ])
    expect(opts).toHaveLength(1)
    expect(opts[0]).toMatchObject({
      name: '子A',
      shareholdingRatio: 0.7,
      carryingAmount: 8_000_000,
    })
  })

  it('writes accountingPolicyAdj into existing G7-14 row and recalcs', () => {
    const payload = {
      materialityLevel: 0,
      conclusion: '',
      groups: [{
        investeeName: '联营B',
        rows: [{
          id: '1',
          seq: 1,
          investeeName: '联营B',
          reportedNetProfit: 1000,
          internalTransactionAdj: 0,
          fvDepreciationAdj: 0,
          accountingPolicyAdj: 0,
          otherAdj: 0,
          adjustedNetProfit: 0,
          investmentRatio: 0.3,
          equityShare: 0,
          confirmedIncome: 0,
          incomeDifference: 0,
          ociChange: 0,
          ociShare: 0,
          otherEquityChange: 0,
          otherEquityShare: 0,
          dividendDistributed: 0,
          openingBalance: 0,
          closingBalance: 0,
          auditConclusion: '无差异',
        }],
      }],
      rows: [],
    }
    const result = applyPolicyAdjToG714Payload(payload, '联营B', 50)
    expect(result.ok).toBe(true)
    const row = result.payload.groups[0].rows[0]
    expect(row.accountingPolicyAdj).toBe(50)
    expect(row.adjustedNetProfit).toBe(1050)
    expect(row.equityShare).toBe(315)
  })

  it('creates stub G7-14 row when investee missing', () => {
    const result = applyPolicyAdjToG714Payload(null, '新联营', -20)
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].investeeName).toBe('新联营')
    expect(result.payload.groups[0].rows[0].accountingPolicyAdj).toBe(-20)
  })

  it('applies G7-5 financial info to reportedNetProfit and auditedNetAssets', () => {
    const result = applyFinancialInfoToG714Payload(null, {
      groups: [{
        investeeName: '联营B',
        rows: [
          { reportItem: '净利润', currentAmount: 2_000, auditStatus: '已审' },
          { reportItem: '所有者权益（净资产）', currentAmount: 10_000, auditStatus: '已审' },
        ],
      }],
    })
    expect(result.ok).toBe(true)
    const row = result.payload.groups[0].rows[0]
    expect(row.reportedNetProfit).toBe(2000)
    expect(row.auditedNetAssets).toBe(10000)
  })

  it('G7-5 skips unaudited items by default and reports warnings', () => {
    const result = applyFinancialInfoToG714Payload(null, {
      groups: [{
        investeeName: '联营B',
        rows: [
          { reportItem: '净利润', currentAmount: 2_000, auditStatus: '未审' },
          { reportItem: '所有者权益（净资产）', currentAmount: 10_000, auditStatus: '待确认' },
        ],
      }],
    })
    expect(result.ok).toBe(false)
    expect(result.warnings?.[0]).toMatch(/未审|待确认/)
    expect(result.message).toMatch(/未审|待确认/)
  })

  it('G7-5 can force-include unaudited when opted in', () => {
    const result = applyFinancialInfoToG714Payload(null, {
      groups: [{
        investeeName: '联营B',
        rows: [
          { reportItem: '净利润', currentAmount: 2_000, auditStatus: '未审' },
          { reportItem: '所有者权益（净资产）', currentAmount: 10_000, auditStatus: '待确认' },
        ],
      }],
    }, { includeUnaudited: true })
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].reportedNetProfit).toBe(2000)
    expect(result.payload.groups[0].rows[0].auditedNetAssets).toBe(10000)
  })

  it('G7-5 still accepts legacy rows without auditStatus', () => {
    const result = applyFinancialInfoToG714Payload(null, {
      groups: [{
        investeeName: '联营B',
        rows: [
          { reportItem: '净利润', currentAmount: 900 },
          { reportItem: '所有者权益（净资产）', currentAmount: 8_000 },
        ],
      }],
    })
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].reportedNetProfit).toBe(900)
  })

  it('applies G7-15 internal elim sum to internalTransactionAdj', () => {
    const result = applyInternalElimToG714Payload(
      { groups: [], rows: [] },
      {
        rows: [
          { investeeName: '联营B', currentChange: 30, eliminationAmount: 100 },
          { investeeName: '联营B', currentChange: 20, eliminationAmount: 50 },
        ],
      },
    )
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].internalTransactionAdj).toBe(50)
  })

  it('G7-15 uses currentChange=0 instead of falling back to eliminationAmount', () => {
    const result = applyInternalElimToG714Payload(
      { groups: [], rows: [] },
      { rows: [{ investeeName: '联营B', currentChange: 0, eliminationAmount: 100 }] },
    )
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].internalTransactionAdj).toBe(0)
  })

  it('G7-15 falls back to eliminationAmount when currentChange absent', () => {
    const result = applyInternalElimToG714Payload(
      { groups: [], rows: [] },
      { rows: [{ investeeName: '联营B', eliminationAmount: 100 }] },
    )
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].internalTransactionAdj).toBe(100)
  })

  it('applies G7-13 difference into goodwillFvDetails and writes back columns', () => {
    const result = applyInvestmentCostToG714Payload(null, {
      rows: [{
        investeeName: '联营B',
        difference: 800,
        differenceNature: '商誉',
        shareOfNetAssets: 1000,
        adjustedShareOfNetAssets: 1200,
        investmentRatio: 0.3,
        indexRef: 'G7-13',
      }],
    })
    expect(result.ok).toBe(true)
    expect(result.payload.goodwillFvDetails).toHaveLength(2)
    const row = result.payload.groups[0].rows[0]
    expect(row.goodwill).toBe(800)
    expect(row.cumulativeFvAdj).toBe(200)
    expect(row.investmentRatio).toBe(0.3)
  })

  it('G7-13 does not invent FV when adjustedShareOfNetAssets is absent', () => {
    const result = applyInvestmentCostToG714Payload(null, {
      rows: [{
        investeeName: '联营B',
        difference: 800,
        differenceNature: '商誉',
        shareOfNetAssets: 1000,
        investmentRatio: 0.3,
        indexRef: 'G7-13',
      }],
    })
    expect(result.ok).toBe(true)
    expect(result.payload.goodwillFvDetails).toHaveLength(1)
    expect(result.payload.goodwillFvDetails[0].kind).toBe('goodwill')
    expect(result.payload.groups[0].rows[0].cumulativeFvAdj).toBe(0)
  })

  it('applies G7-2 equity rows to opening / pnl / dividend', () => {
    const result = applyG72EquityToG714Payload(null, [
      {
        section: 'equity',
        investeeName: '联营B',
        relationship: 'associate',
        investmentRatio: 30,
        openingRatio: 30,
        closingRatio: 30,
        openingAmount: 5_000,
        profitLossAdjustment: 300,
        dividendReceived: 50,
        otherComprehensiveIncome: 60,
        otherEquityChange: 0,
        costIncrease: 100,
        costDecrease: 0,
      },
    ])
    expect(result.ok).toBe(true)
    const row = result.payload.groups[0].rows[0]
    expect(row.investmentRatio).toBe(0.3)
    expect(row.openingBalance).toBe(5000)
    expect(row.pnlAdjChange).toBe(300)
    expect(row.confirmedIncome).toBe(300)
    expect(row.dividendDistributed).toBe(50)
    expect(row.costChange).toBe(100)
    expect(row.ociChange).toBe(200) // 60 / 0.3
  })

  it('G7-2 keeps audited opening 0 when amount is zero', () => {
    const result = applyG72EquityToG714Payload(null, [
      {
        section: 'equity',
        investeeName: '联营B',
        relationship: 'associate',
        openingRatio: 30,
        closingRatio: 30,
        openingAmount: 0,
        profitLossAdjustment: 0,
        dividendReceived: 0,
      },
    ])
    expect(result.ok).toBe(true)
    expect(result.payload.groups[0].rows[0].openingBalance).toBe(0)
  })

  it('add/remove goodwillFvDetails and rewrite row columns', () => {
    let payload: any = { groups: [], rows: [], goodwillFvDetails: [] }
    const added = addGoodwillFvDetail(payload, {
      investeeName: '联营B',
      kind: 'goodwill',
      description: '手工商誉',
      amount: 500,
      indexRef: '',
    })
    expect(added.ok).toBe(true)
    payload = added.payload
    expect(payload.groups[0].rows[0].goodwill).toBe(500)

    const removed = removeGoodwillFvDetail(payload, payload.goodwillFvDetails[0].id)
    expect(removed.payload.groups[0].rows[0].goodwill).toBe(0)
  })

  it('applyGoodwillFvDetailsToRows aggregates by investee', () => {
    const payload = {
      groups: [],
      rows: [],
      goodwillFvDetails: [
        { id: '1', investeeName: '联营B', kind: 'goodwill', description: '', amount: 100, indexRef: '' },
        { id: '2', investeeName: '联营B', kind: 'fvAdj', description: '', amount: 40, indexRef: '' },
        { id: '3', investeeName: '联营B', kind: 'goodwill', description: '', amount: 50, indexRef: '' },
      ],
    }
    applyGoodwillFvDetailsToRows(payload)
    const row = payload.groups[0].rows[0]
    expect(row.goodwill).toBe(150)
    expect(row.cumulativeFvAdj).toBe(40)
  })

  it('clears old investee goodwill when detail is renamed', () => {
    const payload: any = {
      groups: [
        {
          investeeName: '联营A',
          rows: [{
            id: 'a', seq: 1, investeeName: '联营A',
            reportedNetProfit: 0, internalTransactionAdj: 0, fvDepreciationAdj: 0,
            accountingPolicyAdj: 0, otherAdj: 0, investmentRatio: 0.3,
            confirmedIncome: 0, dividendDistributed: 0, openingBalance: 0,
            ociChange: 0, otherEquityChange: 0, goodwill: 500, cumulativeFvAdj: 0,
            impairment: 0, costOpening: 0, costChange: 0, pnlAdjOpening: 0, pnlAdjChange: 0,
            ociBalOpening: 0, otherEqBalOpening: 0, auditedNetAssets: 0,
          }],
        },
        {
          investeeName: '联营B',
          rows: [{
            id: 'b', seq: 1, investeeName: '联营B',
            reportedNetProfit: 0, internalTransactionAdj: 0, fvDepreciationAdj: 0,
            accountingPolicyAdj: 0, otherAdj: 0, investmentRatio: 0.3,
            confirmedIncome: 0, dividendDistributed: 0, openingBalance: 0,
            ociChange: 0, otherEquityChange: 0, goodwill: 0, cumulativeFvAdj: 0,
            impairment: 0, costOpening: 0, costChange: 0, pnlAdjOpening: 0, pnlAdjChange: 0,
            ociBalOpening: 0, otherEqBalOpening: 0, auditedNetAssets: 0,
          }],
        },
      ],
      rows: [],
      goodwillFvDetails: [
        { id: '1', investeeName: '联营B', kind: 'goodwill', description: '改名后', amount: 500, indexRef: '' },
      ],
    }
    applyGoodwillFvDetailsToRows(payload, ['联营A'])
    const rowA = payload.groups.find((g: any) => g.investeeName === '联营A').rows[0]
    const rowB = payload.groups.find((g: any) => g.investeeName === '联营B').rows[0]
    expect(rowA.goodwill).toBe(0)
    expect(rowB.goodwill).toBe(500)
  })

  it('FV rollforward recalcs amount and writes fvDepreciationAdj', () => {
    const payload: any = {
      groups: [],
      rows: [],
      goodwillFvDetails: [{
        id: '1',
        investeeName: '联营B',
        kind: 'fvAdj',
        description: '固定资产FV',
        amount: 0,
        openingUnamortized: 200,
        currentDepreciationAdj: 30,
        otherChange: 10,
        indexRef: '',
      }],
    }
    applyGoodwillFvDetailsToRows(payload)
    const detail = payload.goodwillFvDetails[0]
    expect(detail.amount).toBe(180) // 200+10-30
    const row = payload.groups[0].rows[0]
    expect(row.cumulativeFvAdj).toBe(180)
    expect(row.fvDepreciationAdj).toBe(30)
  })

  it('buildG714SyncPreview lists changed fields', () => {
    const before = {
      groups: [{
        investeeName: '联营B',
        rows: [{ investeeName: '联营B', reportedNetProfit: 100, auditedNetAssets: 1000, goodwill: 0 }],
      }],
    }
    const after = {
      groups: [{
        investeeName: '联营B',
        rows: [{ investeeName: '联营B', reportedNetProfit: 200, auditedNetAssets: 1000, goodwill: 50 }],
      }],
    }
    const lines = buildG714SyncPreview(before, after)
    expect(lines.some((l) => l.field === 'reportedNetProfit' && l.before === 100 && l.after === 200)).toBe(true)
    expect(lines.some((l) => l.field === 'goodwill' && l.after === 50)).toBe(true)
    expect(lines.some((l) => l.field === 'auditedNetAssets')).toBe(false)
  })

  it('stampLastCrossSheetSync writes meta onto payload', () => {
    const payload: any = {}
    const meta = stampLastCrossSheetSync(payload, ['G7-5', 'G7-15'], 3)
    expect(payload.lastCrossSheetSync).toEqual(meta)
    expect(meta.sources).toEqual(['G7-5', 'G7-15'])
    expect(meta.changeCount).toBe(3)
    expect(meta.at).toBeTruthy()
  })

  it('matches investee by investeeId even when names differ', () => {
    const payload = {
      groups: [{
        investeeName: '旧名称',
        investeeId: 'inv-1',
        rows: [{
          id: '1', investeeName: '旧名称', investeeId: 'inv-1',
          reportedNetProfit: 0, internalTransactionAdj: 0, fvDepreciationAdj: 0,
          accountingPolicyAdj: 0, otherAdj: 0, investmentRatio: 0.3,
          confirmedIncome: 0, dividendDistributed: 0, openingBalance: 0,
          ociChange: 0, otherEquityChange: 0, goodwill: 0, cumulativeFvAdj: 0,
          impairment: 0, costOpening: 0, costChange: 0, pnlAdjOpening: 0, pnlAdjChange: 0,
          ociBalOpening: 0, otherEqBalOpening: 0, auditedNetAssets: 0,
        }],
      }],
      rows: [],
    }
    const result = applyFinancialInfoToG714Payload(payload, {
      groups: [{
        investeeName: '新名称',
        investeeId: 'inv-1',
        rows: [
          { reportItem: '净利润', currentAmount: 888, auditStatus: '已审' },
        ],
      }],
    })
    expect(result.ok).toBe(true)
    expect(result.payload.groups).toHaveLength(1)
    expect(result.payload.groups[0].investeeId).toBe('inv-1')
    expect(result.payload.groups[0].rows[0].reportedNetProfit).toBe(888)
  })

  it('matchInvestee prefers id and falls back to name', () => {
    expect(matchInvestee(
      { investeeName: 'A', investeeId: '1' },
      { investeeName: 'B', investeeId: '1' },
    )).toBe(true)
    expect(matchInvestee(
      { investeeName: 'A', investeeId: '1' },
      { investeeName: 'A', investeeId: '2' },
    )).toBe(false)
    expect(matchInvestee(
      { investeeName: ' A ', investeeId: '' },
      { investeeName: 'A' },
    )).toBe(true)
  })
})
