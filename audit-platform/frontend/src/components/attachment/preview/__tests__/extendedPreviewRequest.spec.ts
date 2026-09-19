/**
 * fetchExtendedBytes — download protocol, byte limit and JSON trap
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PreviewResourceScope } from '../previewResourceScope'

vi.mock('@/utils/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), log: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))

import http from '@/utils/http'
import { logger } from '@/utils/logger'
import { fetchExtendedBytes } from '../extendedPreviewRequest'

function requestOptions(overrides: Record<string, unknown> = {}) {
  return {
    attachmentId: 'att-1',
    downloadUrl: '/api/attachments/att-1/download',
    family: 'archive' as const,
    signal: new AbortController().signal,
    generation: 1,
    isCurrent: () => true,
    scope: new PreviewResourceScope(),
    ...overrides,
  }
}

describe('fetchExtendedBytes', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset()
    vi.mocked(logger.error).mockReset()
  })

  it.each(['application/json', 'application/problem+json', 'vendor/vnd.gt+json'])('%s → wiring_error，且日志不含正文', async (contentType) => {
    vi.mocked(http.get).mockResolvedValue({
      data: new Blob([JSON.stringify({ previewable: false })], { type: contentType }),
      headers: { 'content-type': `${contentType}; charset=utf-8`, 'x-request-id': 'rid-1' },
      status: 200,
    })

    const result = await fetchExtendedBytes(requestOptions())

    expect(result.status).toBe('wiring_error')
    expect(logger.error).toHaveBeenCalledWith(
      'attachment_preview_json_blob_trap',
      expect.objectContaining({ requestId: 'rid-1' }),
    )
    expect(JSON.stringify(vi.mocked(logger.error).mock.calls[0])).not.toMatch(/previewable/)
  })

  it('仅 blob.type 为 +json 时也触发 JSON trap', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: new Blob(['{}'], { type: 'application/problem+json' }),
      headers: {},
      status: 200,
    })
    expect((await fetchExtendedBytes(requestOptions())).status).toBe('wiring_error')
  })

  it('blob.size 超限时在 arrayBuffer 前返回 limit_reached', async () => {
    const arrayBuffer = vi.fn(async () => new ArrayBuffer(9))
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', size: 9, arrayBuffer },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })

    const result = await fetchExtendedBytes(requestOptions({ maxBytes: 8 }))

    expect(result.status).toBe('limit_reached')
    expect(arrayBuffer).not.toHaveBeenCalled()
  })

  it('无可信 size 时仍在 arrayBuffer 后执行最终字节守卫', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', arrayBuffer: async () => new ArrayBuffer(9) },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })
    expect((await fetchExtendedBytes(requestOptions({ maxBytes: 8 }))).status).toBe('limit_reached')
  })

  it('边界大小可 ready，并保留同一 ArrayBuffer', async () => {
    const bytes = new ArrayBuffer(8)
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', size: 8, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })
    const result = await fetchExtendedBytes(requestOptions({ maxBytes: 8 }))
    expect(result).toMatchObject({ status: 'ready', bytes })
  })

  it('下载请求固定 _dedupe:false 并保留调用方 signal', async () => {
    const bytes = new ArrayBuffer(4)
    const controller = new AbortController()
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', size: 4, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })

    await expect(fetchExtendedBytes(requestOptions({ signal: controller.signal }))).resolves.toMatchObject({
      status: 'ready',
      bytes,
    })
    expect(http.get).toHaveBeenCalledWith(
      '/api/attachments/att-1/download',
      expect.objectContaining({
        _dedupe: false,
        responseType: 'blob',
        signal: controller.signal,
      }),
    )
  })

  it('preview URL 硬拒绝，不发起请求', async () => {
    const result = await fetchExtendedBytes(requestOptions({ downloadUrl: '/api/attachments/att-1/preview' }))
    expect(result.status).toBe('wiring_error')
    expect(http.get).not.toHaveBeenCalled()
  })

  it('403/404/500 互斥映射', async () => {
    for (const [status, expectedState] of [
      [403, 'forbidden'],
      [404, 'not_found'],
      [500, 'load_failed'],
    ] as const) {
      vi.mocked(http.get).mockRejectedValue({ response: { status }, code: 'ERR_BAD_RESPONSE' })
      expect((await fetchExtendedBytes(requestOptions({ family: 'email' }))).status).toBe(expectedState)
    }
  })

  it('cancel → cancelled；stale generation → stale', async () => {
    vi.mocked(http.get).mockRejectedValue({ code: 'ERR_CANCELED', name: 'CanceledError' })
    expect((await fetchExtendedBytes(requestOptions({ family: 'drawing' }))).status).toBe('cancelled')

    vi.mocked(http.get).mockResolvedValue({
      data: new Blob(['abc']),
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })
    expect((await fetchExtendedBytes(requestOptions({ isCurrent: () => false }))).status).toBe('stale')
  })
})
