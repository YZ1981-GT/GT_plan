/**
 * useD2FormData — saveItemsFromEvent 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import http from '@/utils/http'
import { useD2FormData } from '../composables/useD2FormData'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue([]),
    put: vi.fn().mockResolvedValue({}),
  },
}))

describe('useD2FormData.saveItemsFromEvent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('merges items into allResponses and triggers save', async () => {
    const wpId = ref('wp-test')
    const projectId = ref('proj-test')
    const { allResponses, saveItemsFromEvent } = useD2FormData(wpId, projectId)

    await saveItemsFromEvent([
      { item_id: 'D2-detail-rows', conclusion: null, remark: '[{"rowId":"r1"}]' },
      { item_id: 'D2-adj-reason', conclusion: null, remark: '测试说明' },
    ])

    expect(allResponses.value.get('D2-detail-rows')?.remark).toBe('[{"rowId":"r1"}]')
    expect(allResponses.value.get('D2-adj-reason')?.remark).toBe('测试说明')

    const putCalls = vi.mocked(http.put).mock.calls
    expect(putCalls).toHaveLength(2)
    expect(putCalls.map(([, body]) => body)).toEqual([
      {
        project_id: 'proj-test',
        items: [{
          item_id: 'D2-detail-rows',
          conclusion: null,
          remark: '[{"rowId":"r1"}]',
          wp_ref: null,
        }],
      },
      {
        project_id: 'proj-test',
        items: [{
          item_id: 'D2-adj-reason',
          conclusion: null,
          remark: '测试说明',
          wp_ref: null,
        }],
      },
    ])
  })

  it('ignores empty items array', async () => {
    const wpId = ref('wp-test')
    const { allResponses, saveItemsFromEvent } = useD2FormData(wpId, ref('proj'))
    const before = allResponses.value.size
    await saveItemsFromEvent([])
    expect(allResponses.value.size).toBe(before)
  })
})
