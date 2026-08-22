/**
 * SSE 统一 transport — canonical parser + 连接管理 + run 订阅
 *
 * 本模块是平台唯一 SSE 解析器（Req 1.8 / Property 9 / Property 39）。
 * 核心 `parseSSE` 严格实现 W3C Server-Sent Events 解析规范：
 *   - 跨 chunk buffer：任意网络字节分片下结果与未分片一致
 *   - CRLF / LF / CR 三种行尾均正确处理
 *   - 多行 data（多个 `data:` 行合成一个 data payload，换行拼接）
 *   - `id:` / `event:` / `retry:` 字段完整追踪
 *   - 心跳（注释帧 `: comment`）不 dispatch、不推进 lastEventId
 *   - `server_draining` 事件识别与特殊处理
 *   - AbortSignal 传播
 *   - Last-Event-ID 断点续传
 *
 * Feature: dsh-agent-panel-integration / Task 8
 * Validates: Requirements 1.8, 4.1, 4.4, 4.8
 * Properties: 9, 39
 */

import { useAuthStore } from '@/stores/auth'

// ---------------------------------------------------------------------------
// Core Types
// ---------------------------------------------------------------------------

/** 一个完整的 SSE 事件（分派给消费方）。 */
export interface SSEEvent {
  /** 事件类型（`event:` 字段，缺省为空串 = "message"） */
  type: string
  /** data 负载（多行合并后的字符串） */
  data: string
  /** 事件 ID（`id:` 字段，心跳/drain 帧无此字段） */
  id?: string
  /** retry 建议（毫秒） */
  retry?: number
}

/** 内部解析状态，允许跨 chunk 正确断句。 */
interface ParseState {
  /** 未解析完的行片段（跨 chunk 缓冲） */
  buffer: string
  /** 当前帧积累的 data 行（SSE 规范：多行 data 用 LF 拼接） */
  dataLines: string[]
  /** 当前帧的 event 字段 */
  eventType: string
  /** 当前帧的 id 字段 */
  eventId: string | undefined
  /** 当前帧的 retry 字段 */
  retry: number | undefined
  /** 最近一次收到的有效 id（不含空 id 清除的情况） */
  lastEventId: string | undefined
}

// ---------------------------------------------------------------------------
// Canonical SSE Parser（纯函数，无副作用，便于 Property Testing）
// ---------------------------------------------------------------------------

/** 创建空的解析状态。 */
export function createParseState(lastEventId?: string): ParseState {
  return {
    buffer: '',
    dataLines: [],
    eventType: '',
    eventId: undefined,
    retry: undefined,
    lastEventId,
  }
}

/**
 * 往解析状态中灌入一段原始文本（可以是任意字节分片），
 * 返回本次完成的所有事件（可能为 0 个或多个）。
 *
 * 这是确定性纯函数 —— 给定相同的 (state, chunk) 序列，
 * 输出事件序列与未分片基线完全一致（Property 9 的形式化）。
 *
 * 实现策略：逐字符扫描，识别行尾（CRLF/CR/LF），每找到一行就处理它。
 * 未看到行尾的内容留在 buffer 等下一个 chunk。这保证了跨 chunk 的正确性。
 */
export function feedChunk(state: ParseState, chunk: string): SSEEvent[] {
  const events: SSEEvent[] = []
  state.buffer += chunk

  // 逐行提取：从 buffer 中找到所有完整行并处理，
  // 保留最后不完整的行在 buffer 中。
  let i = 0
  let lineStart = 0

  while (i < state.buffer.length) {
    const ch = state.buffer[i]
    if (ch === '\r' || ch === '\n') {
      // 找到行尾
      const line = state.buffer.slice(lineStart, i)
      // 处理 CRLF：如果是 \r 后面跟 \n，消费两者
      if (ch === '\r' && i + 1 < state.buffer.length && state.buffer[i + 1] === '\n') {
        i += 2
      } else if (ch === '\r' && i + 1 === state.buffer.length) {
        // \r 在 buffer 末尾 —— 可能是 CRLF 的前半。
        // 暂停，等下一个 chunk 确认。
        break
      } else {
        i += 1
      }
      lineStart = i
      processLine(state, events, line)
    } else {
      i++
    }
  }

  // 保留未处理完的部分
  state.buffer = state.buffer.slice(lineStart)
  return events
}

/** 处理一行完整的 SSE 文本（内部使用）。 */
function processLine(state: ParseState, events: SSEEvent[], line: string): void {
  if (line === '') {
    // 空行 = 事件边界（SSE 规范）
    dispatchEvent(state, events)
  } else if (line[0] === ':') {
    // 注释帧 —— 忽略（心跳等），不 dispatch
    return
  } else {
    // 解析字段
    const colonIdx = line.indexOf(':')
    let fieldName: string
    let fieldValue: string
    if (colonIdx < 0) {
      fieldName = line
      fieldValue = ''
    } else {
      fieldName = line.slice(0, colonIdx)
      const valueStart = colonIdx + 1 + (line[colonIdx + 1] === ' ' ? 1 : 0)
      fieldValue = line.slice(valueStart)
    }

    switch (fieldName) {
      case 'data':
        state.dataLines.push(fieldValue)
        break
      case 'event':
        state.eventType = fieldValue
        break
      case 'id':
        if (!fieldValue.includes('\0')) {
          state.eventId = fieldValue
        }
        break
      case 'retry':
        if (/^\d+$/.test(fieldValue)) {
          state.retry = parseInt(fieldValue, 10)
        }
        break
    }
  }
}

