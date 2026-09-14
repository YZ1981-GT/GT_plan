/**
 * usePlatformAiChat — 唯一 run/session/message/cancel/reconnect 状态
 *
 * 两阶段 API 默认路径：POST /runs → startRun → subscribe(events_url) → stream → finalize
 * 旧单 POST 路径由 `USE_LEGACY_STREAMING` feature flag 切换（默认 false）。
 *
 * Feature: dsh-agent-panel-integration / Task 9
 * Validates: Requirements 1.1, 1.4, 1.8, 1.9, 3.5
 * Properties: 5, 39
 */
import { ref, computed, type Ref, onBeforeUnmount } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChatRunStateStore, type ChatEvent, type RunPhase } from '@/stores/chatRunState'
import {
  hostPathSegments,
  hostQueryString,
  type AiHostRequest,
  type AiHostRef,
} from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Feature Flag — 旧路径保留开关（默认 false = 走新两阶段 API）
// ---------------------------------------------------------------------------

/**
 * 环境变量切换遗留路径。
 * `VITE_USE_LEGACY_STREAMING=true` 时回退到旧 POST /doc/{type}/{id} 单请求流。
 */
export const USE_LEGACY_STREAMING =
  (import.meta.env.VITE_USE_LEGACY_STREAMING ?? 'false') === 'true'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Citation {
  source_type: string
  source_id: string
  source_name: string
  paragraph_index?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
  runId?: string
  status?: 'completed' | 'streaming' | 'failed' | 'cancelled'
}

export interface UsePlatformAiChatOptions {
  /** 宿主上下文请求（由 useAiHostContext 的宿主 adapter 构造） */
  host: AiHostRequest | Ref<AiHostRequest>
}

/**
 * 本轮 run 的附加输入（Req 4.2：客户端只提交稳定 ID 与用户输入）。
 *
 * 🔴 这四项此前**全部在面板里被收集、但从未进入请求体** —— `sendMessageNewApi` 的
 * body 只有 `{host, query, idempotency_key}`。后端 `ChatRunRequest` 早就声明了
 * `mentions` / `attachment_ids` / `review_mode` / `sheet_name`，也就是说：
 * 服务端能收、前端能选，中间那一段没接上，选了等于没选。
 */
