/**
 * useG8Adjudication — 勾稽 / 从明细带入 / 回写
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('../workpaperAuditYear', () => ({
  useWorkpaperAuditYear: () => ref(2025),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

import { useG8Adjudication } from '../useG8Adjudication'

function makeMap(entries: Record<string, Partial<ChecklistResponse>> = {}) {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse)
  }
  return m
}

describe('useG8Adjudication', () => {
  let saves: Array<{ id: string; data: Partial<ChecklistResponse> }>
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>

  beforeEach(() => {
    saves = []
    allResponses = ref(makeMap())
  })

  function setup(extra: Record<string, Partial<ChecklistResponse>> = {}) {
    allResponses.value = makeMap(extra)
    const debouncedSave = (id: string, d: Partial<ChecklistResponse>) => {
      saves.push({ id, data: d })
      const prev = allResponses.value.get(id) ?? ({ item_id: id } as ChecklistResponse)
      allResponses.value = new Map(allResponses.value).set(id, { ...prev, ...d } as ChecklistResponse)
    }
    return useG8Adjudication({
      wpId: computed(() => 'wp1'),
      projectId: computed(() => 'p1'),
      allResponses: allResponses as any,
      debouncedSave,
      isReadonly: computed(() => false),
    })
  }

  it('从 G8-2 带入未审到 fv_1，保留账项调整', async () => {
    const adjRows = {
      fv_1: { openingUnadjusted: 1, closingUnadjusted: 2, closingAdjustment: 50 },
    }
    const detail = [
      { investeeName: '甲', openingBalance: 100, closingBalance: 300, closingAdjusted: 350 },
      { investeeName: '乙', openingBalance: 40, closingBalance: 60, closingAdjusted: 60 },
    ]
    const adj = setup({
      'G8-adj-rows': { remark: JSON.stringify(adjRows) },
      'G8-detail-rows': { remark: JSON.stringify(detail) },
    })
    await nextTick()

    const res = adj.syncUnadjustedFromDetail()
    expect(res.count).toBe(2)
    expect(res.opening).toBe(140)
    expect(res.closing).toBe(360)

    const saved = saves.find((s) => s.id === 'G8-adj-rows')
    expect(saved).toBeTruthy()
    const store = JSON.parse(String(saved!.data.remark))
    expect(store.fv_1.openingUnadjusted).toBe(140)
    expect(store.fv_1.closingUnadjusted).toBe(360)
    expect(store.fv_1.closingAdjustment).toBe(50)
  })

  it('明细为空时带入返回 0', () => {
    const adj = setup()
    expect(adj.syncUnadjustedFromDetail().count).toBe(0)
  })

  it('与 G8-2 审定合计勾稽差异', async () => {
    const adjRows = {
      fv_1: { closingUnadjusted: 1000, closingAdjustment: 0 },
    }
    const detail = [{ closingAdjusted: 900 }]
    const adj = setup({
      'G8-adj-rows': { remark: JSON.stringify(adjRows) },
      'G8-detail-rows': { remark: JSON.stringify(detail) },
    })
    await nextTick()
    expect(adj.hasDetailCrossMismatch.value).toBe(true)
    expect(adj.detailCrossVariance.value).toBe(100)
  })

  it('结论双写 G8-adj-conclusion 与 G8-1-audit-conclusion', () => {
    const adj = setup()
    adj.updateAuditConclusion('A、未见异常')
    expect(saves.some((s) => s.id === 'G8-adj-conclusion' && s.data.conclusion === 'A、未见异常')).toBe(true)
    expect(saves.some((s) => s.id === 'G8-1-audit-conclusion' && s.data.remark === 'A、未见异常')).toBe(true)
  })
})
