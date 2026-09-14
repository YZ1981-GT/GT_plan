/**
 * workpaperAuditYear 单元测试
 */
import { describe, it, expect } from 'vitest'
import { resolveAuditYearNumber, pickTbAmount } from '../workpaperAuditYear'

describe('resolveAuditYearNumber', () => {
  it('解析有效年度', () => {
    expect(resolveAuditYearNumber(2025)).toBe(2025)
    expect(resolveAuditYearNumber('2024')).toBe(2024)
  })
  it('拒绝非法值并回退后续候选', () => {
    expect(resolveAuditYearNumber(null, undefined, '', 0, 2026)).toBe(2026)
    expect(resolveAuditYearNumber('abc', 1899, 2025)).toBe(2025)
  })
  it('全无效返回 null', () => {
    expect(resolveAuditYearNumber(null, undefined, '')).toBeNull()
  })
})

describe('pickTbAmount', () => {
  it('优先 audited_amount', () => {
    expect(pickTbAmount({ audited_amount: 10, unadjusted_amount: 5 })).toBe(10)
  })
  it('借贷差兜底', () => {
    expect(pickTbAmount({ debit_amount: 100, credit_amount: 40 })).toBe(60)
  })
})
