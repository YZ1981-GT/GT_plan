/**
 * Unit Tests — useD1ImportExport composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 19.2
 *
 * 验证通用导入导出 composable 的三个方法：
 * - exportTemplate: 调用正确 API endpoint + 触发 blob 下载
 * - exportData: 调用正确 API endpoint + 触发 blob 下载
 * - importData: 上传 file + 返回 ImportResult
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useD1ImportExport, type ImportResult } from '../useD1ImportExport'

// ─── Mock http ─────────────────────────────────────────────────────────────

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

import http from '@/utils/http'

const mockPost = http.post as ReturnType<typeof vi.fn>

// ─── Mock DOM APIs ─────────────────────────────────────────────────────────

let clickedHref = ''
let clickedDownload = ''

beforeEach(() => {
  clickedHref = ''
  clickedDownload = ''

  // Mock URL.createObjectURL / revokeObjectURL
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:mock-url'),
    revokeObjectURL: vi.fn(),
  })

  // Mock document.createElement('a')
  vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
    if (tagName === 'a') {
      return {
        href: '',
        download: '',
        click() {
          clickedHref = this.href
          clickedDownload = this.download
        },
      } as any
    }
    return document.createElement(tagName)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ─── Tests ─────────────────────────────────────────────────────────────────

describe('useD1ImportExport', () => {
  const wpId = ref('wp-123')

  describe('exportTemplate', () => {
    it('calls correct API endpoint and triggers download with correct filename', async () => {
      mockPost.mockResolvedValueOnce({ data: new Blob(['mock'], { type: 'application/octet-stream' }) })

      const { exportTemplate } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-10',
        sheetLabel: '监盘表',
      })

      await exportTemplate()

      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/d1/export-template',
        null,
        { params: { sheet: 'D1-10' }, responseType: 'blob' },
      )
      expect(clickedDownload).toBe('D1-10_监盘表模板.xlsx')
      expect(clickedHref).toBe('blob:mock-url')
    })

    it('uses correct sheetCode/sheetLabel for D1-12', async () => {
      mockPost.mockResolvedValueOnce({ data: new Blob(['mock']) })

      const { exportTemplate } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-12',
        sheetLabel: '质押检查',
      })

      await exportTemplate()

      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/d1/export-template',
        null,
        { params: { sheet: 'D1-12' }, responseType: 'blob' },
      )
      expect(clickedDownload).toBe('D1-12_质押检查模板.xlsx')
    })
  })

  describe('exportData', () => {
    it('calls correct API endpoint and triggers download with correct filename', async () => {
      mockPost.mockResolvedValueOnce({ data: new Blob(['mock']) })

      const { exportData } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-11',
        sheetLabel: '关联方检查',
      })

      await exportData()

      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/d1/export-data',
        null,
        { params: { sheet: 'D1-11' }, responseType: 'blob' },
      )
      expect(clickedDownload).toBe('D1-11_关联方检查数据.xlsx')
    })
  })

  describe('importData', () => {
    it('uploads file with FormData and returns success result', async () => {
      mockPost.mockResolvedValueOnce({
        data: { row_count: 5, field_count: 13 },
      })

      const { importData } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-13',
        sheetLabel: '凭证核对',
      })

      const file = new File(['test'], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const result: ImportResult = await importData(file)

      expect(result.success).toBe(true)
      expect(result.rowCount).toBe(5)
      expect(result.fieldCount).toBe(13)
      expect(result.errors).toBeUndefined()

      // Verify FormData was sent
      const callArgs = mockPost.mock.calls[0]
      expect(callArgs[0]).toBe('/api/workpapers/wp-123/d1/import-data')
      expect(callArgs[1]).toBeInstanceOf(FormData)
      expect(callArgs[2]).toEqual({
        params: { sheet: 'D1-13' },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    })

    it('handles wrapped response data (data.data pattern)', async () => {
      mockPost.mockResolvedValueOnce({
        data: { data: { row_count: 3, field_count: 16 } },
      })

      const { importData } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-12',
        sheetLabel: '质押检查',
      })

      const file = new File(['test'], 'test.xlsx')
      const result = await importData(file)

      expect(result.success).toBe(true)
      expect(result.rowCount).toBe(3)
      expect(result.fieldCount).toBe(16)
    })

    it('returns error result on API failure', async () => {
      mockPost.mockRejectedValueOnce({
        response: { data: { message: '列名不匹配：缺少"票据号码"列' } },
      })

      const { importData } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-10',
        sheetLabel: '监盘表',
      })

      const file = new File(['bad'], 'bad.xlsx')
      const result = await importData(file)

      expect(result.success).toBe(false)
      expect(result.rowCount).toBe(0)
      expect(result.fieldCount).toBe(0)
      expect(result.errors).toEqual(['列名不匹配：缺少"票据号码"列'])
    })

    it('returns generic error when no response message', async () => {
      mockPost.mockRejectedValueOnce(new Error('Network Error'))

      const { importData } = useD1ImportExport({
        wpId,
        sheetCode: 'D1-10',
        sheetLabel: '监盘表',
      })

      const file = new File(['bad'], 'bad.xlsx')
      const result = await importData(file)

      expect(result.success).toBe(false)
      expect(result.errors).toEqual(['Network Error'])
    })
  })

  describe('reactive wpId', () => {
    it('uses current wpId value at call time', async () => {
      const dynamicWpId = ref('wp-A')
      mockPost.mockResolvedValue({ data: new Blob(['x']) })

      const { exportTemplate } = useD1ImportExport({
        wpId: dynamicWpId,
        sheetCode: 'D1-10',
        sheetLabel: '监盘表',
      })

      await exportTemplate()
      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-A/d1/export-template',
        null,
        expect.anything(),
      )

      // Change wpId
      dynamicWpId.value = 'wp-B'
      await exportTemplate()
      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-B/d1/export-template',
        null,
        expect.anything(),
      )
    })
  })
})
