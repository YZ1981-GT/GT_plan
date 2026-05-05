/**
 * SSE 统一封装 — 自动重连、错误处理、生命周期管理
 *
 * 实现方式：fetch + ReadableStream（替代 EventSource），
 * 支持在 Authorization header 传 token，避免 token 暴露在 URL query string。
 *
 * 用法：
 *   const sse = createSSE('/api/events/stream?project_id=xxx')
 *   sse.onMessage((data) => { ... })
 *   sse.onError((err) => { ... })
 *   // 组件卸载时
 *   sse.close()
 */

import { useAuthStore } from '@/stores/auth'

export interface SSEOptions {
  /** 最大重连次数，默认 5 */
  maxRetries?: number
  /** 重连间隔（毫秒），默认 3000，每次翻倍 */
  retryInterval?: number
}

export interface SSEConnection {
  onMessage: (handler: (data: any, event?: string) => void) => void
  onError: (handler: (error: Event | Error) => void) => void
  onOpen: (handler: () => void) => void
  close: () => void
  readonly isConnected: boolean
}

export function createSSE(url: string, options: SSEOptions = {}): SSEConnection {
  const { maxRetries = 5, retryInterval = 3000 } = options
  let retryCount = 0
  let closed = false
  let connected = false
  let abortController: AbortController | null = null
  let messageHandler: ((data: any, event?: string) => void) | null = null
  let errorHandler: ((error: Event | Error) => void) | null = null
  let openHandler: (() => void) | null = null

  async function connect() {
    if (closed) return

    abortController = new AbortController()
    const authStore = useAuthStore()

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
          // token 通过 Authorization header 传输，不放 URL query string
          ...(authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {}),
        },
        signal: abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`)
      }

      connected = true
      retryCount = 0
      openHandler?.()

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (!closed) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const rawData = line.slice(5).trim()
            try {
              const parsed = JSON.parse(rawData)
              messageHandler?.(parsed, currentEvent || undefined)
            } catch {
              messageHandler?.(rawData, currentEvent || undefined)
            }
            currentEvent = ''
          } else if (line === '') {
            // 空行：事件结束，重置 event 字段
            currentEvent = ''
          }
        }
      }
    } catch (err: any) {
      connected = false
      if (closed || err?.name === 'AbortError') return

      errorHandler?.(err instanceof Error ? err : new Error(String(err)))

      if (retryCount < maxRetries) {
        retryCount++
        const delay = retryInterval * Math.pow(2, retryCount - 1)
        setTimeout(connect, delay)
      }
    }
  }

  connect()

  return {
    onMessage(handler) { messageHandler = handler },
    onError(handler) { errorHandler = handler },
    onOpen(handler) { openHandler = handler },
    close() {
      closed = true
      connected = false
      abortController?.abort()
      abortController = null
    },
    get isConnected() {
      return connected
    },
  }
}

/**
 * SSE 流式读取（用于 LLM 流式响应）
 * 基于 fetch + ReadableStream，支持 POST 请求
 */
export async function* fetchSSE(
  url: string,
  body?: any,
  method: string = 'POST',
): AsyncGenerator<{ event?: string; data: string }> {
  const authStore = useAuthStore()
  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = ''
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        yield { event: currentEvent || undefined, data: line.slice(5).trim() }
        currentEvent = ''
      }
    }
  }
}
