/**
 * G7-15 内部交易抵销 — 行模型冒烟测试
 */
import { describe, it, expect } from 'vitest'
import {
  createEmptyInternalTransactionRow,
  hydrateInternalTransactionRow,
  hydrateInternalTransactionRows,
  recalcInternalTransactionRow,
  clearUnrealizedProfitManual,
} from '../g7InternalTransactionModel'

describe('g7InternalTransactionModel', () => {
  it('毛利率公式：未实现利润 = 交易金额 × 毛利率，顺流全额抵销', () => {
    const row = createEmptyInternalTransactionRow(1, '联营甲')
    row.transactionType = '顺流'
    row.transactionAmount = 1_000_000
    row.grossMargin = 0.2
    recalcInternalTransactionRow(row)
    expect(row.unrealizedProfit).toBe(200_000)
    expect(row.eliminationAmount).toBe(200_000)
    expect(row.currentChange).toBe(200_000)
  })

  it('逆流：应抵销 = 未实现利润 × 持股比例；本年变动扣上年', () => {
    const row = createEmptyInternalTransactionRow(1, '联营乙')
    row.transactionType = '逆流'
    row.transactionAmount = 500_000
    row.grossMargin = 0.1
    row.investmentRatio = 0.3
    row.priorElimination = 10_000
    recalcInternalTransactionRow(row)
    expect(row.unrealizedProfit).toBe(50_000)
    expect(row.eliminationAmount).toBe(15_000)
    expect(row.currentChange).toBe(5_000)
  })

  it('手填未实现利润后不再被毛利率覆盖', () => {
    const row = createEmptyInternalTransactionRow(1)
    row.transactionType = '顺流'
    row.transactionAmount = 100_000
    row.grossMargin = 0.2
    row.unrealizedProfit = 999
    row.unrealizedProfitManual = true
    recalcInternalTransactionRow(row)
    expect(row.unrealizedProfit).toBe(999)
    expect(row.eliminationAmount).toBe(999)
  })

  it('旧数据无毛利率时保住未实现利润（标记 manual）', () => {
    const row = hydrateInternalTransactionRow({
      investeeName: '联营丙',
      transactionType: '顺流',
      unrealizedProfit: 80_000,
      investmentRatio: 0.4,
      // 无 grossMargin
    }, 1)
    expect(row.unrealizedProfitManual).toBe(true)
    expect(row.unrealizedProfit).toBe(80_000)
    expect(row.eliminationAmount).toBe(80_000)
  })

  it('hydrate 保留 investeeId，并批量解析 {rows}', () => {
    const list = hydrateInternalTransactionRows({
      rows: [{
        investeeId: 'inv-1',
        investeeName: '联营丁',
        transactionType: '逆流',
        transactionAmount: 200_000,
        grossMargin: 0.25,
        investmentRatio: 0.4,
      }],
    })
    expect(list).toHaveLength(1)
    expect(list[0].investeeId).toBe('inv-1')
    expect(list[0].unrealizedProfit).toBe(50_000)
    expect(list[0].eliminationAmount).toBe(20_000)
  })

  it('毛利率为 0 且有未实现利润时标记手工，避免清零', () => {
    const row = hydrateInternalTransactionRow({
      investeeName: '联营戊',
      transactionType: '顺流',
      grossMargin: 0,
      unrealizedProfit: 12_000,
    }, 1)
    expect(row.unrealizedProfitManual).toBe(true)
    expect(row.unrealizedProfit).toBe(12_000)
    expect(row.eliminationAmount).toBe(12_000)
  })

  it('clearUnrealizedProfitManual 恢复公式', () => {
    const row = createEmptyInternalTransactionRow(1)
    row.transactionType = '顺流'
    row.transactionAmount = 100_000
    row.grossMargin = 0.2
    row.unrealizedProfit = 1
    row.unrealizedProfitManual = true
    clearUnrealizedProfitManual(row)
    expect(row.unrealizedProfitManual).toBe(false)
    expect(row.unrealizedProfit).toBe(20_000)
  })
})
