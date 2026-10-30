import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

import { createSSE } from '@/utils/sse'

const encoder = new TextEncoder()

function closedStreamResponse(text: string): Response {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      if (text) controller.enqueue(encoder.encode(text))
      controller.close()
    },
  }), { status: 200, headers: { 'content-type': 'text/event-stream' } })
}

function openStreamResponse(signal: AbortSignal | undefined): Response {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      signal?.addEventListener('abort', () => {
        controller.error(new DOMException('Aborted', 'AbortError'))
      }, { once: true })
    },
  }), { status: 200, headers: { 'content-type': 'text/event-stream' } })
}

describe('createSSE 重连', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('收到 server_draining 且流结束后立即连接新 worker', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(closedStreamResponse(
        'event: server_draining\ndata: {"message":"服务端交接"}\n\n',
      ))
      .mockImplementationOnce(async (_url: string, init?: RequestInit) => (
        openStreamResponse(init?.signal ?? undefined)
      ))
    vi.stubGlobal('fetch', fetchMock)

    const onOpen = vi.fn()
    const onDraining = vi.fn()
    const onError = vi.fn()
    const conn = createSSE('/api/projects/p1/events/stream', {
      retryInterval: 60_000,
      reconnectOnCleanEnd: true,
    })
    conn.onOpen(onOpen)
    conn.onDraining(onDraining)
    conn.onError(onError)

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(onOpen).toHaveBeenCalledTimes(2)
    })
    expect(onDraining).toHaveBeenCalledWith('服务端交接')
    expect(onError).not.toHaveBeenCalled()
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer test-token',
    })
    conn.close()
  })

  it('没有 drain 帧的意外 EOF 按断线报错并重连', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(closedStreamResponse(''))
      .mockImplementationOnce(async (_url: string, init?: RequestInit) => (
        openStreamResponse(init?.signal ?? undefined)
      ))
    vi.stubGlobal('fetch', fetchMock)

    const onError = vi.fn()
    const conn = createSSE('/api/projects/p1/events/stream', {
      maxRetries: 1,
      retryInterval: 0,
      reconnectOnCleanEnd: true,
    })
    conn.onError(onError)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toMatchObject({ message: 'SSE stream ended unexpectedly' })
    conn.close()
  })
})


describe('createSSE 有限流终态', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('默认把正常 EOF 当终态，不重连也不报错', async () => {
    const fetchMock = vi.fn().mockResolvedValue(closedStreamResponse(
      'event: complete\ndata: {"type":"complete"}\n\n',
    ))
    vi.stubGlobal('fetch', fetchMock)

    const onMessage = vi.fn()
    const onError = vi.fn()
    const conn = createSSE('/api/projects/p1/bulk-tab/progress/t1', { retryInterval: 0 })
    conn.onMessage(onMessage)
    conn.onError(onError)

    await vi.waitFor(() => expect(onMessage).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
    expect(conn.isConnected).toBe(false)
    conn.close()
  })
})
