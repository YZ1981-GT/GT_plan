/**
 * useDocAiChat — 文档级 AI 对话 composable
 *
 * 功能：发起对话 / SSE streaming 接收 / 历史管理 / 离线缓存
 * 需求: 5.2（离线缓存）, 5.3（streaming 响应）
 *
 * Feature: dsh-agent-panel-integration / Task 2（Req 3.3, 3.4, 3.5）
 *   入参从"四个松散标量（docType/docId/projectId/year）"收敛为**一个** `AiHostRequest`
 *   —— 由 `useAiHostContext` 的六个宿主 adapter 构造。好处有三：
 *     ① 宿主不可用（未选定资源 / 无项目上下文）时 composable 直接拒绝发起请求，
 *        不会再发出 `doc_id=''` 或 `project_id=''` 这类必然失败的调用；
 *     ② 项目 ID 不可能出现在 doc ID 位置（旧 `ReportView` 的真实缺陷）；
 *     ③ `projectId` / `year` 只作服务端一致性断言，缺失时传 `null` 而不是猜。
 *
 * @example
 * const host = computed(() => buildWorkpaperHost({ wpId, projectId, auditYear }))
 * const { messages, sendMessage } = useDocAiChat({ host })
 */
import { ref, computed, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  hostPathSegments,
  hostQueryString,
  type AiHostRequest,
} from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Citation {
  source_type: string
  source_id: string
  source_name: string
  paragraph_index?: number
}

export interface DocChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
}

