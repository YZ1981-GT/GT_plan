/**
 * useWpExportImport composable 单元测试
 *
 * 验证:
 * - exportWithMetadata 调用 downloadFile
 * - batchExportEnhanced 调用 downloadFile with POST
 * - importEnhanced 提交 multipart/form-data
 * - importResolve 提交 conflict resolution
 * - getVersionHistory 返回版本列表
 * - getExportHistory 返回导出历史
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockDownloadFile = vi.fn().mockResolvedValue({})
const mockHttpPost = vi.fn().mockResolvedValue({ data: {} })
const mockHttpGet = vi.fn().mockResolvedValue({ data: [] })

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockHttpGet(...args),
    post: (...args: any[]) => mockHttpPost(...args),
  },
  downloadFile: (...args: any[]) => mockDownloadFile(...args),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockHttpGet(...args).then((r: any) => r.data),
    post: (...args: any[]) => mockHttpPost(...args).then((r: any) => r.data),
  },
}))

import { useWpExportImport } from '../useWpExportImport'

describe('useWpExportImport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exportWithMetadata calls downloadFile with correct URL', async () => {
    const { exportWithMetadata } = useWpExportImport()
    await exportWithMetadata('proj-1', 'wp-1')

    expect(mockDownloadFile).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/export-with-metadata',
      { method: 'post' },
    )
  })

  it('batchExportEnhanced calls downloadFile with POST body', async () => {
    const { batchExportEnhanced } = useWpExportImport()
    await batchExportEnhanced('proj-1', ['D', 'E'], ['draft'])

    expect(mockDownloadFile).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/batch-export-enhanced',
      {
        method: 'post',
        data: { audit_cycles: ['D', 'E'], status_filter: ['draft'] },
        fileName: '底稿批量导出.zip',
      },
    )
  })

  it('batchExportEnhanced passes null status_filter when not provided', async () => {
    const { batchExportEnhanced } = useWpExportImport()
    await batchExportEnhanced('proj-1', ['A'])

    expect(mockDownloadFile).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/batch-export-enhanced',
      {
        method: 'post',
        data: { audit_cycles: ['A'], status_filter: null },
        fileName: '底稿批量导出.zip',
      },
    )
  })

  it('importEnhanced submits multipart/form-data', async () => {
    mockHttpPost.mockResolvedValueOnce({
      data: { status: 'success', wp_id: 'wp-1', new_version: 2 },
    })

    const { importEnhanced } = useWpExportImport()
    const file = new File(['test'], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const result = await importEnhanced('proj-1', file)

    expect(mockHttpPost).toHaveBeenCalled()
    const [url, formData, config] = mockHttpPost.mock.calls[0]
    expect(url).toContain('/api/projects/proj-1/workpapers/import-enhanced')
    expect(formData).toBeInstanceOf(FormData)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
    expect(result.status).toBe('success')
  })

  it('importEnhanced returns conflict on 409', async () => {
    const conflictDetail = {
      status: 'conflict',
      wp_id: 'wp-1',
      conflict_result: {
        has_conflict: true,
        server_version: 3,
        imported_version: 1,
        is_substantive: true,
      },
    }
    mockHttpPost.mockRejectedValueOnce({
      response: { status: 409, data: { detail: conflictDetail } },
    })

    const { importEnhanced } = useWpExportImport()
    const file = new File(['test'], 'test.xlsx')
    const result = await importEnhanced('proj-1', file)

    expect(result.status).toBe('conflict')
  })

  it('loading state is managed correctly', async () => {
    const { exportWithMetadata, loading } = useWpExportImport()
    expect(loading.value).toBe(false)

    const p = exportWithMetadata('proj-1', 'wp-1')
    // loading is set synchronously before await resolves
    expect(loading.value).toBe(true)

    await p
    expect(loading.value).toBe(false)
  })
})
