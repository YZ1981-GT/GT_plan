import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

import http from '@/utils/http'
import { useD7ImportExport } from '../useD7ImportExport'

describe('useD7ImportExport', () => {
  const wpId = ref('wp-d7')

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('importData calls d7 import endpoint for D7-7-period', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { ok: true, imported_count: 2 } },
    })
    const { importData } = useD7ImportExport({
      wpId,
      sheetCode: 'D7-7-period',
    })
    const file = new File(['x'], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const result = await importData(file)
    expect(result.success).toBe(true)
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d7/d7/import-data',
      expect.any(FormData),
      expect.objectContaining({ params: { sheet: 'D7-7-period' } }),
    )
  })
})
