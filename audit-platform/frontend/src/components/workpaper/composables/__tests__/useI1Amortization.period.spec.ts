/**
 * useI1Amortization — 期间键 I1-amort-period 双写兼容
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useI1Amortization } from '../useI1Amortization'

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

describe('useI1Amortization period keys', () => {
  it('loads legacy I1-11-period when new key missing', () => {
    const allResponses = makeMap({
      'I1-11-period': { periodBegin: '2025-01-01', periodEnd: '2025-12-31' },
    })
    const state = useI1Amortization(ref('wp1'), allResponses as any)
    expect(state.periodBegin.value).toBe('2025-01-01')
    expect(state.periodEnd.value).toBe('2025-12-31')
  })

  it('prefers I1-amort-period over legacy', () => {
    const allResponses = makeMap({
      'I1-amort-period': { periodBegin: '2024-01-01', periodEnd: '2024-12-31' },
      'I1-11-period': { periodBegin: '2020-01-01', periodEnd: '2020-12-31' },
    })
    const state = useI1Amortization(ref('wp1'), allResponses as any)
    expect(state.periodBegin.value).toBe('2024-01-01')
    expect(state.periodEnd.value).toBe('2024-12-31')
  })

  it('setPeriod dual-writes new and legacy keys', () => {
    const saved: Record<string, any> = {}
    const allResponses = makeMap()
    const state = useI1Amortization(ref('wp1'), allResponses as any, {
      onSave: (id, val) => {
        saved[id] = val
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: typeof val === 'string' ? val : JSON.stringify(val),
        })
      },
    })
    state.setPeriod('2025-01-01', '2025-12-31')
    expect(saved['I1-amort-period']).toEqual({
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
    })
    expect(saved['I1-11-period']).toEqual({
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
    })
  })

  it('amortReconcile reads I1-1 provision and I1-9 alloc keys', () => {
    const allResponses = makeMap({
      'I1-adj-amort-increase-total': 500,
      'I1-9-alloc-totals': { allocSum: 500 },
    })
    const state = useI1Amortization(ref('wp1'), allResponses as any)
    expect(state.amortReconcile.value.adjudicatedProvision).toBe(500)
    expect(state.amortReconcile.value.allocTotal).toBe(500)
    expect(state.amortReconcile.value.periodAmortTotal).toBe(0)
    expect(state.amortReconcile.value.matchedAdj).toBe(false)
    expect(state.amortReconcile.value.matchedAlloc).toBe(false)
  })

  it('syncFromUsefulLife 优先应用 I1-7 lifeParams', () => {
    const allResponses = makeMap({
      'I1-10-rows': [
        {
          rowId: 'r1',
          name: '软件A',
          cost: 12000,
          usefulLifeMonths: 60,
          usefulLifeYears: 5,
          periodAmortization: 0,
        },
      ],
      'I1-7-indefinite-list': {
        lifeParams: [
          { name: '软件A', usefulLifeMonths: 36, isIndefinite: false },
        ],
      },
    })
    const state = useI1Amortization(ref('wp1'), allResponses as any)
    state.switchBranch('noImpair', false)
    // ensure rows loaded
    expect(state.currentRows.value.length).toBeGreaterThan(0)
    const r = state.syncFromUsefulLife()
    expect(r.updated).toBeGreaterThanOrEqual(1)
    const row = state.currentRows.value.find((x) => x.name === '软件A')
    expect(row?.usefulLifeMonths).toBe(36)
  })
})