export interface UseDocAiChatOptions {
  /** 宿主上下文请求（由 useAiHostContext 的宿主 adapter 构造，唯一真源） */
  host: AiHostRequest | Ref<AiHostRequest>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function unrefVal<T>(val: T | Ref<T>): T {
  return (val && typeof val === 'object' && 'value' in val) ? (val as Ref<T>).value : val as T
}

const CACHE_KEY_PREFIX = 'doc_ai_chat_'

function buildCacheKey(docType: string, docId: string): string {
  return `${CACHE_KEY_PREFIX}${docType}_${docId}`
}

const SERVER_MESSAGE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * 是否是服务端签发的消息 ID（UUID 形态）。
 *
 * 本地占位 ID 形如 `ai_1712…` / `user_1712…` / `hist_3`：采纳只能引用服务端 ID
 * （Req 8.1），因此这类 ID 必须在发请求**之前**被识别出来。
 */
function isServerMessageId(id: string): boolean {
  return SERVER_MESSAGE_ID_RE.test(id)
}

/** 幂等键（服务端要求 UUID；`crypto.randomUUID` 不可用时回退到 v4 形态拼装）。 */
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

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useDocAiChat(options: UseDocAiChatOptions) {
  const messages = ref<DocChatMessage[]>([])
  const loading = ref(false)
  const streamingText = ref('')
  const isOnline = ref(navigator.onLine)

  // 监听网络状态
  function handleOnline() { isOnline.value = true }
  function handleOffline() { isOnline.value = false }

  if (typeof window !== 'undefined') {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
  }

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
  // 本地缓存（需求 5.2：断网可查历史）
  // ---------------------------------------------------------------------------

  /** 当前宿主请求（响应式解引用；宿主切换后所有派生值同步）。 */
  const hostRequest = computed<AiHostRequest>(() => unrefVal(options.host))
  /** 宿主是否可用于发起请求（不可用时不发任何调用，Req 3.4）。 */
  const hostAvailable = computed(() => hostRequest.value.available && !!hostRequest.value.host)
  /** 宿主不可用的中文原因（面板直接展示）。 */
  const hostUnavailableReason = computed(() => hostRequest.value.unavailableReason)

  const cacheKey = computed(() => {
    const host = hostRequest.value.host
    if (!host || !host.id) return `${CACHE_KEY_PREFIX}unresolved`
    return buildCacheKey(host.type, host.id)
  })

  function saveToLocalCache() {
    try {
      localStorage.setItem(cacheKey.value, JSON.stringify(messages.value))
    } catch {
      // localStorage 满或不可用时静默忽略
    }
  }

  function loadFromLocalCache() {
    try {
      const cached = localStorage.getItem(cacheKey.value)
      if (cached) {
        messages.value = JSON.parse(cached)
      }
    } catch {
      messages.value = []
    }
  }

  // ---------------------------------------------------------------------------
  // 拉取服务端对话历史
  // ---------------------------------------------------------------------------

  async function fetchHistory(): Promise<void> {
    const host = hostRequest.value.host
    if (!hostAvailable.value || !host) return
    const { docType, docId } = hostPathSegments(host)

    try {
      const res = await fetch(
        `/api/ai-chat/doc/${docType}/${docId}/history${hostQueryString(host)}`,
        {
          headers: { Authorization: `Bearer ${getToken()}` },
        },
      )
      if (res.ok) {
        const body = await res.json()
        // 后端 ResponseWrapperMiddleware 把 2xx 包装成 {code,message,data}
        // 此处用原生 fetch（非 apiProxy），需手动解信封；兼容未包装的情况
        const payload = (body && typeof body === 'object' && 'data' in body && body.data)
          ? body.data
          : body
        const list = payload?.messages
        if (list && list.length > 0) {
          // `message_id` 是服务端签发的真实 ID（Task 3 的 history 元数据），采纳/转存
          // 只能引用它（Req 8.1）。旧实现读不存在的 `m.id` ⇒ 恒回落 `hist_N` 占位 ID，
          // 于是任何历史消息都无法被采纳。
          messages.value = list.map((m: any, idx: number) => ({
            id: m.message_id || m.id || `hist_${idx}`,
            role: m.role,
            text: m.content || m.text,
            citations: m.citations || [],
          }))
          saveToLocalCache()
        }
      }
    } catch {
      // 离线时静默，使用本地缓存
    }
  }

  // ---------------------------------------------------------------------------
  // 清除历史
  // ---------------------------------------------------------------------------

  async function clearHistory(): Promise<void> {
    const host = hostRequest.value.host

    // 清除本地缓存
    messages.value = []
    try {
      localStorage.removeItem(cacheKey.value)
    } catch { /* ignore */ }

    // 尝试清除服务端历史（宿主不可用时不发请求）
    if (isOnline.value && hostAvailable.value && host) {
      const { docType, docId } = hostPathSegments(host)
      try {
        await fetch(
          `/api/ai-chat/doc/${docType}/${docId}/history${hostQueryString(host)}`,
          {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${getToken()}` },
          },
        )
      } catch {
        // 静默处理
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 发送消息（SSE streaming）— 需求 5.3
  // ---------------------------------------------------------------------------

  async function sendMessage(query: string, extraScopes?: string[]): Promise<void> {
    const text = query.trim()
    if (!text || loading.value) return

    // 宿主未解析（未选定资源 / 无项目上下文）→ 显示中文原因，不发注定失败的请求（Req 3.4）
    const host = hostRequest.value.host
    if (!hostAvailable.value || !host) {
      messages.value.push({
        id: `err_${Date.now()}`,
        role: 'assistant',
        text: hostUnavailableReason.value ?? '当前页面无法解析文档上下文，AI 对话不可用。',
      })
      return
    }

    // 离线时拒绝发送新消息
    if (!isOnline.value) {
      const offlineMsg: DocChatMessage = {
        id: `err_${Date.now()}`,
        role: 'assistant',
        text: '当前处于离线状态，无法发送新消息。请恢复网络后重试。',
      }
      messages.value.push(offlineMsg)
      return
    }

    // 添加用户消息
    const userMsg: DocChatMessage = {
      id: `user_${Date.now()}`,
      role: 'user',
      text,
    }
    messages.value.push(userMsg)

    loading.value = true
    streamingText.value = ''

    const { docType, docId } = hostPathSegments(host)

    let currentCitations: Citation[] = []
    let fullText = ''

    try {
      const res = await fetch(`/api/ai-chat/doc/${docType}/${docId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          query: text,
          // project_id / year 只是服务端一致性断言：宿主没有年度绑定时传 null，不猜。
          year: host.year,
          project_id: host.projectId,
          extra_scopes: extraScopes && extraScopes.length > 0 ? extraScopes : null,
        }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      // SSE 流式读取
      const reader = res.body?.getReader()
      if (!reader) throw new Error('无法获取响应流')

      const decoder = new TextDecoder()

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
            if (event.type === 'citations') {
              currentCitations = event.data || []
            } else if (event.type === 'content') {
              fullText += event.data
              streamingText.value = fullText
            } else if (event.type === 'error') {
              fullText += `\n⚠️ ${event.data}`
              streamingText.value = fullText
            }
            // type === 'done' → 结束
          } catch {
            // 非 JSON 行，直接拼接
            fullText += raw
            streamingText.value = fullText
          }
        }
      }

      // 流结束，添加 assistant 消息
      const assistantMsg: DocChatMessage = {
        id: `ai_${Date.now()}`,
        role: 'assistant',
        text: fullText || '（无回复）',
        citations: currentCitations,
      }
      messages.value.push(assistantMsg)
      saveToLocalCache()
    } catch (e: any) {
      const errorMsg: DocChatMessage = {
        id: `err_${Date.now()}`,
        role: 'assistant',
        text: 'AI 服务暂不可用，请稍后重试。',
      }
      messages.value.push(errorMsg)
      console.error('[useDocAiChat] sendMessage error:', e)
    } finally {
      loading.value = false
      streamingText.value = ''
    }
  }

  // ---------------------------------------------------------------------------
  // 采纳 AI 内容
  // ---------------------------------------------------------------------------

  /**
   * 采纳 AI 内容（Task 7：server-authoritative 契约）。
   *
   * 🔴 **不再提交正文**。旧实现把 `msg.text` 当权威内容发给 `/adopt`，服务端原样写进
   * `ai_content_log` —— 等于让浏览器决定"AI 说过什么"。新契约只提交服务端签发的
   * message ID + 宿主 + 幂等键，正文由服务端按 ID 读库（Req 8.1/8.6）。
   *
   * 因此 `messageId` 必须是**服务端消息 ID**（`fetchHistory` 带回的 `message_id`）；
   * 本地占位 ID（`ai_…` / `user_…`）无法采纳，此时直接给出中文原因而不发注定失败的请求。
   */
  async function adoptContent(
    messageId: string,
  ): Promise<{ success: boolean; code?: string; message?: string }> {
    const msg = messages.value.find((m) => m.id === messageId)
    if (!msg) return { success: false, code: 'message_not_found', message: '未找到该消息' }
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
          host: {
            type: host.type,
            id: host.id,
            project_id: host.projectId,
            year: host.year,
          },
          idempotency_key: newIdempotencyKey(),
        }),
      })
      if (res.ok) return { success: true }
      // 失败必须带出可执行原因（Req 8.5：保留选择状态并显示可重试原因）
      let code: string | undefined
      let message: string | undefined
      try {
        const body = await res.json()
        const detail = body?.detail ?? body?.data?.detail ?? body
        code = detail?.code
        message = detail?.message ?? (typeof detail === 'string' ? detail : undefined)
      } catch {
        /* 非 JSON 响应体：保留 undefined，由调用方给通用文案 */
      }
      return { success: false, code, message }
    } catch {
      return { success: false, code: 'network_error', message: '网络异常，采纳未生效' }
    }
  }

  // ---------------------------------------------------------------------------
  // 初始化：加载本地缓存
  // ---------------------------------------------------------------------------

  loadFromLocalCache()

  return {
    /** 当前宿主请求（面板上下文条渲染用） */
    hostRequest,
    /** 宿主是否可用于发起请求 */
    hostAvailable,
    /** 宿主不可用的中文原因 */
    hostUnavailableReason,
    /** 消息列表 */
    messages,
    /** 加载状态 */
    loading,
    /** 当前 streaming 文本 */
    streamingText,
    /** 网络状态 */
    isOnline,
    /** 发送消息（SSE streaming） */
    sendMessage,
    /** 拉取服务端历史 */
    fetchHistory,
    /** 清除历史（本地 + 服务端） */
    clearHistory,
    /** 采纳 AI 内容 */
    adoptContent,
    /** 保存到本地缓存 */
    saveToLocalCache,
    /** 从本地缓存加载 */
    loadFromLocalCache,
  }
}