/** 冲刷 buffer 末尾（流结束时调用，处理末尾无空行的最后一帧）。 */
export function flushState(state: ParseState): SSEEvent[] {
  const events: SSEEvent[] = []
  if (state.buffer) {
    // 处理残留 buffer 中的行（可能是末尾的 \r 或不完整行）
    const lines = state.buffer.split(/\r\n|\r|\n/)
    state.buffer = ''
    for (const line of lines) {
      processLine(state, events, line)
    }
  }
  // 如果有未 dispatch 的数据（流没有以空行结尾），做最终 dispatch
  if (state.dataLines.length > 0) {
    dispatchEvent(state, events)
  }
  return events
}

function dispatchEvent(state: ParseState, events: SSEEvent[]) {
  if (state.dataLines.length === 0) {
    // SSE 规范：data buffer 为空时不 dispatch
    resetFrame(state)
    return
  }
  // 多行 data 用 LF 拼接
  const data = state.dataLines.join('\n')
  // 更新 lastEventId（如果此帧有 id 字段）
  if (state.eventId !== undefined) {
    state.lastEventId = state.eventId
  }
  events.push({
    type: state.eventType || '',
    data,
    id: state.eventId,
    retry: state.retry,
  })
  resetFrame(state)
}

function resetFrame(state: ParseState) {
  state.dataLines = []
  state.eventType = ''
  state.eventId = undefined
  state.retry = undefined
}

// ---------------------------------------------------------------------------
// Special Event Names（对应后端 run_events.py 的常量）
// ---------------------------------------------------------------------------

/** 服务端优雅关闭帧的 event 名（传输层信号，不是业务事件） */
export const DRAINING_EVENT_NAME = 'server_draining'

/** 心跳注释内容（后端发 `: heartbeat\n\n`；解析层不会 dispatch 注释帧） */
export const HEARTBEAT_COMMENT = 'heartbeat'

// ---------------------------------------------------------------------------
// High-Level SSE Connection (backward-compatible, enhanced)
// ---------------------------------------------------------------------------

export interface SSEOptions {
  /** 最大重连次数，默认 5 */
  maxRetries?: number
  /** 重连间隔（毫秒），默认 3000，每次翻倍 */
  retryInterval?: number
  /** 外部 AbortSignal（组件卸载时取消） */
  signal?: AbortSignal
  /** 初始 Last-Event-ID（断点续传） */
  lastEventId?: string
}

export interface SSEConnection {
  onMessage: (handler: (data: any, event?: string, id?: string) => void) => void
  onError: (handler: (error: Event | Error) => void) => void
  onOpen: (handler: () => void) => void
  /** 当收到 server_draining 帧时触发 */
  onDraining: (handler: (reason: string) => void) => void
  close: () => void
  readonly isConnected: boolean
  readonly lastEventId: string | undefined
}

export function createSSE(url: string, options: SSEOptions = {}): SSEConnection {
  const { maxRetries = 5, retryInterval = 3000, signal, lastEventId: initialLastEventId } = options
  let retryCount = 0
  let closed = false
  let connected = false
  let abortController: AbortController | null = null
  let messageHandler: ((data: any, event?: string, id?: string) => void) | null = null
  let errorHandler: ((error: Event | Error) => void) | null = null
  let openHandler: (() => void) | null = null
  let drainingHandler: ((reason: string) => void) | null = null
  let currentLastEventId: string | undefined = initialLastEventId

  // 外部 signal 监听
  if (signal) {
    signal.addEventListener('abort', () => { close() })
  }

  async function connect() {
    if (closed) return

    abortController = new AbortController()
    const authStore = useAuthStore()

    // 构建带 Last-Event-ID 的 URL（如有续传 ID）
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    }
    if (authStore.token) {
      headers['Authorization'] = `Bearer ${authStore.token}`
    }
    if (currentLastEventId) {
      headers['Last-Event-ID'] = currentLastEventId
    }

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers,
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
      const state = createParseState(currentLastEventId)

      while (!closed) {
        const { done, value } = await reader.read()
        if (done) break

        const text = decoder.decode(value, { stream: true })
        const events = feedChunk(state, text)

        for (const evt of events) {
          // 更新 lastEventId
          if (evt.id !== undefined) {
            currentLastEventId = evt.id
          }
          // 特殊处理 server_draining
          if (evt.type === DRAINING_EVENT_NAME) {
            let reason = '服务端正在优雅关闭，请稍后重连该会话'
            try {
              const parsed = JSON.parse(evt.data)
              reason = parsed.message || reason
            } catch { /* use default */ }
            drainingHandler?.(reason)
            continue
          }
          // 正常事件分派
          try {
            const parsed = JSON.parse(evt.data)
            messageHandler?.(parsed, evt.type || undefined, evt.id)
          } catch {
            messageHandler?.(evt.data, evt.type || undefined, evt.id)
          }
        }
      }

      // 流自然结束后 flush
      const remaining = flushState(state)
      for (const evt of remaining) {
        if (evt.id !== undefined) currentLastEventId = evt.id
        if (evt.type === DRAINING_EVENT_NAME) continue
        try {
          const parsed = JSON.parse(evt.data)
          messageHandler?.(parsed, evt.type || undefined, evt.id)
        } catch {
          messageHandler?.(evt.data, evt.type || undefined, evt.id)
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

  function close() {
    closed = true
    connected = false
    abortController?.abort()
    abortController = null
  }

  connect()

  return {
    onMessage(handler) { messageHandler = handler },
    onError(handler) { errorHandler = handler },
    onOpen(handler) { openHandler = handler },
    onDraining(handler) { drainingHandler = handler },
    close,
    get isConnected() { return connected },
    get lastEventId() { return currentLastEventId },
  }
}

// ---------------------------------------------------------------------------
// SSE 流式读取（POST 请求，用于 LLM 流式响应 — backward compat）
// ---------------------------------------------------------------------------

export async function* fetchSSE(
  url: string,
  body?: any,
  method: string = 'POST',
): AsyncGenerator<{ event?: string; data: string; id?: string }> {
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
  const state = createParseState()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value, { stream: true })
    const events = feedChunk(state, text)
    for (const evt of events) {
      yield { event: evt.type || undefined, data: evt.data, id: evt.id }
    }
  }

  // flush
  const remaining = flushState(state)
  for (const evt of remaining) {
    yield { event: evt.type || undefined, data: evt.data, id: evt.id }
  }
}

