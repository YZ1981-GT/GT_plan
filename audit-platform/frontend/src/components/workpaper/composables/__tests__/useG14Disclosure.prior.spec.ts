/**
 * useG14Disclosure — 上期回算与明细刷新
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG14Disclosure } from '../useG14Disclosure'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn().mockResolvedValue({ data: {} }) },
}))

describe('useG14Disclosure prior sync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('拉取上期时用 priorUnadjusted+priorAdjustment 回算（无 priorAudited）', () => {
    const allResponses = ref(new Map<string, any>([
      ['G14-adj-prior', {
        item_id: 'G14-adj-prior',
        remark: JSON.stringify({
          ar: { priorUnadjusted: 800, priorAdjustment: 200 },
          notes: { priorUnadjusted: 100, priorAdjustment: 0 },
        }),
      }],
      ['G14-detail-rows', {
        item_id: 'G14-detail-rows',
        remark: JSON.stringify([
          { rowKey: 'ar', currentAudited: 1200 },
          { rowKey: 'notes', currentAudited: 50 },
        ]),
      }],
    ]))

    const disc = useG14Disclosure({
      variant: 'listed',
      allResponses,
      debouncedSave: vi.fn(),
      wpId: ref('wp-1'),
      isReadonly: ref(false),
    })

    disc.pullLatestAdjudicated()

    const ar = disc.rows.value.find((r) => r.rowKey === 'ar')
    const notes = disc.rows.value.find((r) => r.rowKey === 'notes')
    expect(ar?.priorAmount).toBe(1000)
    expect(notes?.priorAmount).toBe(100)
  })
})
