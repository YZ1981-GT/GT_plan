/**
 * G10 附注披露 — Level3 跨表勾稽
 */
import { describe, it, expect } from 'vitest'
import {
  buildG10DisclosureCrossChecks,
  buildG10MovementCrossChecks,
  sumG10Level3FvAudited,
  sumG10L3ReportedClosing,
} from '../g10DisclosureCross'
import type { ChecklistResponse } from '../useF1FormData'

function responses(data: Record<string, unknown>): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(data)) {
    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) } as ChecklistResponse)
  }
  return m
}

describe('buildG10DisclosureCrossChecks', () => {
  it('G10-5 Level3 与 G10-6 不一致时告警', () => {
    const checks = buildG10DisclosureCrossChecks(responses({
      'G10-fv-test-rows': JSON.stringify([
        { liabilityName: '债券A', fairValueLevel: 'Level3', closingAuditedFV: 100 },
      ]),
      'G10-l3-rows': JSON.stringify([
        { liabilityName: '债券A', reportedClosing: 80 },
      ]),
    }))
    expect(checks.some((c) => c.code === 'disclosure-fv5-vs-l6')).toBe(true)
  })

  it('有 Level3 余额时给出 G10-5/G10-6 编制提示', () => {
    const checks = buildG10DisclosureCrossChecks(responses({
      'G10-fv-test-rows': JSON.stringify([
        { liabilityName: '债券A', fairValueLevel: 'Level3', closingAuditedFV: 50 },
      ]),
    }))
    expect(checks.some((c) => c.code === 'disclosure-l3-hint')).toBe(true)
  })

  it('Level3 汇总函数', () => {
    const r = responses({
      'G10-fv-test-rows': JSON.stringify([
        { fairValueLevel: 'Level3', closingAuditedFV: 30 },
        { fairValueLevel: 'Level2', closingAuditedFV: 999 },
      ]),
      'G10-l3-rows': JSON.stringify([{ reportedClosing: 30 }]),
    })
    expect(sumG10Level3FvAudited(r)).toBe(30)
    expect(sumG10L3ReportedClosing(r)).toBe(30)
  })
})

describe('buildG10MovementCrossChecks', () => {
  it('期初+增加-减少≠期末时告警', () => {
    const checks = buildG10MovementCrossChecks({
      mv_trading_bond: {
        openingAmount: 100,
        increaseAmount: 20,
        decreaseAmount: 0,
        closingAmount: 150,
      },
    })
    expect(checks.some((c) => c.code === 'disclosure-movement-balance')).toBe(true)
  })
})
