/**
 * Chat Run 生命周期状态管理
 *
 * 追踪单个 Chat Run 的完整生命周期：idle → creating → running → terminal
 * 提供 typed event dispatch、Last-Event-ID 续传、重连逻辑和中文错误消息。
 *
 * 这是前端唯一的 run 状态模型（Req 1.8 / Property 39）。
 * 消费方通过 `useChatRunState()` 获取响应式状态与控制方法。
 *
 * Feature: dsh-agent-panel-integration / Task 8
 * Validates: Requirements 1.8, 4.1, 4.4, 4.8
 * Properties: 9, 39
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  subscribeRunEvents,
  DRAINING_EVENT_NAME,
  type SSEEvent,
} from '@/utils/sse'

// ---------------------------------------------------------------------------
// Types（对应后端 run_contract.py 的 TypeScript 投影）
// ---------------------------------------------------------------------------

/**
 * Chat 事件类型（与后端 ChatEventType 单一真源对应）。
 * 前端不自行新增枚举值 —— 未知类型按 unknown 处理。
 */
export type ChatEventType =
  | 'run_started'
  | 'context_ready'
  | 'citation'
  | 'delta'
  | 'tool_started'
  | 'tool_finished'
  | 'quota'
  | 'error'
  | 'cancelled'
  | 'done'

/** Chat 事件负载（解析后的 typed event） */
export interface ChatEvent {
  event_id: string
  run_id: string
  session_id: string
  request_id: string
  type: ChatEventType
  timestamp: string
  message_id?: string | null
  payload: Record<string, any>
}

/** 稳定 error code（与后端 ChatErrorCode 对应） */
export type ChatErrorCode =
  | 'access_denied'
  | 'host_context_mismatch'
  | 'context_build_failed'
  | 'semantic_unavailable'
  | 'ocr_unavailable'
  | 'engine_unavailable'
  | 'local_only_violation'
  | 'rate_limited'
  | 'tool_budget_exceeded'
  | 'attachment_invalid'
  | 'run_cancelled'
  | 'run_interrupted'
  | 'adopt_log_failed'

/** error code → 中文用户消息（NFR-5：全中文可执行下一步） */
export const ERROR_MESSAGE_ZH: Record<ChatErrorCode, string> = {
  access_denied: '当前账号无权访问该资源，请联系项目负责人调整权限范围。',
  host_context_mismatch: '页面上下文与服务端记录不一致，请刷新页面后重试。',
  context_build_failed: '无法加载当前文档上下文，请稍后重试。',
  semantic_unavailable: '语义检索服务当前不可用，本轮未使用语义匹配结果。',
  ocr_unavailable: 'OCR 服务当前不可用，请稍后重新识别附件。',
  engine_unavailable: 'AI 引擎当前不可用，请稍后重试或联系管理员。',
  local_only_violation: '检测到非本地模型路由，已阻止本次执行。',
  rate_limited: '请求过于频繁，请稍候再试；您的输入已保留。',
  tool_budget_exceeded: '本次执行的取数配额已用尽，请缩小问题范围后重试。',
  attachment_invalid: '附件不可用或不属于当前会话，请重新上传。',
  run_cancelled: '本次回答已取消。',
  run_interrupted: '服务重启导致本次回答中断，请重新提问。',
  adopt_log_failed: '采纳留痕写入失败，内容未进入确认流，请重试。',
}

/** 获取 error code 对应的中文消息（未知 code 返回通用文案） */
export function getErrorMessageZh(code: string | undefined | null): string {
  if (!code) return '发生未知错误，请稍后重试。'
  return ERROR_MESSAGE_ZH[code as ChatErrorCode] ?? `发生错误（${code}），请稍后重试。`
}

/** Run 生命周期阶段 */
export type RunPhase = 'idle' | 'creating' | 'running' | 'done' | 'error' | 'cancelled'

/** 终态集合 */
const TERMINAL_PHASES: ReadonlySet<RunPhase> = new Set(['done', 'error', 'cancelled'])

