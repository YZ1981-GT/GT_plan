/**
 * i4PolicyLeaseShorter — 租赁期孰短单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  monthsBetween,
  checkLeaseShorterRule,
  checkPolicyVsLeaseByCategory,
} from '../i4PolicyLeaseShorter'

describe('monthsBetween', () => {
  it('计算整月间隔', () => {
    expect(monthsBetween('2024-01-01', '2024-12-31')).toBe(11)
    expect(monthsBetween('2024-01-15', '2025-01-15')).toBe(12)
  })

  it('非法日期返回 null', () => {
    expect(monthsBetween('', '2024-12-31')).toBeNull()
    expect(monthsBetween('2025-01-01', '2024-01-01')).toBeNull()
  })
})

describe('checkLeaseShorterRule', () => {
  it('受益期超过租赁期报错', () => {
    const r = checkLeaseShorterRule(
      [{
        expenseType: '装修费',
        projectName: '门店A',
        startDate: '2024-01-01',
        endDate: '2025-01-01',
        totalMonths: 36,
      }],
      { 装修费: '3年' },
    )
    expect(r.ok).toBe(false)
    expect(r.byCategory.some((c) => c.severity === 'error')).toBe(true)
  })

  it('受益期不超过租赁期通过', () => {
    const r = checkLeaseShorterRule([
      {
        expenseType: '租赁改良',
        projectName: '仓库',
        startDate: '2020-01-01',
        endDate: '2025-01-01',
        totalMonths: 36,
      },
    ])
    expect(r.ok).toBe(true)
  })

  it('非敏感类别跳过', () => {
    const r = checkLeaseShorterRule([
      { expenseType: '开办费', startDate: '2024-01-01', endDate: '2025-01-01', totalMonths: 60 },
    ])
    expect(r.items.length).toBe(0)
    expect(r.ok).toBe(true)
  })
})

describe('checkPolicyVsLeaseByCategory', () => {
  it('表A政策超过明细最短租赁期', () => {
    const issues = checkPolicyVsLeaseByCategory(
      [{ category: '装修费', benefitPeriod: '5年' }],
      [{
        expenseType: '装修费',
        startDate: '2024-01-01',
        endDate: '2025-07-01',
      }],
    )
    expect(issues.some((i) => i.severity === 'error')).toBe(true)
  })
})
