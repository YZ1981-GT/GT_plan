/**
 * useG8Disclosure — 附注 AI section + 与 G8-1 勾稽（模板分表结构）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: vi.fn(async (_url: string, body: any) => ({
      data: { content: `AI:${body?.variant || 'x'}` },
    })),
  },
}))

import { api } from '@/services/apiProxy'
import { useG8Disclosure } from '../useG8Disclosure'
import {
  G8_LISTED_BALANCE_SLOTS,
  G8_LISTED_OCI_SLOTS,
  G8_SOE_BALANCE_SLOTS,
  G8_SOE_DETAIL_SLOTS,
  migrateLegacyDisclosureStore,
} from '../g8SchemaRows'

function makeMap(entries: Record<string, Partial<ChecklistResponse>> = {}) {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse)
  }
  return m
}

describe('useG8Disclosure', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>
  let saves: Array<{ id: string; data: Partial<ChecklistResponse> }>

  beforeEach(() => {
    saves = []
    allResponses = ref(makeMap())
    vi.mocked(api.post).mockClear()
  })

  function setup(extra: Record<string, Partial<ChecklistResponse>> = {}, variant: 'listed' | 'soe' = 'listed') {
    allResponses.value = makeMap(extra)
    const debouncedSave = (id: string, d: Partial<ChecklistResponse>) => {
      saves.push({ id, data: d })
      const prev = allResponses.value.get(id) ?? ({ item_id: id } as ChecklistResponse)
      allResponses.value = new Map(allResponses.value).set(id, { ...prev, ...d } as ChecklistResponse)
    }
    return useG8Disclosure({
      variant,
      wpId: computed(() => 'wp1'),
      allResponses: allResponses as any,
      debouncedSave,
      isReadonly: computed(() => false),
    })
  }

  it('AI 汇总调用 disclosure-listed-note 而非 adjudication-analysis', async () => {
    const disc = setup()
    await disc.generateAiConclusion()
    expect(api.post).toHaveBeenCalled()
    const url = String(vi.mocked(api.post).mock.calls[0][0])
    expect(url).toContain('/g8/ai/disclosure-listed-note')
    expect(url).not.toContain('adjudication-analysis')
  })

  it('国企变体调用 disclosure-soe-note', async () => {
    const disc = setup({}, 'soe')
    await disc.generateAiConclusion()
    const url = String(vi.mocked(api.post).mock.calls[0][0])
    expect(url).toContain('/g8/ai/disclosure-soe-note')
  })

  it('模板槽位：上市余额3+合计、OCI3；国企余额3+合计、明细4+合计', async () => {
    const listed = setup()
    await nextTick()
    expect(listed.balanceRows.value).toHaveLength(G8_LISTED_BALANCE_SLOTS + 1)
    expect(listed.balanceRows.value.at(-1)?.isTotal).toBe(true)
    expect(listed.ociRows.value).toHaveLength(G8_LISTED_OCI_SLOTS)

    const soe = setup({}, 'soe')
    await nextTick()
    expect(soe.balanceRows.value).toHaveLength(G8_SOE_BALANCE_SLOTS + 1)
    expect(soe.detailRows.value).toHaveLength(G8_SOE_DETAIL_SLOTS + 1)
    expect(soe.detailRows.value.at(-1)?.isTotal).toBe(true)
  })

  it('余额合计与审定数差异时 hasAdjCrossMismatch', async () => {
    const disc = setup({
      'G8-1-adjudicated-amount': { conclusion: '1000' },
      'G8-disclosure-listed': {
        remark: JSON.stringify({
          v: 2,
          balanceRows: [
            { label: 'A', closing: 800, prior: 0 },
            { label: '', closing: 0, prior: 0 },
            { label: '', closing: 0, prior: 0 },
          ],
          designationText: '',
          ociRows: [],
        }),
      },
    })
    await nextTick()
    expect(disc.adjudicatedAmount.value).toBe(1000)
    expect(disc.primaryCurrentAmount.value).toBe(800)
    expect(disc.hasAdjCrossMismatch.value).toBe(true)
    expect(disc.adjCrossVariance.value).toBe(-200)
  })

  it('写入审定数后勾稽一致', async () => {
    const disc = setup({
      'G8-1-adjudicated-amount': { conclusion: '1000' },
      'G8-disclosure-listed': {
        remark: JSON.stringify({
          v: 2,
          balanceRows: [
            { label: 'A', closing: 800, prior: 0 },
            { label: '', closing: 0, prior: 0 },
            { label: '', closing: 0, prior: 0 },
          ],
          designationText: '',
          ociRows: [],
        }),
      },
    })
    await nextTick()
    disc.pullLatestAdjudicated(true)
    expect(disc.primaryCurrentAmount.value).toBe(1000)
    expect(disc.hasAdjCrossMismatch.value).toBe(false)
  })

  it('兼容旧扁平键 listed_bal_1.currentAmount', async () => {
    const disc = setup({
      'G8-1-adjudicated-amount': { conclusion: '1000' },
      'G8-disclosure-listed': {
        remark: JSON.stringify({ listed_bal_1: { currentAmount: 800, priorAmount: 0, noteText: '' } }),
      },
    })
    await nextTick()
    expect(disc.primaryCurrentAmount.value).toBe(800)
    expect(disc.hasAdjCrossMismatch.value).toBe(true)
  })

  it('syncFromDetail 从 G8-2 写入余额合计', async () => {
    const disc = setup({
      'G8-detail-rows': {
        remark: JSON.stringify([
          { investeeName: '甲', closingAdjusted: 600, openingAdjusted: 100, ociCurrentChange: 20, ociCumulativeChange: 80 },
          { investeeName: '乙', closingAdjusted: 400, openingAdjusted: 50, ociCurrentChange: 10, ociCumulativeChange: 40 },
        ]),
      },
    })
    await nextTick()
    const res = disc.syncFromDetail(true)
    expect(res.sourceCount).toBe(2)
    expect(disc.primaryCurrentAmount.value).toBe(1000)
    expect(disc.balanceRows.value[0].label).toBe('甲')
    expect(disc.designationText.value.length).toBeGreaterThan(0)
  })
})

describe('migrateLegacyDisclosureStore', () => {
  it('空值得到模板槽位', () => {
    const listed = migrateLegacyDisclosureStore(null, 'listed')
    expect(listed.v).toBe(2)
    expect(listed.balanceRows).toHaveLength(3)
    expect(listed.ociRows).toHaveLength(3)
    const soe = migrateLegacyDisclosureStore(null, 'soe')
    expect(soe.balanceRows).toHaveLength(3)
    expect(soe.detailRows).toHaveLength(4)
  })
})