/** ChatEventType → RunPhase 的终态映射 */
const TERMINAL_EVENT_TO_PHASE: Partial<Record<ChatEventType, RunPhase>> = {
  done: 'done',
  error: 'error',
  cancelled: 'cancelled',
}

/** 事件类型是否为终态 */
export function isTerminalEvent(type: string): boolean {
  return type === 'done' || type === 'error' || type === 'cancelled'
}

// ---------------------------------------------------------------------------
// Run State Store
// ---------------------------------------------------------------------------

export const useChatRunStateStore = defineStore('chatRunState', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const phase = ref<RunPhase>('idle')
  const runId = ref<string | null>(null)
  const sessionId = ref<string | null>(null)
  const lastEventId = ref<string | undefined>(undefined)
  const errorCode = ref<ChatErrorCode | null>(null)
  const errorMessage = ref<string | null>(null)
  const streamingDelta = ref('')
  const currentMessageId = ref<string | null>(null)
  const contextManifest = ref<any[] | null>(null)
  const eventsUrl = ref<string | null>(null)

  // quota 信息
  const quotaRemaining = ref<number | null>(null)
  const quotaReset = ref<number | null>(null)
  const retryAfter = ref<number | null>(null)

  // 内部控制
  let abortController: AbortController | null = null
  const eventHandlers: Map<ChatEventType | '*', Set<(event: ChatEvent) => void>> = new Map()

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const isTerminal = computed(() => TERMINAL_PHASES.has(phase.value))
  const isActive = computed(() => phase.value === 'creating' || phase.value === 'running')
  const displayError = computed(() => {
    if (phase.value !== 'error') return null
    return errorMessage.value || getErrorMessageZh(errorCode.value)
  })

  // ---------------------------------------------------------------------------
  // Event Dispatch
  // ---------------------------------------------------------------------------

  /** 注册事件处理器（type='*' 监听所有事件） */
  function on(type: ChatEventType | '*', handler: (event: ChatEvent) => void): () => void {
    if (!eventHandlers.has(type)) {
      eventHandlers.set(type, new Set())
    }
    eventHandlers.get(type)!.add(handler)
    return () => { eventHandlers.get(type)?.delete(handler) }
  }

  /** 分派一个 typed event */
  function dispatch(event: ChatEvent) {
    // 更新 lastEventId
    if (event.event_id) {
      lastEventId.value = event.event_id
    }

    // 🔴 终态 guard（Property 7 前端侧）：一旦进入终态，不再接受业务事件更新 phase/delta。
    // 后端 CAS 保证不会在终态后发出 done/delta，但防御性编程要求前端也不盲信。
    if (isTerminal.value) {
      // 终态后只允许 handler 通知（供日志/调试），不改变任何状态
      _notifyHandlers(event)
      return
    }

    // 按事件类型更新状态
    switch (event.type) {
      case 'run_started':
        phase.value = 'running'
        if (event.message_id) currentMessageId.value = event.message_id
        break
      case 'context_ready':
        contextManifest.value = event.payload?.manifest ?? null
        break
      case 'delta':
        streamingDelta.value += (event.payload?.text ?? event.payload?.content ?? '')
        if (event.message_id) currentMessageId.value = event.message_id
        break
      case 'citation':
        // citation 更新由消费方通过 on('citation', ...) 自行处理
        break
      case 'tool_started':
      case 'tool_finished':
        // 工具事件由消费方通过 typed dispatch 处理
        break
      case 'quota':
        quotaRemaining.value = event.payload?.remaining ?? null
        quotaReset.value = event.payload?.reset ?? null
        retryAfter.value = event.payload?.retry_after ?? null
        break
      case 'error':
        phase.value = 'error'
        errorCode.value = (event.payload?.code ?? null) as ChatErrorCode | null
        errorMessage.value = event.payload?.message ?? getErrorMessageZh(event.payload?.code)
        break
      case 'cancelled':
        phase.value = 'cancelled'
        errorCode.value = 'run_cancelled'
        errorMessage.value = ERROR_MESSAGE_ZH.run_cancelled
        break
      case 'done':
        phase.value = 'done'
        break
    }

    // 通知具体类型的 handler
    _notifyHandlers(event)
  }

  /** 内部：分派事件到已注册 handler（终态后也可调用，用于日志/调试） */
  function _notifyHandlers(event: ChatEvent) {
    const handlers = eventHandlers.get(event.type)
    if (handlers) {
      for (const h of handlers) {
        try { h(event) } catch { /* ignore handler errors */ }
      }
    }
    // 通知 wildcard handler
    const wildcards = eventHandlers.get('*')
    if (wildcards) {
      for (const h of wildcards) {
        try { h(event) } catch { /* ignore */ }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Run Lifecycle
  // ---------------------------------------------------------------------------

  /** 开始一个 run（创建阶段） */
  function startRun(params: { runId: string; sessionId: string; eventsUrl: string; lastEventId?: string }) {
    reset()
    phase.value = 'creating'
    runId.value = params.runId
    sessionId.value = params.sessionId
    eventsUrl.value = params.eventsUrl
    lastEventId.value = params.lastEventId
  }

  /** 订阅 SSE 事件流（两阶段 API 的第二阶段） */
  async function subscribe(): Promise<void> {
    if (!eventsUrl.value) return

    abortController = new AbortController()

    try {
      const stream = subscribeRunEvents({
        eventsUrl: eventsUrl.value,
        lastEventId: lastEventId.value,
        signal: abortController.signal,
        maxReconnects: 3,
        reconnectInterval: 2000,
      })

      for await (const sseEvent of stream) {
        if (abortController?.signal.aborted) break

        // server_draining：不当成业务事件，只更新状态
        if (sseEvent.type === DRAINING_EVENT_NAME) {
          // drain 后 subscribeRunEvents 内部会尝试重连
          continue
        }

        // 解析为 ChatEvent
        try {
          const chatEvent = JSON.parse(sseEvent.data) as ChatEvent
          dispatch(chatEvent)
        } catch {
          // 无法解析的事件跳过
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError' || abortController?.signal.aborted) return
      // 连接失败且非取消 → error
      if (!isTerminal.value) {
        phase.value = 'error'
        errorMessage.value = '与服务端的连接已中断，请重试。'
      }
    }
  }

  /** 取消当前 run */
  function cancel() {
    abortController?.abort()
    abortController = null
    if (!isTerminal.value) {
      phase.value = 'cancelled'
      errorCode.value = 'run_cancelled'
      errorMessage.value = ERROR_MESSAGE_ZH.run_cancelled
    }
  }

  /** 重置全部状态（新一轮对话前调用） */
  function reset() {
    abortController?.abort()
    abortController = null
    phase.value = 'idle'
    runId.value = null
    sessionId.value = null
    lastEventId.value = undefined
    errorCode.value = null
    errorMessage.value = null
    streamingDelta.value = ''
    currentMessageId.value = null
    contextManifest.value = null
    eventsUrl.value = null
    quotaRemaining.value = null
    quotaReset.value = null
    retryAfter.value = null
    eventHandlers.clear()
  }

  /** 设置 quota 信息（由限流 429 响应触发 — Req 13.6 前端中文倒计时） */
  function setQuota(params: { remaining: number; reset: string | null; retryAfter: number }) {
    quotaRemaining.value = params.remaining
    quotaReset.value = params.reset ? new Date(params.reset).getTime() : null
    retryAfter.value = params.retryAfter
    phase.value = 'error'
    errorCode.value = 'rate_limited'
    errorMessage.value = ERROR_MESSAGE_ZH.rate_limited
  }

  return {
    // state
    phase,
    runId,
    sessionId,
    lastEventId,
    errorCode,
    errorMessage,
    streamingDelta,
    currentMessageId,
    contextManifest,
    eventsUrl,
    quotaRemaining,
    quotaReset,
    retryAfter,
    // computed
    isTerminal,
    isActive,
    displayError,
    // methods
    on,
    dispatch,
    startRun,
    subscribe,
    cancel,
    reset,
    setQuota,
    // exposed for testing
    getErrorMessageZh,
  }
})
