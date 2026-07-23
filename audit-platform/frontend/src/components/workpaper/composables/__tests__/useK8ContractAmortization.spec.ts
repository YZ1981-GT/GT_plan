/**
 * useK8ContractAmortization 纯函数单测 — 锁定 K8-5 合同费用摊销核对公式
 */
import { describe, it, expect } from 'vitest'
import {
  parseYm,
  monthsInclusive,
  accrualMonthsInPeriod,
  calcAccruedPL,
} from '../useK8ContractAmortization'

describe('parseYm', () => {
  it('解析合法 YYYY-MM-DD', () => {
    expect(parseYm('2025-03-15')).toEqual({ y: 2025, m: 3 })
    expect(parseYm('2025-1-1')).toEqual({ y: 2025, m: 1 })
  })
  it('非法输入返回 null', () => {
    expect(parseYm('')).toBeNull()
    expect(parseYm('bad')).toBeNull()
    expect(parseYm('2025-13-01')).toBeNull()
    expect(parseYm(undefined as any)).toBeNull()
  })
})

describe('monthsInclusive（合同总月份，含首尾月）', () => {
  it('整年 = 12', () => {
    expect(monthsInclusive('2025-01-01', '2025-12-31')).toBe(12)
  })
  it('单月 = 1', () => {
    expect(monthsInclusive('2025-05-10', '2025-05-28')).toBe(1)
  })
  it('跨年 = 正确跨月数', () => {
    // 2024-07 ~ 2025-06 = 12 个月
    expect(monthsInclusive('2024-07-01', '2025-06-30')).toBe(12)
    // 2024-11 ~ 2025-02 = 4 个月
    expect(monthsInclusive('2024-11-01', '2025-02-28')).toBe(4)
  })
  it('逆序/非法返回 0（防除零）', () => {
    expect(monthsInclusive('2025-12-01', '2025-01-01')).toBe(0)
    expect(monthsInclusive('', '2025-12-31')).toBe(0)
    expect(monthsInclusive('2025-01-01', '')).toBe(0)
  })
})

describe('accrualMonthsInPeriod（合同期 ∩ 摊销期）', () => {
  it('合同期完全覆盖摊销期 → 摊销期月份数', () => {
    // 合同 2024-01~2026-12，摊销期整个 2025 → 12
    expect(accrualMonthsInPeriod('2024-01-01', '2026-12-31', '2025-01-01', '2025-12-31')).toBe(12)
  })
  it('部分重叠 → 交集月份数', () => {
    // 合同 2024-07~2025-06，摊销期 2025 全年 → 交集 2025-01~2025-06 = 6
    expect(accrualMonthsInPeriod('2024-07-01', '2025-06-30', '2025-01-01', '2025-12-31')).toBe(6)
  })
  it('合同期在摊销期内 → 合同月份数', () => {
    // 合同 2025-03~2025-08，摊销期 2025 全年 → 6
    expect(accrualMonthsInPeriod('2025-03-01', '2025-08-31', '2025-01-01', '2025-12-31')).toBe(6)
  })
  it('无重叠 → 0', () => {
    // 合同 2023 年，摊销期 2025 年 → 0
    expect(accrualMonthsInPeriod('2023-01-01', '2023-12-31', '2025-01-01', '2025-12-31')).toBe(0)
  })
  it('非法日期 → 0', () => {
    expect(accrualMonthsInPeriod('', '2025-12-31', '2025-01-01', '2025-12-31')).toBe(0)
  })
})

describe('calcAccruedPL（本期应计损益 = 金额÷总月份×应计月份）', () => {
  it('正常直线摊销', () => {
    // 合同 120000，总月份 12，应计月份 6 → 60000
    expect(calcAccruedPL(120000, 12, 6)).toBe(60000)
    // 合同 120000，总月份 12，应计月份 12 → 120000（全额）
    expect(calcAccruedPL(120000, 12, 12)).toBe(120000)
  })
  it('总月份为 0 → 0（防除零）', () => {
    expect(calcAccruedPL(120000, 0, 6)).toBe(0)
  })
  it('应计月份为 0 → 0', () => {
    expect(calcAccruedPL(120000, 12, 0)).toBe(0)
  })
  it('非法输入按 0 处理', () => {
    expect(calcAccruedPL(NaN as any, 12, 6)).toBe(0)
    expect(calcAccruedPL(120000, NaN as any, 6)).toBe(0)
  })
})
