import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
import { useD5ReviewThreads } from '../useD5ReviewThreads'

describe('useD5ReviewThreads', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({
      data: {
        data: {
          threads: [
            { section_id: 'D5-detail-row-abc-note', has_unread: false },
            { section_id: 'D5-detail-row-xyz-note', has_unread: true },
          ],
        },
      },
    })
  })

  it('getRowDot matches prefix-rowKey and prefers red', async () => {
    const wpId = ref('wp-d5')
    const { getRowDot, reload } = useD5ReviewThreads(wpId)
    await reload()
    expect(getRowDot('D5-detail-row', 'abc')).toBe('blue')
    expect(getRowDot('D5-detail-row', 'xyz')).toBe('red')
    expect(getRowDot('D5-detail-row', 'missing')).toBeNull()
  })
})
