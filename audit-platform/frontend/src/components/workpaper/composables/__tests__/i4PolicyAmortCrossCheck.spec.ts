/**
 * i4PolicyAmortCrossCheck — 表A ↔ I4-6/7 勾稽单测
 */
import { describe, it, expect } from 'vitest'
import {
  parseBenefitPeriodToMonths,
  aggregateI46ByCategory,
  aggregateI47ByCategory,
  crossCheckPolicyVsAmort,
} from '../i4PolicyAmortCrossCheck'

describe('parseBenefitPeriodToMonths', () => {
  it('解析年/月/区间', () => {
    expect(parseBenefitPeriodToMonths('3年')).toBe(36)
    expect(parseBenefitPeriodToMonths('36月')).toBe(36)
    expect(parseBenefitPeriodToMonths('3-5年')).toBe(48)
    expect(parseBenefitPeriodToMonths('3年（36月）')).toBe(36)
  })

  it('租赁期等定性返回 null', () => {
    expect(parseBenefitPeriodToMonths('租赁期')).toBeNull()
  })
})

describe('aggregate + crossCheck', () => {
  it('I4-6 按类别聚合方法与月限', () => {
    const aggs = aggregateI46ByCategory([
      { category: '装修费', usefulLife: '3年', lifeMonths: 36, amortMethod: '直线法', accumDiff: 100, monthlyDiff: 10 },
      { category: '装修费', usefulLife: '3年', lifeMonths: 36, amortMethod: '直线法', accumDiff: 50, monthlyDiff: 5 },
      { category: '开办费', usefulLife: '5年', lifeMonths: 60, amortMethod: '直线法', accumDiff: 0, monthlyDiff: 0 },
    ])
    const deco = aggs.find((a) => a.category === '装修费')!
    expect(deco.itemCount).toBe(2)
    expect(deco.amortMethod).toBe('直线法')
    expect(deco.lifeMonthsMode).toBe(36)
    expect(deco.accumDiffAbs).toBe(150)
  })

  it('方法不一致报 error', () => {
    const result = crossCheckPolicyVsAmort(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '直线法', meetsStandards: 'Y' }],
      [],
      [{ category: '装修费', periodDiff: 0, accumDiff: 0 }],
    )
    expect(result.issues.some((i) => i.code === 'method-mismatch' && i.severity === 'error')).toBe(true)
    expect(result.ok).toBe(false)
  })

  it('期限不一致报 error', () => {
    const result = crossCheckPolicyVsAmort(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '直线法' }],
      [{ category: '装修费', usefulLife: '5年', lifeMonths: 60, amortMethod: '直线法', accumDiff: 0, monthlyDiff: 0 }],
      [],
    )
    expect(result.issues.some((i) => i.code === 'period-mismatch')).toBe(true)
  })

  it('重大差异且表A判Y → error', () => {
    const result = crossCheckPolicyVsAmort(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '直线法', meetsStandards: 'Y' }],
      [{ category: '装修费', usefulLife: '3年', lifeMonths: 36, amortMethod: '直线法', accumDiff: 50000, monthlyDiff: 0 }],
      [],
    )
    const diff = result.issues.find((i) => i.code === 'significant-diff')
    expect(diff?.severity).toBe('error')
    expect(result.ok).toBe(false)
  })

  it('无测算数据时 info 且 ok', () => {
    const result = crossCheckPolicyVsAmort(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '直线法' }],
      [],
      [],
    )
    expect(result.ok).toBe(true)
    expect(result.issues[0].severity).toBe('info')
  })

  it('I4-7 聚合为工作量法', () => {
    const aggs = aggregateI47ByCategory([
      { category: '其他', periodDiff: 20, accumDiff: 30 },
    ])
    expect(aggs[0].amortMethod).toBe('工作量法')
    expect(aggs[0].periodDiffAbs).toBe(20)
  })
})
