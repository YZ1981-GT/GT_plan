/**
 * g8AdjStorage / summarizeG8Adjustment — G8-3 汇总与回写
 */
import { describe, it, expect } from 'vitest'
import {
  calcG8AdjustmentNet,
  summarizeG8Adjustment,
  aggregateG8AdjustmentWriteback,
  applyG8AdjustmentWriteback,
  defaultG8AdjStore,
} from '../g8AdjStorage'

describe('calcG8AdjustmentNet', () => {
  it('仅汇总 1503 借−贷', () => {
    const net = calcG8AdjustmentNet([
      { accountCode: '1503', debitAmount: 100, creditAmount: 0 },
      { accountCode: '4002', debitAmount: 0, creditAmount: 100 },
      { accountCode: '1503', debitAmount: 0, creditAmount: 30 },
    ])
    expect(net).toBe(70)
  })

  it('缺省科目按 1503', () => {
    expect(calcG8AdjustmentNet([{ debitAmount: 50, creditAmount: 10 }])).toBe(40)
  })
})

describe('summarizeG8Adjustment', () => {
  it('汇总借贷、AJE/RJE 与 OCI', () => {
    const s = summarizeG8Adjustment([
      { entryType: 'AJE', accountCode: '1503', debitAmount: 200, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '4002', debitAmount: 0, creditAmount: 200 },
      { entryType: 'RJE', accountCode: '1503', debitAmount: 0, creditAmount: 50 },
      { entryType: 'RJE', accountCode: '1503', debitAmount: 50, creditAmount: 0 },
    ])
    expect(s.rowCount).toBe(4)
    expect(s.ajeCount).toBe(2)
    expect(s.rjeCount).toBe(2)
    expect(s.totalDebits).toBe(250)
    expect(s.totalCredits).toBe(250)
    expect(s.balanceDiff).toBe(0)
    expect(s.net1503).toBe(200)
    expect(s.ajeNet1503).toBe(200)
    expect(s.rjeNet1503).toBe(0)
    expect(s.ociNet).toBe(-200)
  })

  it('空表为零', () => {
    const s = summarizeG8Adjustment([])
    expect(s.rowCount).toBe(0)
    expect(s.net1503).toBe(0)
  })
})

describe('aggregateG8AdjustmentWriteback', () => {
  it('回写至 fv_1', () => {
    const wb = aggregateG8AdjustmentWriteback([
      { accountCode: '1503', debitAmount: 80, creditAmount: 0 },
      { accountCode: '4002', debitAmount: 0, creditAmount: 80 },
    ])
    expect(wb.rowKey).toBe('fv_1')
    expect(wb.closingAdjustment).toBe(80)

    const store = applyG8AdjustmentWriteback(defaultG8AdjStore(), wb)
    expect(store.fv_1?.closingAdjustment).toBe(80)
  })
})
