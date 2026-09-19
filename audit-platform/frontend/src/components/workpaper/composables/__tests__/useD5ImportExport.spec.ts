import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useD5ImportExport } from '../useD5ImportExport'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

import http from '@/utils/http'

describe('useD5ImportExport', () => {
  const wpId = ref('wp-d5')

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('D5-1 审定表导出请求正确 endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: new ArrayBuffer(8) })
    const { exportData } = useD5ImportExport({ wpId, sheetCode: 'D5-1' })
    await exportData()
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d5/d5/export-data',
      null,
      expect.objectContaining({ params: { sheet: 'D5-1' } }),
    )
  })

  it('D5-3 调整分录导入请求正确 endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { ok: true, imported_count: 3 },
    })
    const { importData } = useD5ImportExport({ wpId, sheetCode: 'D5-3' })
    const file = new File(['x'], 'adj.xlsx')
    const result = await importData(file)
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d5/d5/import-data',
      expect.any(FormData),
      expect.objectContaining({ params: { sheet: 'D5-3' } }),
    )
    expect(result.success).toBe(true)
    expect(result.rowCount).toBe(3)
  })
})
