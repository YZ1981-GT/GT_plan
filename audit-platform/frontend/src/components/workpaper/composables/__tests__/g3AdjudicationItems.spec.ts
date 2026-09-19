/**
 * G3-1 调整回写辅助单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  applyG3AdjustmentWriteback,
  applyG3DetailSyncToAdjStore,
  aggregateG3DetailByInvestee,
  computeG3NetAdjustments,
  computeG3AgingSummary,
  G3_ADJ_WRITEBACK_ID,
  G3_ADJ_WRITEBACK_INVESTEE,
  parseG3AdjStore,
} from '../g3AdjudicationItems'

describe('g3AdjudicationItems', () => {
  it('computeG3NetAdjustments 仅汇总 1131 借−贷，并区分 AJE/RJE', () => {
    const { netAJE, netRJE } = computeG3NetAdjustments([
      { entryType: 'AJE', accountCode: '1131', debitAmount: 1000, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '1131', debitAmount: 0, creditAmount: 200 },
      { entryType: 'RJE', accountCode: '113101', debitAmount: 50, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '6001', debitAmount: 0, creditAmount: 800 },
    ])
    expect(netAJE).toBe(800)
    expect(netRJE).toBe(50)
  })

  it('computeG3NetAdjustments 支持 D4 类别字段与科目名称匹配', () => {
    const { netAJE, netRJE } = computeG3NetAdjustments([
      { category: '账项调整', accountName: '应收股利', debitAmount: 300, creditAmount: 0 },
      { category: '报表调整', accountCode: '1131', debitAmount: 0, creditAmount: 80 },
      { category: '账项调整', accountCode: '6111', debitAmount: 0, creditAmount: 300 },
    ])
    expect(netAJE).toBe(300)
    expect(netRJE).toBe(-80)
  })

  it('applyG3AdjustmentWriteback 新建账项调整汇总行并可幂等覆盖', () => {
    const once = applyG3AdjustmentWriteback([], 100, -20)
    expect(once).toHaveLength(1)
    expect(once[0].id).toBe(G3_ADJ_WRITEBACK_ID)
    expect(once[0].investeeName).toBe(G3_ADJ_WRITEBACK_INVESTEE)
    expect(once[0].closingAJE).toBe(100)
    expect(once[0].closingRJE).toBe(-20)
    expect(once[0].remark).toContain('G3-3')

    const twice = applyG3AdjustmentWriteback(once, 30, 0)
    expect(twice).toHaveLength(1)
    expect(twice[0].closingAJE).toBe(30)
    expect(twice[0].closingRJE).toBe(0)
  })

  it('parseG3AdjStore 容错非法 JSON，并补齐 reasonAnalysis', () => {
    expect(parseG3AdjStore(null)).toEqual([])
    expect(parseG3AdjStore('not-json')).toEqual([])
    expect(parseG3AdjStore('{"a":1}')).toEqual([])
    const rows = parseG3AdjStore(JSON.stringify([
      { id: 'r1', investeeName: '甲', openingUnadjusted: 10 },
    ]))
    expect(rows).toHaveLength(1)
    expect(rows[0].reasonAnalysis).toBe('')
    expect(rows[0].openingUnadjusted).toBe(10)
  })

  it('computeG3AgingSummary 按逾期≥365天拆分一年内/一年以上', () => {
    const asOf = new Date('2020-12-31')
    const overdue = JSON.stringify([
      {
        investeeName: '甲',
        receivableAmount: 400,
        agreedPaymentDate: '2019-06-01',
      },
      {
        investeeName: '乙',
        receivableAmount: 100,
        agreedPaymentDate: '2020-11-01',
      },
    ])
    const summary = computeG3AgingSummary(1000, overdue, asOf)
    expect(summary.over1YearAmount).toBe(400)
    expect(summary.within1YearAmount).toBe(600)
    expect(summary.over1YearCount).toBe(1)
    expect(summary.source).toBe('g3-5')
  })

  it('computeG3AgingSummary 支持滚动态期末金额（无 receivableAmount）', () => {
    const asOf = new Date('2020-12-31')
    const overdue = JSON.stringify([
      {
        investeeName: '甲',
        openingBalance: 300,
        periodDebit: 100,
        periodCredit: 0,
        agreedPaymentDate: '2019-01-01',
      },
    ])
    const summary = computeG3AgingSummary(1000, overdue, asOf)
    expect(summary.over1YearAmount).toBe(400)
    expect(summary.within1YearAmount).toBe(600)
  })

  it('aggregateG3DetailByInvestee 按被投资方合并宣告/收回', () => {
    const raw = JSON.stringify([
      { investeeName: '甲', shareholdingRatio: 20, dividendReceivable: 100, receivedAmount: 40 },
      { investeeName: '甲', shareholdingRatio: 20, dividendReceivable: 50, receivedAmount: 10 },
      { investeeName: '乙', shareholdingRatio: 10, totalDividend: 80, receivedAmount: 0 },
      { investeeName: '', dividendReceivable: 999 },
    ])
    const aggs = aggregateG3DetailByInvestee(raw)
    expect(aggs).toHaveLength(2)
    const jia = aggs.find((a) => a.investeeName === '甲')!
    expect(jia.currentDeclared).toBe(150)
    expect(jia.currentReceived).toBe(50)
    expect(jia.shareholdingRatio).toBe(20)
    const yi = aggs.find((a) => a.investeeName === '乙')!
    expect(yi.currentDeclared).toBe(80)
  })

  it('applyG3DetailSyncToAdjStore 更新宣告/收回并保留 AJE/RJE，不碰账项调整汇总', () => {
    const store = [
      {
        id: 'inv-1',
        investeeName: '甲',
        shareholdingRatio: 15,
        openingUnadjusted: 1000,
        openingAJE: 10,
        openingRJE: 0,
        currentDeclared: 1,
        currentReceived: 1,
        closingAJE: 5,
        closingRJE: -2,
        remark: 'keep',
        indexRef: 'idx',
        reasonAnalysis: 'r',
      },
      {
        id: G3_ADJ_WRITEBACK_ID,
        investeeName: G3_ADJ_WRITEBACK_INVESTEE,
        shareholdingRatio: 0,
        openingUnadjusted: 0,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 0,
        currentReceived: 0,
        closingAJE: 99,
        closingRJE: 1,
        remark: 'adj',
        indexRef: '',
        reasonAnalysis: '',
      },
    ]
    const { next, added, updated } = applyG3DetailSyncToAdjStore(store, [
      { investeeName: '甲', shareholdingRatio: 20, currentDeclared: 500, currentReceived: 200 },
      { investeeName: '丙', shareholdingRatio: 5, currentDeclared: 30, currentReceived: 0 },
    ])
    expect(updated).toBe(1)
    expect(added).toBe(1)
    const jia = next.find((r) => r.id === 'inv-1')!
    expect(jia.currentDeclared).toBe(500)
    expect(jia.currentReceived).toBe(200)
    expect(jia.openingUnadjusted).toBe(1000)
    expect(jia.closingAJE).toBe(5)
    expect(jia.closingRJE).toBe(-2)
    expect(jia.remark).toBe('keep')
    const wb = next.find((r) => r.id === G3_ADJ_WRITEBACK_ID)!
    expect(wb.closingAJE).toBe(99)
    expect(next.some((r) => r.investeeName === '丙')).toBe(true)
  })
})
