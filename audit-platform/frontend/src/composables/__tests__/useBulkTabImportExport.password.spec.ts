/**
 * useBulkTabImportExport — 批量导出的密码透传与 blob 错误体
 *
 * Spec: .kiro/specs/environment-hygiene-deps-and-scratch-schemas/ Requirement 4.4
 *
 * 🔴 两处缺陷的反向判据：
 *  - 模板导出原先不带 password：对话框对模板导出同样显示「密码保护」框，用户设了密码仍拿到明文 ZIP
 *  - blob 下载失败时错误体也是 Blob，原先只能显示 axios 英文 `Request failed with status code 503`，
 *    后端给的中文原因（如「服务器未安装 AES 加密组件…」）用户看不到
 */
import { describe, it, expect, vi, beforeEach, beforeAll, afterAll } from 'vitest'
import { ref } from 'vue'

/**
 * jsdom 25 的 Blob 没有 `text()`（所有目标浏览器都有，生产代码用的就是这个标准 API）。
 * 只在本文件内按浏览器语义补上（FileReader 读 UTF-8），结束后还原，不影响别的测试。
 */
const nativeBlobText = (Blob.prototype as any).text
beforeAll(() => {
  if (typeof nativeBlobText !== 'function') {
    ;(Blob.prototype as any).text = function (this: Blob) {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(reader.error)
        reader.readAsText(this, 'utf-8')
      })
    }
  }
})
afterAll(() => {
  ;(Blob.prototype as any).text = nativeBlobText
})

const mockHttpPost = vi.fn()

