/**
 * SSE 统一封装 — 自动重连、错误处理、生命周期管理
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
  /** 自定义请求头 */
  headers?: Record<string, string>
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
  let eventSource: EventSource | null = null
  let retryCount = 0
  let closed = false
  let messageHandler: ((data: any, event?: string) => void) | null = null
  let errorHandler: ((error: Event | Error) => void) | null = null
  let openHandler: (() => void) | null = null

  function connect() {
    if (closed) return

    // 附加 token 到 URL（EventSource 不支持自定义 header）
    const authStore = useAuthStore()
    const separator = url.includes('?') ? '&' : '?'
    const fullUrl = authStore.token
      ? `${url}${separator}token=${authStore.token}`
      : url

    eventSource = new EventSource(fullUrl)

    eventSource.onopen = () => {
      retryCount = 0
      openHandler?.()
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        messageHandler?.(data, event.type)
      } catch {
        messageHandler?.(event.data, event.type)
      }
    }

    eventSource.onerror = (event) => {
      eventSource?.close()
      errorHandler?.(event)

      if (!closed && retryCount < maxRetries) {
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
      eventSource?.close()
      eventSource = null
    },
    get isConnected() {
      return eventSource?.readyState === EventSource.OPEN
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
