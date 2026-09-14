/**
 * useG9Disclosure — 合计 / 勾稽 / 分项带入
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn(async () => ({ data: { content: 'AI文案' } })) },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

import { useG9Disclosure } from '../useG9Disclosure'

function makeMap(entries: Record<string, Partial<ChecklistResponse>> = {}) {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse)
  }
  return m
}

describe('useG9Disclosure', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>
  let saves: Array<{ id: string; data: Partial<ChecklistResponse> }>

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
    return useG9Disclosure({
      variant: 'listed',
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave,
      isReadonly: ref(false),
    })
  }

  it('表头为上市口径 + 含合计行', () => {
    const disc = setup()
    expect(disc.colLabels.value.item).toBe('种  类')
    expect(disc.colLabels.value.current).toBe('期末余额')
    expect(disc.rows.value).toHaveLength(5)
    expect(disc.rows.value[4].isTotal).toBe(true)
    expect(disc.rows.value[4].label).toContain('合')
  })

  it('勾稽差异：合计 vs 审定数', () => {
    const disc = setup({
      'G9-disclosure-listed': {
        remark: JSON.stringify({
          listed_1: { currentAmount: 60, priorAmount: 0, noteText: '' },
          listed_2: { currentAmount: 40, priorAmount: 0, noteText: '' },
        }),
      },
      'G9-1-adjudicated-amount': { conclusion: '90' },
    })
    expect(disc.disclosureCurrentSum.value).toBe(100)
    expect(disc.hasAdjCrossMismatch.value).toBe(true)
    expect(disc.adjCrossVariance.value).toBe(10)
  })

  it('从明细工具种类分项带入', () => {
    const disc = setup({
      'G9-1-adjudicated-amount': { conclusion: '150' },
      'G9-detail-rows': {
        remark: JSON.stringify([
          {
            assetName: '债A',
            instrumentType: '债务工具投资',
            closingAdjusted: 100,
            openingAdjusted: 50,
          },
          {
            assetName: '权B',
            instrumentType: '权益工具投资',
            closingAdjusted: 50,
            openingAdjusted: 20,
          },
        ]),
      },
    })
    disc.pullFromAdjudication()
    expect(disc.dataRows.value.find((r) => r.rowKey === 'listed_1')?.currentAmount).toBe(100)
    expect(disc.dataRows.value.find((r) => r.rowKey === 'listed_2')?.currentAmount).toBe(50)
    expect(disc.disclosureCurrentSum.value).toBe(150)
    expect(disc.hasAdjCrossMismatch.value).toBe(false)
    expect(disc.pullSummary.value).toMatch(/债务←G9-2/)
    expect(saves.some((s) => s.id === 'G9-disclosure-listed')).toBe(true)
  })

  it('无分项时残差写入其他，并标记 usedResidual', () => {
    const disc = setup({
      'G9-1-adjudicated-amount': { conclusion: '888' },
    })
    disc.pullFromAdjudication()
    expect(disc.lastPullUsedResidual.value).toBe(true)
    expect(disc.dataRows.value.find((r) => r.rowKey === 'listed_4')?.currentAmount).toBe(888)
  })
})