vi.mock('@/utils/http', () => ({
  default: { post: (...args: any[]) => mockHttpPost(...args), get: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/utils/sse', () => ({ createSSE: vi.fn() }))

global.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
global.URL.revokeObjectURL = vi.fn()

import { useBulkTabImportExport } from '../useBulkTabImportExport'
import { ElMessage } from 'element-plus'

const REASON = '服务器未安装 AES 加密组件（pyzipper），无法生成带密码的压缩包，已中止导出。'

function blobError(status: number, body: string) {
  const err: any = new Error(`Request failed with status code ${status}`)
  err.response = { status, data: new Blob([body], { type: 'application/json' }) }
  return err
}

function okResponse() {
  return {
    data: new Blob(['PK'], { type: 'application/zip' }),
    headers: { 'content-disposition': "attachment; filename*=UTF-8''x.zip" },
  }
}

describe('useBulkTabImportExport — 密码透传', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(document.body, 'appendChild').mockImplementation(((n: any) => n) as any)
    vi.spyOn(document.body, 'removeChild').mockImplementation(((n: any) => n) as any)
    // jsdom 不实现导航：下载用的 <a>.click() 会打印「Not implemented: navigation」
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('模板导出把密码放进请求体', async () => {
    mockHttpPost.mockResolvedValueOnce(okResponse())
    const { exportTemplates } = useBulkTabImportExport(ref('proj-1'))
    await exportTemplates(['D'], 'pw-123')

    expect(mockHttpPost).toHaveBeenCalledTimes(1)
    const [url, body, config] = mockHttpPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/bulk-tab/export-templates')
    expect(body).toEqual({ cycles: ['D'], password: 'pw-123' })
    expect(config.responseType).toBe('blob')
  })

  it('模板导出不设密码时明确发送 null（不是漏字段）', async () => {
    mockHttpPost.mockResolvedValueOnce(okResponse())
    const { exportTemplates } = useBulkTabImportExport(ref('proj-1'))
    await exportTemplates(['D'])

    expect(mockHttpPost.mock.calls[0][1]).toEqual({ cycles: ['D'], password: null })
  })

  it('数据导出同样带密码（既有行为不回退）', async () => {
    mockHttpPost.mockResolvedValueOnce(okResponse())
    const { exportData } = useBulkTabImportExport(ref('proj-1'))
    await exportData(['D'], true, false, 'pw-456')

    expect(mockHttpPost.mock.calls[0][1]).toMatchObject({ password: 'pw-456', only_with_data: true })
  })
})

describe('useBulkTabImportExport — blob 错误体里的中文原因', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([
    ['exportTemplates', (api: any) => api.exportTemplates(['D'], 'pw')],
    ['exportData', (api: any) => api.exportData(['D'], false, false, 'pw')],
  ])('%s 失败时展示后端 message，而不是 axios 英文', async (_name, run) => {
    mockHttpPost.mockRejectedValueOnce(blobError(503, JSON.stringify({ code: 503, message: REASON })))
    const api = useBulkTabImportExport(ref('proj-1'))

    await expect(run(api)).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith(REASON)
    expect(api.error.value).toBe(REASON)
  })

  it('优先取 detail（FastAPI 原生形态）', async () => {
    mockHttpPost.mockRejectedValueOnce(blobError(409, JSON.stringify({ detail: '导出进行中' })))
    const api = useBulkTabImportExport(ref('proj-1'))

    await expect(api.exportTemplates(['D'])).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('导出进行中')
  })

  it('错误体不是 JSON 时退回中文兜底文案（不把原始字节 / 英文甩给用户）', async () => {
    mockHttpPost.mockRejectedValueOnce(blobError(502, '<html>Bad Gateway</html>'))
    const api = useBulkTabImportExport(ref('proj-1'))

    await expect(api.exportData(['D'])).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('导出数据失败')
  })

  it('非 blob 错误仍走原 detail / message 逻辑', async () => {
    const err: any = new Error('Network Error')
    mockHttpPost.mockRejectedValueOnce(err)
    const api = useBulkTabImportExport(ref('proj-1'))

    await expect(api.exportTemplates(['D'])).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('Network Error')
  })
})

/**
 * 错误提示单一出口（spec `environment-hygiene…` Requirement 8.6）
 *
 * 两个导出请求带 `_silent: true`，原因有两条：
 *  ① 全局拦截器对 4xx 会用同一句再弹一次 —— 与 composable 的 ElMessage.error 重复；
 *  ② 拦截器对 5xx 会自动重跑两遍，而导出超时是 5 分钟 ⇒ 加密不可用 / 零 Tab / 密码违规
 *    这类确定性错误重跑毫无意义，只让用户多等十分钟。
 * 代价是拦截器也不再为它们弹超时 / 断网提示，故由 composable 自己给中文原因。
 */
describe('useBulkTabImportExport — 导出错误单一出口', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(document.body, 'appendChild').mockImplementation(((n: any) => n) as any)
    vi.spyOn(document.body, 'removeChild').mockImplementation(((n: any) => n) as any)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('两个导出请求都带 _silent', async () => {
    mockHttpPost.mockResolvedValue(okResponse())
    const api = useBulkTabImportExport(ref('proj-1'))

    await api.exportTemplates(['D'])
    await api.exportData(['D'], true, false)

    expect(mockHttpPost).toHaveBeenCalledTimes(2)
    for (const call of mockHttpPost.mock.calls) {
      const config = call[2]
      expect(config?._silent, `请求 ${call[0]} 未带 _silent`).toBe(true)
    }
  })

  it('导入 / 回滚不加 _silent（只有两个导出改了出口）', async () => {
    // 反向对照：`_silent` 是针对「blob 下载 + 5 分钟超时」这两个导出的，
    // 全量加会让其它请求的错误彻底无提示
    mockHttpPost.mockResolvedValue({ data: { data: { ok: true } } })
    const api = useBulkTabImportExport(ref('proj-1'))
    await api.rollback('task-1').catch(() => {})
    for (const call of mockHttpPost.mock.calls) {
      expect(call[2]?._silent).not.toBe(true)
    }
  })

  it.each([
    ['exportTemplates', (api: any) => api.exportTemplates(['D'])],
    ['exportData', (api: any) => api.exportData(['D'], true, false)],
  ])('%s 超时给中文原因（拦截器已不再弹）', async (_name, run) => {
    const err: any = new Error('timeout of 300000ms exceeded')
    err.code = 'ECONNABORTED'
    mockHttpPost.mockRejectedValue(err)

    const api = useBulkTabImportExport(ref('proj-1'))
    await expect(run(api)).rejects.toBeTruthy()

    const msg = (ElMessage.error as any).mock.calls.at(-1)?.[0] as string
    expect(msg).toContain('导出超时')
    expect(msg).toContain('缩小导出范围')
    expect(msg).not.toContain('timeout of')  // 不把 axios 英文原文甩给用户
    expect(api.error.value).toBe(msg)
  })

  it('断网给中文原因', async () => {
    const onLineSpy = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    try {
      const err: any = new Error('Network Error')  // 无 response
      mockHttpPost.mockRejectedValue(err)

      const api = useBulkTabImportExport(ref('proj-1'))
      await expect(api.exportTemplates(['D'])).rejects.toBeTruthy()

      const msg = (ElMessage.error as any).mock.calls.at(-1)?.[0] as string
      expect(msg).toContain('网络已断开')
      expect(msg).not.toContain('Network Error')
    } finally {
      onLineSpy.mockRestore()
    }
  })

  it('422 零 Tab 的中文原因照原样展示（不被超时/断网分支吞掉）', async () => {
    const reason = '没有可导出的底稿，已取消导出：有 3 张表格找不到对应底稿（尚未生成，或同一编号存在多份无法确定用哪份），请先在「底稿列表」点「生成底稿」。'
    mockHttpPost.mockRejectedValue(blobError(422, JSON.stringify({ code: 422, message: reason })))

    const api = useBulkTabImportExport(ref('proj-1'))
    await expect(api.exportTemplates(['D'])).rejects.toBeTruthy()

    expect(ElMessage.error).toHaveBeenCalledWith(reason)
    // 只弹一次 —— 重复弹出正是加 _silent 要消除的那个问题
    expect((ElMessage.error as any).mock.calls.length).toBe(1)
  })
})
