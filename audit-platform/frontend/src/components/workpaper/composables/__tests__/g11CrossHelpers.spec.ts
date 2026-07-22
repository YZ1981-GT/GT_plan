import { describe, it, expect } from 'vitest'
import {
  extractEquityIncomeSeedsFromG714,
  mergeG714SeedsIntoDetailRows,
  computeG11DetailCrossCheck,
  mergeLedgerSeedsIntoDetailRows,
} from '../g11CrossHelpers'
import { g11TbRowPlAmount } from '../g11TbResolve'

describe('g11CrossHelpers', () => {
  it('extractEquityIncomeSeedsFromG714 解析确认投资收益', () => {
    const seeds = extractEquityIncomeSeedsFromG714({
      rows: [
        {
          investeeName: '甲公司',
          confirmedIncome: 100000,
          equityShare: 95000,
          incomeDifference: 5000,
        },
        { investeeName: '', confirmedIncome: 1 },
      ],
    })
    expect(seeds).toHaveLength(1)
    expect(seeds[0].investeeName).toBe('甲公司')
    expect(seeds[0].currentUnadjusted).toBe(100000)
    expect(seeds[0].incomeDifference).toBe(5000)
  })

  it('mergeG714SeedsIntoDetailRows 按被投资单位增行并移除空骨架', () => {
    const merged = mergeG714SeedsIntoDetailRows(
      [
        {
          id: 'sk',
          rowKey: 'equity_method',
          itemName: '权益法核算的长期股权投资收益',
          isSkeleton: true,
          investeeName: '',
          currentUnadjusted: 0,
        },
      ],
      [
        {
          investeeName: '甲公司',
          currentUnadjusted: 80000,
          equityShare: 78000,
          incomeDifference: 2000,
          reasonIndex: 'wp:G7-14',
        },
      ],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0].investeeName).toBe('甲公司')
    expect(merged[0].currentUnadjusted).toBe(80000)
    expect(merged[0].isSkeleton).toBe(false)
    expect(String(merged[0].reasonIndex)).toContain('差异')
  })

  it('empty_only 不覆盖已有未审数', () => {
    const merged = mergeG714SeedsIntoDetailRows(
      [
        {
          rowKey: 'equity_method',
          investeeName: '甲公司',
          currentUnadjusted: 50000,
          isSkeleton: false,
        },
      ],
      [
        {
          investeeName: '甲公司',
          currentUnadjusted: 80000,
          equityShare: 0,
          incomeDifference: 0,
          reasonIndex: 'wp:G7-14',
        },
      ],
      'empty_only',
    )
    expect(merged[0].currentUnadjusted).toBe(50000)
  })

  it('computeG11DetailCrossCheck 检测 G11-1/G11-2 不一致', () => {
    const adj = JSON.stringify({
      equity_method: { currentUnadjusted: 100, currentAdjustment: 0 },
      other: { currentUnadjusted: 0, currentAdjustment: 0 },
    })
    const detail = JSON.stringify([
      { rowKey: 'equity_method', currentUnadjusted: 80, currentAdjustment: 0 },
    ])
    const check = computeG11DetailCrossCheck(adj, detail)
    expect(check.isBalanced).toBe(false)
    expect(check.diff).toBe(20)
    expect(check.message).toContain('不一致')
  })

  it('mergeLedgerSeedsIntoDetailRows 按 rowKey 预填未审数', () => {
    const merged = mergeLedgerSeedsIntoDetailRows(
      [{ rowKey: 'trading_hold', itemName: '交易性金融资产持有期间的投资收益', currentUnadjusted: 0, isSkeleton: true }],
      [{
        rowKey: 'trading_hold',
        itemName: '交易性金融资产持有期间的投资收益',
        investeeName: '',
        currentUnadjusted: 12000,
        priorUnadjusted: 0,
        reasonIndex: '序时账/2025',
      }],
    )
    expect(merged[0].currentUnadjusted).toBe(12000)
  })
})

describe('g11TbResolve', () => {
  it('g11TbRowPlAmount 取贷−借', () => {
    expect(g11TbRowPlAmount({ credit_amount: 100, debit_amount: 30 })).toBe(70)
  })
})
