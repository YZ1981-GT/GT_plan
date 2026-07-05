import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useD3ImportExport } from '../useD3ImportExport'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

import http from '@/utils/http'

describe('useD3ImportExport', () => {
  const wpId = ref('wp-test')

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exportTemplate 请求正确 endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: new ArrayBuffer(8) })
    const { exportTemplate } = useD3ImportExport({ wpId, sheetCode: 'D3-2' })
    await exportTemplate()
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-test/d3/export-template',
      null,
      expect.objectContaining({ params: { sheet: 'D3-2' } }),
    )
  })

  it('importData 解析 imported_count', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { ok: true, imported_count: 5, field_count: 12 } },
    })
    const { importData } = useD3ImportExport({ wpId, sheetCode: 'D3-5' })
    const file = new File(['x'], 'test.xlsx')
    const result = await importData(file)
    expect(result.success).toBe(true)
    expect(result.rowCount).toBe(5)
  })

  it('D3-1 审定表导出请求正确 endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: new ArrayBuffer(8) })
    const { exportData } = useD3ImportExport({ wpId, sheetCode: 'D3-1' })
    await exportData()
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-test/d3/export-data',
      null,
      expect.objectContaining({ params: { sheet: 'D3-1' } }),
    )
  })

  it('D3-3 调整分录导入请求正确 endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { ok: true, imported_count: 2 },
    })
    const { importData } = useD3ImportExport({ wpId, sheetCode: 'D3-3' })
    const file = new File(['x'], 'adj.xlsx')
    const result = await importData(file)
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-test/d3/import-data',
      expect.any(FormData),
      expect.objectContaining({ params: { sheet: 'D3-3' } }),
    )
    expect(result.success).toBe(true)
    expect(result.rowCount).toBe(2)
  })
})
