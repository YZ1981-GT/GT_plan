import { describe, expect, it } from 'vitest'

import {

  aggregateG10AdjustmentAjeRjeByRow,

  applyG10AdjustmentWritebacks,

  defaultG10AdjStore,

  g10RowClosingAdjusted,

  parseG10AdjStore,

  summarizeG10Adjustment,

} from '../g10AdjStorage'



describe('g10AdjStorage', () => {

  it('按回写行分别汇总 AJE/RJE 净额', () => {

    const wb = aggregateG10AdjustmentAjeRjeByRow([

      { entryType: 'AJE', accountCode: '2101', creditAmount: 100, debitAmount: 0, liabilityType: '衍生金融负债' },

      { entryType: 'RJE', accountCode: '2101', debitAmount: 20, creditAmount: 0, liabilityType: '衍生金融负债' },

      { accountCode: '6101', debitAmount: 100, creditAmount: 0 },

    ])

    expect(wb.byRow.book_derivative_liability).toEqual({ closingAje: 100, closingRje: -20 })

  })



  it('回写前先清零 (三) 分项 AJE/RJE', () => {

    const store = defaultG10AdjStore()

    store.book_other = { closingAJE: 999, closingRJE: 1 }

    const patched = applyG10AdjustmentWritebacks(store, {

      byRow: { book_trading_bond: { closingAje: 50, closingRje: 0 } },

    })

    expect(patched.book_other?.closingAJE).toBe(0)

    expect(patched.book_other?.closingRJE).toBe(0)

    expect(patched.book_trading_bond?.closingAJE).toBe(50)

  })



  it('旧 closingAdjustment 字段可迁移读取', () => {

    const closing = g10RowClosingAdjusted({

      closingUnadjusted: 100,

      closingAdjustment: 25,

    })

    expect(closing).toBe(125)

  })

  it('旧 periodCredit/periodDebit 可推导期末未审', () => {
    const store = parseG10AdjStore(JSON.stringify({
      book_other: {
        openingUnadjusted: 100,
        periodCredit: 30,
        periodDebit: 10,
      },
    }))
    expect(store.book_other?.closingUnadjusted).toBe(120)
    expect(g10RowClosingAdjusted(store.book_other)).toBe(120)
  })



  it('summarizeG10Adjustment 统计 AJE/RJE 与 6101 净额', () => {

    const s = summarizeG10Adjustment([

      { entryType: 'AJE', accountCode: '2101', creditAmount: 80, debitAmount: 0 },

      { entryType: 'AJE', accountCode: '6101', debitAmount: 80, creditAmount: 0 },

      { entryType: 'RJE', accountCode: '2101', debitAmount: 10, creditAmount: 0 },

      { entryType: 'RJE', accountCode: '2202', creditAmount: 10, debitAmount: 0 },

    ])

    expect(s.rowCount).toBe(4)

    expect(s.ajeCount).toBe(2)

    expect(s.rjeCount).toBe(2)

    expect(s.net2101).toBe(70)

    expect(s.fvPlNet).toBe(80)

    expect(s.balanceDiff).toBe(0)

  })

})

