/**
 * useAiChat — 统一 AI 对话 composable [R9 F8 Task 26]
 *
 * 合并 AiAssistantSidebar / AIChatPanel / WorkpaperWorkbench 内联 AI 对话逻辑
 * 支持 SSE 流式响应 + 消息历史 + 上下文注入
 *
 * @example
 * const { messages, loading, send, clear } = useAiChat({
 *   endpoint: computed(() => `/api/workpapers/${wpId}/ai/chat`),
 *   context: computed(() => ({ project_id: pid, wp_id: wpId })),
 *   streaming: true,
 * })
 */
import { ref, unref, type Ref, type ComputedRef } from 'vue'
import { useAuthStore } from '@/stores/auth'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  sources?: Array<{ label: string; url?: string }>
}

export interface UseAiChatOptions {
  /** API 端点路径（可以是响应式的） */
  endpoint: string | ComputedRef<string> | Ref<string>
  /** 额外上下文参数，会合并到请求体 */
  context?: ComputedRef<Record<string, any>> | Ref<Record<string, any>>
  /** 是否启用 SSE 流式响应（默认 true） */
  streaming?: boolean
}

export function useAiChat(options: UseAiChatOptions) {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const streamingText = ref('')

  function getToken(): string {
    try {
      const authStore = useAuthStore()
      return authStore.token || ''
    } catch {
      return ''
    }
  }

  async function send(message: string) {
    if (!message.trim() || loading.value) return

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      text: message.trim(),
    }
    messages.value.push(userMsg)

    loading.value = true
    streamingText.value = ''

    const endpoint = unref(options.endpoint)
    const context = options.context ? unref(options.context) : {}
    const streaming = options.streaming !== false

    const body: Record<string, any> = {
      message: message.trim(),
      ...context,
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`,
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const contentType = response.headers.get('content-type') || ''
      const isStream = streaming && (
        contentType.includes('text/event-stream') ||
        contentType.includes('text/plain') ||
        response.body !== null
      )

      if (isStream && response.body) {
        // SSE 流式读取
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let fullText = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          // 处理 SSE 格式 data: 前缀
          const lines = chunk.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              if (data === '[DONE]') continue
              fullText += data
            } else if (line.trim() && !line.startsWith(':')) {
              // 非 SSE 格式，直接拼接
              fullText += line
            }
          }
          streamingText.value = fullText
        }

        addAssistantMessage(fullText || streamingText.value)
      } else {
        // JSON 响应
        const result = await response.json()
        const answer = result.answer || result.message || result.text || JSON.stringify(result)
        addAssistantMessage(answer)
      }
    } catch (e: any) {
      console.error('[useAiChat] error:', e)
      addAssistantMessage('AI 服务暂不可用，请稍后重试。')
    } finally {
      loading.value = false
      streamingText.value = ''
    }
  }

  function addAssistantMessage(text: string) {
    const aiMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      text,
    }
    messages.value.push(aiMsg)
  }

  function clear() {
    messages.value = []
    streamingText.value = ''
  }

  return {
    messages,
    loading,
    streamingText,
    send,
    clear,
  }
}