// ---------------------------------------------------------------------------
// Run Event Subscription（两阶段 API 的第二阶段 — Task 8 新增）
// ---------------------------------------------------------------------------

/** Chat Run SSE 订阅选项 */
export interface RunSSEOptions {
  /** Run 事件 URL（从 POST /runs 响应的 events_url） */
  eventsUrl: string
  /** 初始 Last-Event-ID（从 run_started 的 event_id 可获得） */
  lastEventId?: string
  /** 外部取消信号 */
  signal?: AbortSignal
  /** 最大重连次数（默认 3） */
  maxReconnects?: number
  /** 重连间隔基数（毫秒，默认 2000） */
  reconnectInterval?: number
}

/**
 * 订阅某个 Chat Run 的 SSE 事件流。
 * 支持 Last-Event-ID 断点续传、心跳过滤、drain 识别。
 *
 * yield 的每个 SSEEvent 已经过解析（type + data + id）。
 * drain 帧会作为特殊 type="server_draining" yield 出来，
 * 消费方应据此尝试重连。
 */
export async function* subscribeRunEvents(
  options: RunSSEOptions,
): AsyncGenerator<SSEEvent> {
  const { eventsUrl, signal, maxReconnects = 3, reconnectInterval = 2000 } = options
  let lastId = options.lastEventId
  let reconnectCount = 0

  while (true) {
    const authStore = useAuthStore()
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    }
    if (authStore.token) {
      headers['Authorization'] = `Bearer ${authStore.token}`
    }
    if (lastId) {
      headers['Last-Event-ID'] = lastId
    }

    let streamBroken = false

    try {
      const response = await fetch(eventsUrl, {
        method: 'GET',
        headers,
        signal,
      })

      if (!response.ok) {
        throw new Error(`SSE subscribe failed: ${response.status}`)
      }

      reconnectCount = 0 // 成功连接后重置

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      const state = createParseState(lastId)

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          streamBroken = true
          break
        }

        const text = decoder.decode(value, { stream: true })
        const events = feedChunk(state, text)

        for (const evt of events) {
          if (evt.id !== undefined) {
            lastId = evt.id
          }
          yield evt
          // 终态事件后不再继续
          if (isTerminalEventType(evt.type)) {
            return
          }
          // drain 帧 yield 后尝试重连
          if (evt.type === DRAINING_EVENT_NAME) {
            streamBroken = true
            break
          }
        }
        if (streamBroken) break
      }

      // flush 残留
      if (!streamBroken) {
        const remaining = flushState(state)
        for (const evt of remaining) {
          if (evt.id !== undefined) lastId = evt.id
          yield evt
          if (isTerminalEventType(evt.type)) return
        }
        streamBroken = true
      }
    } catch (err: any) {
      if (signal?.aborted || err?.name === 'AbortError') {
        return
      }
      streamBroken = true
    }

    // 重连逻辑
    if (!streamBroken) return
    reconnectCount++
    if (reconnectCount > maxReconnects) {
      return
    }
    // 等待后重连（指数退避）
    const delay = reconnectInterval * Math.pow(2, reconnectCount - 1)
    await new Promise((resolve) => setTimeout(resolve, delay))
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** 终态事件类型（与后端 TERMINAL_EVENT_TYPES 对应） */
const TERMINAL_TYPES = new Set(['done', 'error', 'cancelled'])

function isTerminalEventType(type: string): boolean {
  return TERMINAL_TYPES.has(type)
}
