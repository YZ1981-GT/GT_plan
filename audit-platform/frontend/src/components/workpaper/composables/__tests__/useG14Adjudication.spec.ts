/**
 * useG14Adjudication — 审定表与 G14-2 同步
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG14Adjudication } from '../useG14Adjudication'
import { G14_CHANGE_RATE_THRESHOLD } from '../g14Constants'
import { isChangeRateExceeding } from '../useG14FormulaEngine'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: [] }) },
}))

describe('useG14Adjudication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('本期数自 G14-2 明细同步', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1000)
    adj.detail.updateCell('ar', 'currentAdjustment', 50)

    const row = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row?.currentUnadjusted).toBe(1000)
    expect(row?.currentAdjustment).toBe(50)
    expect(row?.currentAudited).toBe(1050)
  })

  it('|变动率|>30% 触发原因必填', () => {
    const rate = 0.35
    expect(isChangeRateExceeding(rate, G14_CHANGE_RATE_THRESHOLD)).toBe(true)
    expect(isChangeRateExceeding(0.2, G14_CHANGE_RATE_THRESHOLD)).toBe(false)
  })

  it('明细与审定同步时 detailCrossValidation 为 null', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1000)
    adj.detail.updateCell('ar', 'currentAdjustment', 50)

    expect(adj.detailMismatch.value).toBe(false)
    expect(adj.detailCrossValidation.value).toBeNull()
  })
})
