/**
 * H3-14 租金收入测算 — 公式与行模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcMonthsInFiscalYear,
  createEmptyRentalRow,
  recalcRentalRow,
  sumMonthlyActual,
  buildRentalDisplayRows,
  parseTb6051Amount,
} from '../composables/useH3RentalIncome'

describe('H3-14 recalcRentalRow：应计③=①×②，差异⑤=③−④', () => {
  it('应计 = 本期月数 × 月租金', () => {
    const row = createEmptyRentalRow({
      monthsThisYear: 10,
      monthlyRent: 50_000,
      bookedRent: 480_000,
    })
    expect(row.expectedRent).toBe(500_000)
    expect(row.incomeDiff).toBe(20_000) // 账面少计
    expect(row.annualRent).toBe(600_000)
  })

  it('日后未折现收款合计 = Y1..Y5 + 5年后', () => {
    const row = createEmptyRentalRow({
      futureY1: 100,
      futureY2: 100,
      futureY3: 100,
      futureY4: 100,
      futureY5: 100,
      futureAfter: 50,
    })
    expect(row.futureTotal).toBe(550)
  })

  it('合同总额可推算月租金（月租金为空时）', () => {
    const row = createEmptyRentalRow({
      leaseStart: '2024-01-01',
      leaseEnd: '2025-12-31',
      contractAmount: 240_000,
      monthsThisYear: 12,
      monthlyRent: 0,
    })
    expect(row.monthlyRent).toBe(10_000) // 24个月
    expect(row.expectedRent).toBe(120_000)
  })
})

describe('H3-14 calcMonthsInFiscalYear', () => {
  it('整年在租 → 12', () => {
    expect(calcMonthsInFiscalYear('2024-01-01', '2026-12-31', 2025)).toBe(12)
  })

  it('年中起租 → 重叠月数', () => {
    expect(calcMonthsInFiscalYear('2025-07-01', '2026-06-30', 2025)).toBe(6)
  })

  it('无重叠 → 0', () => {
    expect(calcMonthsInFiscalYear('2023-01-01', '2023-12-31', 2025)).toBe(0)
  })
})

describe('H3-14 buildRentalDisplayRows', () => {
  it('按类别插入小计与合计行', () => {
    const rows = [
      createEmptyRentalRow({ category: 'building', assetName: 'A', monthsThisYear: 12, monthlyRent: 10_000, bookedRent: 120_000 }),
      createEmptyRentalRow({ category: 'land', assetName: 'B', monthsThisYear: 6, monthlyRent: 5_000, bookedRent: 30_000 }),
    ]
    const display = buildRentalDisplayRows(rows)
    expect(display.filter((r) => r.rowKind === 'data')).toHaveLength(2)
    expect(display.some((r) => r.label.includes('房屋、建筑物'))).toBe(true)
    expect(display.some((r) => r.label.includes('土地使用权'))).toBe(true)
    expect(display[display.length - 1].rowKind).toBe('grandTotal')
    expect(display[display.length - 1].expectedRent).toBe(150_000)
  })
})

describe('H3-14 parseTb6051Amount', () => {
  it('贷方-借方 = 收入发生额', () => {
    expect(parseTb6051Amount({ credit_amount: 500_000, debit_amount: 20_000 })).toBe(480_000)
  })

  it('优先取 audited_amount', () => {
    expect(parseTb6051Amount({ audited_amount: 123_456, credit_amount: 1 })).toBe(123_456)
  })
})

describe('H3-14 月度累计', () => {
  it('sumMonthlyActual 汇总12列', () => {
    const row = createEmptyRentalRow({
      monthlyActual: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    })
    expect(sumMonthlyActual(row)).toBe(78)
  })

  it('recalc 保持差异方向：应计−已计', () => {
    const row = createEmptyRentalRow({
      monthsThisYear: 12,
      monthlyRent: 10_000,
      bookedRent: 130_000,
    })
    recalcRentalRow(row)
    expect(row.incomeDiff).toBe(-10_000) // 账面多计
  })
})
