/**
 * useG13Adjudication — 审定表与 G13-2 同步
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG13Adjudication } from '../useG13Adjudication'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: [] }) },
}))

describe('useG13Adjudication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('detailCrossValidation 无明细数据时为 null', () => {
    const adj = useG13Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses: ref(new Map()),
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(adj.detailCrossValidation.value).toBeNull()
    expect(adj.hasDetailData.value).toBe(false)
  })

  it('本期数自 G13-2 明细按科目汇总', () => {
    const allResponses = ref(new Map<string, any>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '测试工具',
          belongAccount: 'G1',
          currentUnadjusted: 500,
          adjustment: 20,
          currentAudited: 520,
        }]),
      }],
    ]))
    const adj = useG13Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    const adjRow = adj.dataRows.value.find((r) => r.rowKey === 'trading_assets')
    expect(adjRow?.currentUnadjusted).toBe(500)
    expect(adjRow?.currentAudited).toBe(520)
    expect(adj.hasDetailData.value).toBe(true)
    expect(adj.totalRow.value.currentAudited).toBe(520)
    expect(adj.detail.grandTotalAudited.value).toBe(520)
    expect(adj.detailCrossValidation.value).toBeNull()
  })
})
