/**
 * useC24ImportExport composable 单元测试
 *
 * 验证:
 * - exportTemplate 调用正确端点并触发 blob 下载
 * - exportData 调用正确端点并触发 blob 下载
 * - importData 提交 multipart/form-data 并返回结果
 * - loading 状态正确管理
 * - 错误情况提示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const mockHttpGet = vi.fn()
const mockHttpPost = vi.fn()

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockHttpGet(...args),
    post: (...args: any[]) => mockHttpPost(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock URL.createObjectURL / revokeObjectURL
global.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
global.URL.revokeObjectURL = vi.fn()

import { useC24ImportExport } from '../useC24ImportExport'
import { ElMessage } from 'element-plus'

describe('useC24ImportExport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock document.createElement and related DOM methods
    const mockAnchor = { href: '', download: '', click: vi.fn() }
    vi.spyOn(document, 'createElement').mockReturnValue(mockAnchor as any)
    vi.spyOn(document.body, 'appendChild').mockImplementation((() => {}) as any)
    vi.spyOn(document.body, 'removeChild').mockImplementation((() => {}) as any)
  })

  describe('exportTemplate', () => {
    it('GET 正确端点并下载', async () => {
      mockHttpGet.mockResolvedValueOnce({ data: new ArrayBuffer(8) })

      const { exportTemplate } = useC24ImportExport(ref('wp-123'))
      await exportTemplate()

      expect(mockHttpGet).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/c24-journal/export-template',
        { responseType: 'blob' },
      )
      expect(ElMessage.success).toHaveBeenCalledWith('模板已导出')
    })

    it('请求失败时提示错误', async () => {
      mockHttpGet.mockRejectedValueOnce({
        response: { data: { message: '模板不存在' } },
      })

      const { exportTemplate } = useC24ImportExport(ref('wp-123'))
      await exportTemplate()

      expect(ElMessage.error).toHaveBeenCalledWith('模板不存在')
    })
  })

  describe('exportData', () => {
    it('GET 正确端点并下载', async () => {
      mockHttpGet.mockResolvedValueOnce({ data: new ArrayBuffer(8) })

      const { exportData } = useC24ImportExport(ref('wp-456'))
      await exportData()

      expect(mockHttpGet).toHaveBeenCalledWith(
        '/api/workpapers/wp-456/c24-journal/export-data',
        { responseType: 'blob' },
      )
      expect(ElMessage.success).toHaveBeenCalledWith('数据已导出')
    })

    it('请求失败时提示错误', async () => {
      mockHttpGet.mockRejectedValueOnce({ message: '网络错误' })

      const { exportData } = useC24ImportExport(ref('wp-456'))
      await exportData()

      expect(ElMessage.error).toHaveBeenCalledWith('网络错误')
    })
  })

  describe('importData', () => {
    it('POST multipart/form-data 正确端点', async () => {
      mockHttpPost.mockResolvedValueOnce({
        data: { data: { imported_count: 150 } },
      })

      const { importData } = useC24ImportExport(ref('wp-789'))
      const file = new File(['test'], 'journal.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const result = await importData(file)

      expect(mockHttpPost).toHaveBeenCalled()
      const [url, formData, config] = mockHttpPost.mock.calls[0]
      expect(url).toBe('/api/workpapers/wp-789/c24-journal/import-data')
      expect(formData).toBeInstanceOf(FormData)
      expect(config.headers['Content-Type']).toBe('multipart/form-data')
      expect(result).toEqual({ rowCount: 150, warning: undefined })
      expect(ElMessage.success).toHaveBeenCalledWith('成功导入 150 条分录')
    })

    it('导入有警告时显示在消息中', async () => {
      mockHttpPost.mockResolvedValueOnce({
        data: { data: { imported_count: 98, warning: '2行数据格式异常已跳过' } },
      })

      const { importData } = useC24ImportExport(ref('wp-789'))
      const file = new File(['test'], 'journal.xlsx')
      const result = await importData(file)

      expect(result).toEqual({ rowCount: 98, warning: '2行数据格式异常已跳过' })
      expect(ElMessage.success).toHaveBeenCalledWith('成功导入 98 条分录（2行数据格式异常已跳过）')
    })

    it('导入失败返回null并提示错误', async () => {
      mockHttpPost.mockRejectedValueOnce({
        response: { data: { detail: '列名不匹配' } },
      })

      const { importData } = useC24ImportExport(ref('wp-789'))
      const file = new File(['test'], 'bad.xlsx')
      const result = await importData(file)

      expect(result).toBeNull()
      expect(ElMessage.error).toHaveBeenCalledWith('列名不匹配')
    })

    it('非字符串错误消息显示通用提示', async () => {
      mockHttpPost.mockRejectedValueOnce({
        response: { data: { detail: ['col1', 'col2'] } },
      })

      const { importData } = useC24ImportExport(ref('wp-789'))
      const file = new File(['test'], 'bad.xlsx')
      const result = await importData(file)

      expect(result).toBeNull()
      expect(ElMessage.error).toHaveBeenCalledWith('导入数据格式错误')
    })
  })

  describe('loading 状态', () => {
    it('exportTemplate 期间 loading=true', async () => {
      let resolveGet: any
      mockHttpGet.mockImplementationOnce(() => new Promise(r => { resolveGet = r }))

      const { exportTemplate, loading } = useC24ImportExport(ref('wp-1'))
      expect(loading.value).toBe(false)

      const p = exportTemplate()
      expect(loading.value).toBe(true)

      resolveGet({ data: new ArrayBuffer(8) })
      await p
      expect(loading.value).toBe(false)
    })

    it('importData 期间 loading=true', async () => {
      let resolvePost: any
      mockHttpPost.mockImplementationOnce(() => new Promise(r => { resolvePost = r }))

      const { importData, loading } = useC24ImportExport(ref('wp-1'))
      const file = new File(['x'], 'test.xlsx')

      const p = importData(file)
      expect(loading.value).toBe(true)

      resolvePost({ data: { data: { imported_count: 1 } } })
      await p
      expect(loading.value).toBe(false)
    })
  })

  describe('wpId 响应性', () => {
    it('使用 unref 解包 ref 值', async () => {
      mockHttpGet.mockResolvedValueOnce({ data: new ArrayBuffer(8) })

      const wpId = ref('dynamic-wp-id')
      const { exportTemplate } = useC24ImportExport(wpId)
      await exportTemplate()

      expect(mockHttpGet).toHaveBeenCalledWith(
        '/api/workpapers/dynamic-wp-id/c24-journal/export-template',
        expect.any(Object),
      )
    })

    it('支持传入普通字符串', async () => {
      mockHttpGet.mockResolvedValueOnce({ data: new ArrayBuffer(8) })

      const { exportData } = useC24ImportExport('plain-wp-id')
      await exportData()

      expect(mockHttpGet).toHaveBeenCalledWith(
        '/api/workpapers/plain-wp-id/c24-journal/export-data',
        expect.any(Object),
      )
    })
  })
})
