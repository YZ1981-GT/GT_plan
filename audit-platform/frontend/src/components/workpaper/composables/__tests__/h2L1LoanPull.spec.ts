/**
 * h2L1LoanPull — H2-10 ↔ L1 借款带入纯函数单测
 */
import { describe, it, expect } from 'vitest'
import { reconstructL1InterestRows, normalizeL1RateToPercent } from '../h2L1LoanPull'

describe('reconstructL1InterestRows', () => {
  it('按 L1-int-{n}-{field} 逐单元格重建行', () => {
    const responses = [
      { item_id: 'L1-int-1-bank', remark: '工商银行' },
      { item_id: 'L1-int-1-contractNo', remark: 'C001' },
      { item_id: 'L1-int-1-principal', remark: '1000000' },
      { item_id: 'L1-int-1-rate', remark: '0.045' },
      { item_id: 'L1-int-1-days', remark: '365' },
      { item_id: 'L1-int-1-calculatedInterest', remark: '45000' },
      { item_id: 'L1-int-1-bookedInterest', remark: '44000' },
      { item_id: 'L1-int-2-bank', remark: '建设银行' },
      { item_id: 'L1-int-2-principal', remark: '500000' },
      { item_id: 'L1-adj-1-name', remark: '短期借款' }, // 非利息行忽略
    ]
    const rows = reconstructL1InterestRows(responses)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      bank: '工商银行', contractNo: 'C001', principal: 1000000,
      rate: 0.045, days: 365, calculatedInterest: 45000, bookedInterest: 44000,
    })
    expect(rows[1]).toMatchObject({ bank: '建设银行', principal: 500000 })
  })
  it('全空行跳过；非数组安全返回', () => {
    expect(reconstructL1InterestRows([])).toEqual([])
    expect(reconstructL1InterestRows([{ item_id: 'L1-int-9-days', remark: '30' }])).toEqual([])
  })
  it('行号乱序按 n 升序输出', () => {
    const rows = reconstructL1InterestRows([
      { item_id: 'L1-int-3-bank', remark: 'C' },
      { item_id: 'L1-int-3-principal', remark: '3' },
      { item_id: 'L1-int-1-bank', remark: 'A' },
      { item_id: 'L1-int-1-principal', remark: '1' },
    ])
    expect(rows.map((r) => r.bank)).toEqual(['A', 'C'])
  })
})

describe('normalizeL1RateToPercent', () => {
  it('小数利率转百分数', () => {
    expect(normalizeL1RateToPercent(0.05)).toBe(5)
    expect(normalizeL1RateToPercent(0.045)).toBeCloseTo(4.5, 5)
  })
  it('已是百分数则原样返回', () => {
    expect(normalizeL1RateToPercent(5)).toBe(5)
  })
  it('0 返回 0', () => {
    expect(normalizeL1RateToPercent(0)).toBe(0)
  })
})
