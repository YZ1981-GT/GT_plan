import { describe, it, expect } from 'vitest'
import {
  aggregateGrossFromG52,
  aggregateProvisionFromG53,
  normalizeDebtorName,
} from '../g5CrossHelpers'

describe('g5CrossHelpers', () => {
  it('normalizeDebtorName 去掉空白', () => {
    expect(normalizeDebtorName(' 甲  公司 ')).toBe('甲公司')
  })

  it('aggregateGrossFromG52 优先用 isWithinOneYear', () => {
    const g = aggregateGrossFromG52([
      { debtorName: '甲', businessType: 'lease', closingBalance: 100, isWithinOneYear: true },
      { debtorName: '乙', businessType: 'factoring', closingBalance: 50, isWithinOneYear: false },
    ])
    expect(g.businessClosing).toBe(100)
    expect(g.customerClosing).toBe(50)
    expect(g.oneYearClosing).toBe(100)
    expect([...g.oneYearDebtors]).toEqual(['甲'])
  })

  it('aggregateProvisionFromG53 报告一年内未匹配债务人', () => {
    const oneYear = new Set(['甲公司', '乙公司'])
    const p = aggregateProvisionFromG53(
      [
        { debtorOrGroup: '甲 公司', provisionMethod: 'group', portfolioType: 'business', adjustedProvision: 10 },
      ],
      oneYear,
    )
    expect(p.oneYearClosing).toBe(10)
    expect(p.unmatchedOneYearDebtors).toEqual(['乙公司'])
  })
})