export interface ChatRunExtras {
  /** 用户显式引用的资源（只传 type + 稳定 ID；label/正文由服务端重新授权后加载） */
  mentions?: Array<{ type: string; id: string }>
  /** 会话附件 ID（正文与 OCR 由服务端按 owner/session 授权后读取） */
  attachmentIds?: string[]
  /** 是否启用底稿复核模式 */
  reviewMode?: boolean
  /** 复核模式的目标 sheet */
  sheetName?: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function unrefVal<T>(val: T | Ref<T>): T {
  return (val && typeof val === 'object' && 'value' in val)
    ? (val as Ref<T>).value
    : (val as T)
}

function newIdempotencyKey(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const SERVER_MESSAGE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isServerMessageId(id: string): boolean {
  return SERVER_MESSAGE_ID_RE.test(id)
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePlatformAiChat(options: UsePlatformAiChatOptions) {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const draft = ref('')
  const runStore = useChatRunStateStore()

  /** 宿主请求（响应式解引用） */
  const hostRequest = computed<AiHostRequest>(() => unrefVal(options.host))
  const hostAvailable = computed(() => hostRequest.value.available && !!hostRequest.value.host)
  const hostUnavailableReason = computed(() => hostRequest.value.unavailableReason)

  // ---------------------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------------------

  function getToken(): string {
    try {
      const authStore = useAuthStore()
      return authStore.token || ''
    } catch {
      return ''
    }
  }

  // ---------------------------------------------------------------------------
  // History
  // ---------------------------------------------------------------------------

  async function fetchHistory(): Promise<void> {
    const host = hostRequest.value.host
    if (!hostAvailable.value || !host) return
    const { docType, docId } = hostPathSegments(host)

    try {
      const res = await fetch(
        `/api/ai-chat/doc/${docType}/${docId}/history${hostQueryString(host)}`,
        { headers: { Authorization: `Bearer ${getToken()}` } },
      )
      if (res.ok) {
        const body = await res.json()
        const payload = body?.data ?? body
        const list = payload?.messages
        if (list && list.length > 0) {
          messages.value = list.map((m: any, idx: number) => ({
            id: m.message_id || m.id || `hist_${idx}`,
            role: m.role,
            text: m.content || m.text,
            citations: m.citations || [],
            status: 'completed' as const,
          }))
        }
      }
    } catch {
      // 离线时使用已有内存消息
    }
  }

  async function clearHistory(): Promise<void> {
    const host = hostRequest.value.host
    messages.value = []
    if (hostAvailable.value && host) {
      const { docType, docId } = hostPathSegments(host)
      try {
        await fetch(
          `/api/ai-chat/doc/${docType}/${docId}/history${hostQueryString(host)}`,
          { method: 'DELETE', headers: { Authorization: `Bearer ${getToken()}` } },
        )
      } catch { /* silent */ }
    }
  }

  // ---------------------------------------------------------------------------
  // 两阶段 API：POST /runs → SSE subscribe（默认路径）
  // ---------------------------------------------------------------------------

  /**
   * 把 `ChatRunExtras` 投影成后端 `ChatRunRequest` 的字段名。
   *
   * 只输出**非空**字段：后端 `model_config = ConfigDict(extra="forbid")` 不会因为多传
   * 空数组而拒绝，但空数组会让服务端日志/审计里出现"本轮有 0 个引用"的噪音，
   * 而"没提交这个字段"与"提交了空列表"在 manifest 里是两种语义。
   *
   * mention 只投 `{type, id}` —— 客户端**不得**提交 label（Req 5.5 / `MentionRef`
   * 是 `extra="forbid"`，多一个 label 键整个请求会被拒）。
   */
  function buildExtrasPayload(extras: ChatRunExtras): Record<string, unknown> {
    const payload: Record<string, unknown> = {}
    const mentions = (extras.mentions ?? []).filter((m) => m && m.type && m.id)
    if (mentions.length > 0) {
      payload.mentions = mentions.map((m) => ({ type: m.type, id: m.id }))
    }
    const attachmentIds = (extras.attachmentIds ?? []).filter(Boolean)
    if (attachmentIds.length > 0) {
      payload.attachment_ids = attachmentIds
    }
    if (extras.reviewMode) {
      payload.review_mode = true
      if (extras.sheetName) payload.sheet_name = extras.sheetName
    }
    return payload
  }

  async function sendMessageNewApi(query: string, extras: ChatRunExtras): Promise<void> {
    const host = hostRequest.value.host!
    const idempotencyKey = newIdempotencyKey()

    // Phase 1: POST /runs
    const res = await fetch('/api/ai-chat/runs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({
        host: {
          type: host.type,
          id: host.id,
          project_id_assertion: host.projectId,
          year_assertion: host.year,
        },
        query,
        idempotency_key: idempotencyKey,
        ...buildExtrasPayload(extras),
      }),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const code = body?.detail?.code || body?.data?.error_code || body?.code || 'unknown'
      // 🔴 Req 13.6：429 限流时解析 remaining/reset/retry_after 并更新 store
      if (res.status === 429 && body?.data) {
        runStore.setQuota({
          remaining: body.data.remaining ?? 0,
          reset: body.data.reset ?? null,
          retryAfter: body.data.retry_after ?? 5,
        })
      }
      const err = new Error(code) as any
      err.status = res.status
      throw err
    }

    const runData = await res.json()
    const data = runData?.data ?? runData
    const { run_id, session_id, events_url } = data

    // Phase 2: start run state + subscribe to SSE
    runStore.startRun({ runId: run_id, sessionId: session_id, eventsUrl: events_url })

    // Listen for events to build assistant message
    let assistantText = ''
    let assistantCitations: Citation[] = []
    let assistantMessageId: string | null = null

    const unsubDelta = runStore.on('delta', (event: ChatEvent) => {
      assistantText += (event.payload?.text ?? event.payload?.content ?? '')
      if (event.message_id) assistantMessageId = event.message_id
    })

    const unsubCitation = runStore.on('citation', (event: ChatEvent) => {
      if (event.payload?.sources) {
        assistantCitations = event.payload.sources
      }
    })

    const unsubDone = runStore.on('done', () => {
      finalizeMessage('completed')
    })

    const unsubError = runStore.on('error', () => {
      finalizeMessage('failed')
    })

    const unsubCancelled = runStore.on('cancelled', () => {
      finalizeMessage('cancelled')
    })

    function finalizeMessage(status: 'completed' | 'failed' | 'cancelled') {
      unsubDelta()
      unsubCitation()
      unsubDone()
      unsubError()
      unsubCancelled()

      if (status === 'completed' && assistantText) {
        messages.value.push({
          id: assistantMessageId || `ai_${Date.now()}`,
          role: 'assistant',
          text: assistantText,
          citations: assistantCitations.length > 0 ? assistantCitations : undefined,
          runId: run_id,
          status: 'completed',
        })
      } else if (status === 'failed') {
        messages.value.push({
          id: `err_${Date.now()}`,
          role: 'assistant',
          text: runStore.displayError || 'AI 服务暂不可用，请稍后重试。',
          status: 'failed',
        })
      } else if (status === 'cancelled') {
        if (assistantText) {
          messages.value.push({
            id: assistantMessageId || `ai_${Date.now()}`,
            role: 'assistant',
            text: assistantText + '\n\n⏹️ 已取消',
            citations: assistantCitations.length > 0 ? assistantCitations : undefined,
            runId: run_id,
            status: 'cancelled',
          })
        }
      }
    }

    // Start subscribing (non-blocking — runs in background)
    await runStore.subscribe()
  }

  // ---------------------------------------------------------------------------
  // 旧路径：单 POST streaming（USE_LEGACY_STREAMING = true 时使用）
  // ---------------------------------------------------------------------------

  async function sendMessageLegacy(query: string): Promise<void> {
    const host = hostRequest.value.host!
    const { docType, docId } = hostPathSegments(host)

    const res = await fetch(`/api/ai-chat/doc/${docType}/${docId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({
        query,
        year: host.year,
        project_id: host.projectId,
      }),
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No stream')
    const decoder = new TextDecoder()
    let fullText = ''
    let citations: Citation[] = []

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          const event = JSON.parse(raw)
          if (event.type === 'citations') citations = event.data || []
          else if (event.type === 'content') fullText += event.data
        } catch {
          fullText += raw
        }
      }
    }

    messages.value.push({
      id: `ai_${Date.now()}`,
      role: 'assistant',
      text: fullText || '（无回复）',
      citations: citations.length > 0 ? citations : undefined,
      status: 'completed',
    })
  }

  // ---------------------------------------------------------------------------
  // 公共 sendMessage 入口
  // ---------------------------------------------------------------------------

  async function sendMessage(query?: string, extras: ChatRunExtras = {}): Promise<void> {
    const text = (query ?? draft.value).trim()
    if (!text || loading.value) return

    const host = hostRequest.value.host
    if (!hostAvailable.value || !host) {
      messages.value.push({
        id: `err_${Date.now()}`,
        role: 'assistant',
        text: hostUnavailableReason.value ?? '当前页面无法解析文档上下文，AI 对话不可用。',
        status: 'failed',
      })
      return
    }

    // 添加用户消息
    messages.value.push({
      id: `user_${Date.now()}`,
      role: 'user',
      text,
    })
    draft.value = ''
    loading.value = true
    runStore.reset()

    try {
      if (USE_LEGACY_STREAMING) {
        await sendMessageLegacy(text)
      } else {
        await sendMessageNewApi(text, extras)
      }
    } catch (e: any) {
      const errorCode = e?.message ?? ''
      // 🔴 Req 13.6：限流触发时恢复 draft 并保留用户消息（不弹通用错误）
      if (errorCode === 'rate_limited' || e?.status === 429) {
        // 恢复草稿 — 用户无需重新输入
        draft.value = text
        // 移除刚添加的用户消息（避免重复）
        const lastUserIdx = messages.value.findLastIndex(m => m.role === 'user' && m.text === text)
        if (lastUserIdx >= 0) messages.value.splice(lastUserIdx, 1)
        // quota 信息已由 runStore.retryAfter / quotaRemaining 持有
        // 前端 ChatQuotaCountdown 组件将渲染中文倒计时
      } else if (!messages.value.find((m) => m.status === 'failed' && m.id.startsWith('err_'))) {
        messages.value.push({
          id: `err_${Date.now()}`,
          role: 'assistant',
          text: 'AI 服务暂不可用，请稍后重试。',
          status: 'failed',
        })
      }
    } finally {
      loading.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Cancel
  // ---------------------------------------------------------------------------

  async function cancelRun(): Promise<void> {
    // Abort SSE subscription
    runStore.cancel()
    // Call cancel endpoint
    if (runStore.runId) {
      try {
        await fetch(`/api/ai-chat/runs/${runStore.runId}/cancel`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${getToken()}` },
        })
      } catch { /* best effort */ }
    }
    loading.value = false
  }

  // ---------------------------------------------------------------------------
  // Adopt
  // ---------------------------------------------------------------------------

  async function adoptContent(
    messageId: string,
  ): Promise<{ success: boolean; code?: string; message?: string }> {
    if (!isServerMessageId(messageId)) {
      return {
        success: false,
        code: 'message_id_not_server_issued',
        message: '该回复尚未取得服务端消息编号，请刷新会话后再采纳',
      }
    }
    const host = hostRequest.value.host
    if (!hostAvailable.value || !host) {
      return {
        success: false,
        code: 'host_unavailable',
        message: hostUnavailableReason.value ?? '当前页面无法解析文档上下文',
      }
    }
    try {
      const res = await fetch('/api/ai-chat/adopt', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          message_id: messageId,
          host: { type: host.type, id: host.id, project_id: host.projectId, year: host.year },
          idempotency_key: newIdempotencyKey(),
        }),
      })
      if (res.ok) return { success: true }
      let code: string | undefined
      let message: string | undefined
      try {
        const body = await res.json()
        const detail = body?.detail ?? body?.data?.detail ?? body
        code = detail?.code
        message = detail?.message ?? (typeof detail === 'string' ? detail : undefined)
      } catch { /* non-JSON */ }
      return { success: false, code, message }
    } catch {
      return { success: false, code: 'network_error', message: '网络异常，采纳未生效' }
    }
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  onBeforeUnmount(() => {
    runStore.reset()
  })

  return {
    // State
    messages,
    loading,
    draft,
    hostRequest,
    hostAvailable,
    hostUnavailableReason,
    // Run state (delegated to store)
    phase: computed<RunPhase>(() => runStore.phase),
    streamingDelta: computed(() => runStore.streamingDelta),
    displayError: computed(() => runStore.displayError),
    isActive: computed(() => runStore.isActive),
    // Methods
    sendMessage,
    cancelRun,
    fetchHistory,
    clearHistory,
    adoptContent,
  }
}
