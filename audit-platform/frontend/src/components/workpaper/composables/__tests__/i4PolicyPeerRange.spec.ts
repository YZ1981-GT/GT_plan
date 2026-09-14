/**
 * i4PolicyPeerRange — 同业区间 / 偏离 / 建议判断 单测
 */
import { describe, it, expect } from 'vitest'
import {
  computePeerRanges,
  computePeerDeviations,
  suggestReasonableVsPeers,
  suggestReasonableYForInRange,
  categoriesNeedingPeerRemark,
} from '../i4PolicyPeerRange'
import {
  buildAttentionRemarksFromIssues,
  significantDiffAmounts,
  crossCheckPolicyVsAmort,
} from '../i4PolicyAmortCrossCheck'

describe('computePeerRanges / deviations', () => {
  it('计算同业受益期区间', () => {
    const ranges = computePeerRanges([
      {
        category: '装修费',
        cells: {
          a: { benefitPeriod: '3年', amortMethod: '直线法' },
          b: { benefitPeriod: '5年', amortMethod: '直线法' },
        },
      },
    ])
    expect(ranges[0].periodMinMonths).toBe(36)
    expect(ranges[0].periodMaxMonths).toBe(60)
    expect(ranges[0].label).toContain('期限')
  })

  it('客户期限超出同业区间 → 偏离', () => {
    const ranges = computePeerRanges([
      {
        category: '装修费',
        cells: {
          a: { benefitPeriod: '3年', amortMethod: '直线法' },
          b: { benefitPeriod: '5年', amortMethod: '直线法' },
        },
      },
    ])
    const devs = computePeerDeviations(
      [{ category: '装修费', benefitPeriod: '10年', amortMethod: '直线法' }],
      ranges,
    )
    expect(devs.some((d) => d.field === 'benefitPeriod')).toBe(true)
  })

  it('方法不在同业集合 → 偏离', () => {
    const ranges = computePeerRanges([
      {
        category: '装修费',
        cells: {
          a: { benefitPeriod: '3年', amortMethod: '直线法' },
        },
      },
    ])
    const devs = computePeerDeviations(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '工作量法' }],
      ranges,
    )
    expect(devs.some((d) => d.field === 'amortMethod')).toBe(true)
  })
})

describe('suggestReasonable / remark gate', () => {
  it('偏离填 N 并写备注；区间内填 Y', () => {
    const ranges = computePeerRanges([
      {
        category: '装修费',
        cells: {
          a: { benefitPeriod: '3年', amortMethod: '直线法' },
          b: { benefitPeriod: '5年', amortMethod: '直线法' },
        },
      },
      {
        category: '开办费',
        cells: {
          a: { benefitPeriod: '5年', amortMethod: '直线法' },
        },
      },
    ])
    const rows = [
      { category: '装修费', benefitPeriod: '10年', amortMethod: '直线法', reasonableVsPeers: '', remark: '' },
      { category: '开办费', benefitPeriod: '5年', amortMethod: '直线法', reasonableVsPeers: '', remark: '' },
    ]
    const devs = computePeerDeviations(rows, ranges)
    const nN = suggestReasonableVsPeers(rows, devs)
    const nY = suggestReasonableYForInRange(rows, ranges, devs)
    expect(nN + nY).toBe(2)
    expect(rows[0].reasonableVsPeers).toBe('N')
    expect(rows[0].remark).toContain('同业偏离')
    expect(rows[1].reasonableVsPeers).toBe('Y')
  })

  it('判 Y 但仍偏离 → 须备注', () => {
    const need = categoriesNeedingPeerRemark(
      [{ category: '装修费', benefitPeriod: '10年', reasonableVsPeers: 'Y', remark: '' }],
      [{ category: '装修费', field: 'benefitPeriod', message: '超出', requiresRemark: true }],
    )
    expect(need).toContain('装修费')
  })
})

describe('cross-check → attention / adj drafts', () => {
  it('buildAttentionRemarksFromIssues 按类别合并', () => {
    const map = buildAttentionRemarksFromIssues([
      { id: '1', severity: 'error', category: '装修费', code: 'period-mismatch', message: '期限不一致' },
      { id: '2', severity: 'warning', category: '装修费', code: 'significant-diff', message: '差异大' },
    ])
    expect(map.get('装修费')).toContain('期限不一致')
    expect(map.get('装修费')).toContain('差异大')
  })

  it('significantDiffAmounts 取最大差异', () => {
    const result = crossCheckPolicyVsAmort(
      [{ category: '装修费', benefitPeriod: '3年', amortMethod: '直线法', meetsStandards: 'Y' }],
      [{ category: '装修费', usefulLife: '3年', lifeMonths: 36, amortMethod: '直线法', accumDiff: 25000, monthlyDiff: 100 }],
      [],
    )
    const amts = significantDiffAmounts(result)
    expect(amts[0]?.category).toBe('装修费')
    expect(amts[0]?.amount).toBe(25000)
  })
})
