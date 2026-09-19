/**
 * G11-2/G11-3 分项回写与匹配 — 单测
 */
import { describe, it, expect } from 'vitest'
import {
  aggregateG11AdjustmentByRow,
  applyG11AdjustmentWriteback,
  calcG11AdjustmentNet,
  defaultG11AdjStore,
  summarizeG11Adjustment,
} from '../g11AdjStorage'
import { inferG11AdjudicationRowKey } from '../g11AccountMatch'
import { isChangeRateExceeding, calcChangeRate } from '../useG11FormulaEngine'

describe('g11AccountMatch', () => {
  it('显式 rowKey 优先', () => {
    expect(inferG11AdjudicationRowKey({
      adjudicationRowKey: 'equity_method',
      description: '处置交易性金融资产',
    })).toBe('equity_method')
  })

  it('从摘要推断权益法 / 交易性处置', () => {
    expect(inferG11AdjudicationRowKey({ description: '补提联营企业权益法损益' })).toBe('equity_method')
    expect(inferG11AdjudicationRowKey({ description: '处置交易性金融资产损益更正' })).toBe('trading_dispose')
  })

  it('无法匹配时回落 other', () => {
    expect(inferG11AdjudicationRowKey({ description: '杂项调整' })).toBe('other')
  })
})

describe('g11AdjStorage 分项回写', () => {
  it('6111 账项调整按回写行汇总（贷−借）', () => {
    const byRow = aggregateG11AdjustmentByRow([
      {
        category: '账项调整',
        accountCode: '6111',
        creditAmount: 100,
        debitAmount: 0,
        adjudicationRowKey: 'equity_method',
      },
      {
        category: '账项调整',
        accountCode: '6111',
        creditAmount: 0,
        debitAmount: 30,
        description: '处置交易性金融资产',
      },
      {
        category: '报表调整',
        accountCode: '6111',
        creditAmount: 999,
        debitAmount: 0,
        adjudicationRowKey: 'other',
      },
      {
        category: '账项调整',
        accountCode: '1002',
        debitAmount: 70,
        creditAmount: 0,
      },
    ])
    expect(byRow.equity_method).toBe(100)
    expect(byRow.trading_dispose).toBe(-30)
    expect(byRow.other).toBe(0)
  })

  it('applyG11AdjustmentWriteback 写入 currentAdjustment', () => {
    const store = applyG11AdjustmentWriteback(defaultG11AdjStore(), {
      equity_method: 50,
      other: -10,
    })
    expect(store.equity_method?.currentAdjustment).toBe(50)
    expect(store.other?.currentAdjustment).toBe(-10)
  })

  it('calcG11AdjustmentNet 排除报表调整', () => {
    expect(calcG11AdjustmentNet([
      { accountCode: '6111', creditAmount: 80, debitAmount: 0, category: '账项调整' },
      { accountCode: '6111', creditAmount: 20, debitAmount: 0, category: '报表调整' },
    ])).toBe(80)
  })

  it('summarize 区分 AJE/RJE', () => {
    const s = summarizeG11Adjustment([
      { category: '账项调整', accountCode: '6111', creditAmount: 10, debitAmount: 0 },
      { category: '报表调整', accountCode: '6111', creditAmount: 5, debitAmount: 0 },
    ])
    expect(s.ajeCount).toBe(1)
    expect(s.rjeCount).toBe(1)
    expect(s.netAje6111).toBe(10)
    expect(s.netRje6111).toBe(5)
  })
})

describe('G11-2 变动率阈值', () => {
  it('|变动率|>20% 触发高亮', () => {
    const rate = calcChangeRate(100, 130)
    expect(rate).toBeCloseTo(0.3)
    expect(isChangeRateExceeding(rate, 0.2)).toBe(true)
    expect(isChangeRateExceeding(calcChangeRate(100, 110), 0.2)).toBe(false)
  })
})
