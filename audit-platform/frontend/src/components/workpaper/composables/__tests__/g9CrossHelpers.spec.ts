/**
 * g9CrossHelpers — G9 跨表勾稽
 */
import { describe, expect, it } from 'vitest'
import type { ChecklistResponse } from '../useF1FormData'
import {
  buildG9CrossChecks,
  isG9Level3,
  listG9Fv4VsG95AssetMismatches,
  sumG9Level3FvAudited,
  sumG9L3ReportedClosing,
} from '../g9CrossHelpers'

function resp(remark: string): ChecklistResponse {
  return { item_id: 'x', conclusion: null, remark } as ChecklistResponse
}

function mapOf(entries: Record<string, string>): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) m.set(k, resp(v))
  return m
}

describe('isG9Level3', () => {
  it('识别多种写法', () => {
    expect(isG9Level3('Level3')).toBe(true)
    expect(isG9Level3('l3')).toBe(true)
    expect(isG9Level3('3')).toBe(true)
    expect(isG9Level3('第三层次')).toBe(true)
    expect(isG9Level3('Level2')).toBe(false)
  })
})

describe('G9-4 vs G9-5 合计', () => {
  it('Level3 审定合计与企业报告勾稽一致时无告警', () => {
    const responses = mapOf({
      'G9-fv-test-rows': JSON.stringify([
        { assetName: 'A', fairValueLevel: 'Level3', closingAuditedFV: 100 },
        { assetName: 'B', fairValueLevel: 'Level2', closingAuditedFV: 999 },
      ]),
      'G9-l3-rows': JSON.stringify([
        { assetName: 'A', reportedClosing: 100, closingFairValue: 100 },
      ]),
    })
    expect(sumG9Level3FvAudited(responses)).toBe(100)
    expect(sumG9L3ReportedClosing(responses)).toBe(100)
    const checks = buildG9CrossChecks(responses)
    expect(checks.find((c) => c.code === 'fv4-l3-total-vs-g95-reported')).toBeUndefined()
  })

  it('合计差异时告警', () => {
    const responses = mapOf({
      'G9-fv-test-rows': JSON.stringify([
        { assetName: 'A', fairValueLevel: 'Level3', closingAuditedFV: 120 },
      ]),
      'G9-l3-rows': JSON.stringify([
        { assetName: 'A', reportedClosing: 100 },
      ]),
    })
    const checks = buildG9CrossChecks(responses)
    const hit = checks.find((c) => c.code === 'fv4-l3-total-vs-g95-reported')
    expect(hit?.diff).toBeCloseTo(20, 5)
  })
})

describe('按资产勾稽', () => {
  it('同名资产金额不符列入 mismatches', () => {
    const responses = mapOf({
      'G9-fv-test-rows': JSON.stringify([
        { assetName: '基金甲', fairValueLevel: 'Level3', closingAuditedFV: 50 },
      ]),
      'G9-l3-rows': JSON.stringify([
        { assetName: '基金甲', reportedClosing: 40 },
      ]),
    })
    const list = listG9Fv4VsG95AssetMismatches(responses)
    expect(list).toHaveLength(1)
    expect(list[0].diff).toBeCloseTo(10, 5)
  })
})

describe('附注 vs 审定', () => {
  it('披露合计与审定差异时告警', () => {
    const checks = buildG9CrossChecks(new Map(), {
      disclosureCurrentSum: 1000,
      adjudicatedAmount: 980,
    })
    expect(checks.some((c) => c.code === 'disclosure-sum-vs-adj')).toBe(true)
  })

  it('差异在容差内不告警', () => {
    const checks = buildG9CrossChecks(new Map(), {
      disclosureCurrentSum: 100,
      adjudicatedAmount: 100.005,
    })
    expect(checks.find((c) => c.code === 'disclosure-sum-vs-adj')).toBeUndefined()
  })
})
