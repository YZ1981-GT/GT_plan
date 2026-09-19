/**
 * H8↔H9：终止落库 + 多键勾稽
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { applyH8TerminationToH92Rows } from '../useH9Detail'
import { useH9CrossSheet } from '../useH9CrossSheet'
import { useH8CrossSheet } from '../useH8CrossSheet'

function makeMap(entries?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (entries) {
    for (const [k, v] of Object.entries(entries)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('applyH8TerminationToH92Rows', () => {
  it('marks terminated and settles repayAje so auditedEnd → 0', () => {
    const rows = [
      {
        contractNo: 'C-001',
        beginBalance: 100_000,
        beginAje: 0,
        interestAccrued: 5_000,
        interestAje: 0,
        repayment: 20_000,
        repayAje: 0,
        reclassification: 0,
      },
      { contractNo: 'C-OTHER', beginBalance: 1, repayment: 0, interestAccrued: 0 },
    ]
    const { rows: next, matched } = applyH8TerminationToH92Rows(rows, {
      contractNo: 'C-001',
      reductionDate: '2025-06-30',
      settle: true,
    })
    expect(matched).toBe(1)
    expect(next[0].isTerminated).toBe('是')
    expect(next[0].terminatedFromH8).toBe(true)
    expect(next[0].terminationDate).toBe('2025-06-30')
    // auditedBegin 100k + interest 5k = 105k → repay+repayAje = 105k → end 0
    expect(Number(next[0].auditedEnd)).toBe(0)
    expect(Number(next[0].repayAje)).toBe(85_000)
    expect(next[1].isTerminated).toBeUndefined()
  })
})

describe('H9↔H8 multi-key linkage', () => {
  it('H9 CrossSheet reads H8 canonical aliases when H9-h8-* absent', () => {
    const allResponses = makeMap({
      'H9-1-initial-liability': '101000',
      'H8-initial-measurement': '102000',
      'H8-direct-cost-total': '2000',
      'H8-incentive-total': '1000',
    })
    const { h9VsH8Linkage } = useH9CrossSheet(allResponses as any)
    // expected H9 = 102000 - 2000 + 1000 = 101000
    expect(h9VsH8Linkage.value.isConsistent).toBe(true)
    expect(Math.abs(h9VsH8Linkage.value.diff)).toBeLessThanOrEqual(1)
  })

  it('H8 CrossSheet prefers H8-h9-initial-recognition alias', () => {
    const allResponses = makeMap({
      'H8-h9-initial-recognition': '100000',
      'H8-initial-measurement': '101000',
      'H8-direct-cost-total': '2000',
      'H8-incentive-total': '1000',
      'H8-2-rows': [],
    })
    const { h8VsH9Linkage } = useH8CrossSheet(allResponses as any)
    // H8 = 101000; expected = 100000 + 2000 - 1000 = 101000
    expect(h8VsH9Linkage.value.isConsistent).toBe(true)
  })
})
