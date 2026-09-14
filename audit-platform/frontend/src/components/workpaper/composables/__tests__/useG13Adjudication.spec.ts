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

  it('「其中」备忘行不计入审定合计', () => {
    const allResponses = ref(new Map<string, any>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '交易性',
          belongAccount: 'G1',
          currentUnadjusted: 1000,
          adjustment: 0,
        }]),
      }],
      ['G13-adj-prior', {
        remark: JSON.stringify({
          designated_fv_assets: { currentUnadjusted: 200, currentAdjustment: 0 },
        }),
      }],
    ]))
    const adj = useG13Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    const ofWhich = adj.dataRows.value.find((r) => r.rowKey === 'designated_fv_assets')
    expect(ofWhich?.currentAudited).toBe(200)
    expect(ofWhich?.kind).toBe('ofWhich')
    expect(adj.totalRow.value.currentAudited).toBe(1000)
  })

  it('旧 priorStore key 迁移到新行键', () => {
    const allResponses = ref(new Map<string, any>([
      ['G13-adj-prior', {
        remark: JSON.stringify({
          designated_fv: { priorUnadjusted: 80, priorAdjustment: 0 },
          derivatives: { priorUnadjusted: 40, priorAdjustment: 0 },
        }),
      }],
    ]))
    const adj = useG13Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(adj.dataRows.value.find((r) => r.rowKey === 'other_noncurrent')?.priorAudited).toBe(80)
    expect(adj.dataRows.value.find((r) => r.rowKey === 'derivative_assets')?.priorAudited).toBe(40)
  })

  it('G13-3 overlay 优先作为本期调整数写入审定表', () => {
    const allResponses = ref(new Map<string, any>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '房产',
          belongAccount: 'H3',
          currentUnadjusted: 1000,
          adjustment: 0,
        }]),
      }],
      ['G13-aje-adj-overlay', {
        remark: JSON.stringify({ investment_property: 80, trading_assets: 0 }),
      }],
    ]))
    const adj = useG13Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(adj.hasAjeOverlay.value).toBe(true)
    const ip = adj.dataRows.value.find((r) => r.rowKey === 'investment_property')
    expect(ip?.currentUnadjusted).toBe(1000)
    expect(ip?.currentAdjustment).toBe(80)
    expect(ip?.currentAudited).toBe(1080)
  })
})
