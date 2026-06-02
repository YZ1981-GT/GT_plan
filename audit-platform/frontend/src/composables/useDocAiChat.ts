/**
 * useDocAiChat — 文档级 AI 对话 composable
 *
 * 功能：发起对话 / SSE streaming 接收 / 历史管理 / 离线缓存
 * 需求: 5.2（离线缓存）, 5.3（streaming 响应）
 *
 * @example
 * const { messages, loading, streamingText, sendMessage, fetchHistory, clearHistory, adoptContent } =
 *   useDocAiChat({ docType: 'workpaper', docId: 'wp-001', projectId: 'proj-1', year: 2025 })
 */
import { ref, computed, watch, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

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
  /** 文档类型（workpaper / note / report / knowledge_folder） */
  docType: string | Ref<string>
  /** 文档 ID */
  docId: string | Ref<string>
  /** 项目 ID */
  projectId: string | Ref<string>
  /** 审计年度 */
  year: number | Ref<number>
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

  const cacheKey = computed(() =>
    buildCacheKey(unrefVal(options.docType), unrefVal(options.docId)),
  )

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
    const docType = unrefVal(options.docType)
    const docId = unrefVal(options.docId)

    try {
      const res = await fetch(
        `/api/ai-chat/doc/${docType}/${docId}/history`,
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
          messages.value = list.map((m: any, idx: number) => ({
            id: m.id || `hist_${idx}`,
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
    const docType = unrefVal(options.docType)
    const docId = unrefVal(options.docId)

    // 清除本地缓存
    messages.value = []
    try {
      localStorage.removeItem(cacheKey.value)
    } catch { /* ignore */ }

    // 尝试清除服务端历史
    if (isOnline.value) {
      try {
        await fetch(`/api/ai-chat/doc/${docType}/${docId}/history`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${getToken()}` },
        })
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

    const docType = unrefVal(options.docType)
    const docId = unrefVal(options.docId)
    const projectId = unrefVal(options.projectId)
    const year = unrefVal(options.year)

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
          year,
          project_id: projectId,
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

  async function adoptContent(messageId: string): Promise<{ success: boolean }> {
    const msg = messages.value.find((m) => m.id === messageId)
    if (!msg) return { success: false }

    const docType = unrefVal(options.docType)
    const docId = unrefVal(options.docId)
    const projectId = unrefVal(options.projectId)

    try {
      const res = await fetch('/api/ai-chat/adopt', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          doc_type: docType,
          doc_id: docId,
          project_id: projectId,
          content: msg.text,
          message_id: messageId,
        }),
      })
      return { success: res.ok }
    } catch {
      return { success: false }
    }
  }

  // ---------------------------------------------------------------------------
  // 初始化：加载本地缓存
  // ---------------------------------------------------------------------------

  loadFromLocalCache()

  return {
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
