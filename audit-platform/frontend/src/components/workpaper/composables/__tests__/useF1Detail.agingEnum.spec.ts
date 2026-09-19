/**
 * useF1Detail — 账龄枚举口径（3年段/5年段/自定义）与快捷分配
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useF1Detail } from '../useF1Detail'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockRejectedValue(new Error('no aging api')), post: vi.fn() },
}))

vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return {
    ...actual,
    useAgingConfig: () => ({
      segments: ref(actual.PRESET_SEGMENTS.THREE_YEAR),
      bands: ref([]),
      preset: ref('THREE_YEAR' as const),
      loading: ref(false),
      refresh: vi.fn(),
    }),
  }
})

describe('useF1Detail aging enum', () => {
  beforeEach(() => {
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  function setup(map = new Map<string, ChecklistResponse>()) {
    const save = vi.fn()
    const api = useF1Detail({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: save,
      debouncedSave: save,
      isReadonly: ref(false),
      relatedParties: ref([]),
    })
    return { api, save }
  }

  it('默认 3 年段；切换 5 年段后 bands 含 3-4 年枚举标签', async () => {
    const { api, save } = setup()
    await nextTick()
    expect(api.agingPreset.value).toBe('THREE_YEAR')
    expect(api.bands.value).toHaveLength(4)
    expect(api.bands.value[0].label).toContain('1年以内')

    expect(api.setAgingPreset('FIVE_YEAR')).toBe(true)
    await nextTick()
    expect(api.agingPreset.value).toBe('FIVE_YEAR')
    expect(api.segments.value).toHaveLength(6)
    expect(api.bands.value.some(b => b.key === 'y3to4')).toBe(true)
    expect(api.bands.value.find(b => b.key === 'y3to4')?.label).toContain('3至4年')
    expect(save).toHaveBeenCalledWith(
      'F1-det-aging-preset',
      expect.objectContaining({ remark: 'FIVE_YEAR' }),
    )
  })

  it('自定义账龄段：至少 2 段，bands 按自定义 label 生成', async () => {
    const { api, save } = setup()
    await nextTick()
    expect(api.setAgingPreset('CUSTOM', ['短期', '中期', '长期'])).toBe(true)
    await nextTick()
    expect(api.agingPreset.value).toBe('CUSTOM')
    expect(api.segments.value).toHaveLength(3)
    expect(api.bands.value.map(b => b.label)).toEqual(['短期', '中期', '长期'])
    expect(save).toHaveBeenCalledWith(
      'F1-det-aging-custom-segments',
      expect.objectContaining({ remark: JSON.stringify(['短期', '中期', '长期']) }),
    )
  })

  it('自定义少于 2 段时拒绝', async () => {
    const { api } = setup()
    await nextTick()
    expect(api.setAgingPreset('CUSTOM', ['仅一段'])).toBe(false)
    expect(api.agingPreset.value).toBe('THREE_YEAR')
  })

  it('账龄分配：将期末审定整笔填入枚举档位，其余段清零', async () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-rows', {
      item_id: 'F1-det-rows',
      conclusion: null,
      remark: JSON.stringify([{
        rowId: 'r1',
        customerName: '甲',
        priorUnadjusted: 100,
        priorAdjustment: 0,
        priorReclass: 0,
        priorAudited: 100,
        debit: 0,
        credit: 0,
        endBalance: 100,
        entityReclass: 0,
        endUnadjusted: 100,
        endAje: 0,
        endRje: 0,
        endAudited: 100,
        agingPrior: { within1: 100, y1to2: 0, y2to3: 0, over3: 0 },
        agingCurrent: { within1: 100, y1to2: 0, y2to3: 0, over3: 0 },
        agingAudited: { within1: 100, y1to2: 0, y2to3: 0, over3: 0 },
      }]),
    })
    const { api } = setup(map)
    await nextTick()
    api.allocateAging('r1', 'audited', 'y1to2')
    await nextTick()
    const row = api.rows.value.find(r => r.rowId === 'r1')!
    expect(row.agingAudited.y1to2).toBe(100)
    expect(row.agingAudited.within1).toBe(0)
  })
})
