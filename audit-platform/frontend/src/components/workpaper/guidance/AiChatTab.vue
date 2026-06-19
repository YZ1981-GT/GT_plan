<script setup lang="ts">
/**
 * AiChatTab — 底稿编制指导 AI 对话 Tab
 *
 * 功能：
 * - MessageList：历史消息 + streaming 渲染
 * - ChatInput：输入框 + 发送按钮
 * - RecommendedQuestions：快捷按钮（从 guidance 响应取）
 * - SSE 消费（fetch ReadableStream）
 * - 打字动画指示器（streaming 态）
 * - 「清除对话」按钮
 * - LLM 不可用时禁用输入框 + 提示「AI 服务暂不可用」
 *
 * Requirements: 4.1, 4.2, 4.4, 4.5, 4.7, 4.8
 */
import { ref, nextTick, onMounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import CitationList from './CitationList.vue'
import type { Citation } from './CitationList.vue'

// ─── Types ──────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
}

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  wpCode: string
  wpName: string
  projectId: string
  recommendedQuestions: string[]
  aiAvailable: boolean
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamingContent = ref('')
const messageListRef = ref<HTMLDivElement | null>(null)
const historyLoaded = ref(false)
const pendingCitations = ref<Citation[]>([])

// ─── Auth ───────────────────────────────────────────────────────────────────

function getToken(): string {
  try {
    const authStore = useAuthStore()
    return authStore.token || ''
  } catch {
    return ''
  }
}

// ─── Auto-scroll ────────────────────────────────────────────────────────────

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTo({
        top: messageListRef.value.scrollHeight,
        behavior: 'smooth',
      })
    }
  })
}

// ─── Fetch history ──────────────────────────────────────────────────────────

async function fetchHistory() {
  if (!props.wpId || !props.aiAvailable) return

  try {
    const res = await fetch(
      `/api/workpapers/${props.wpId}/ai-chat/history`,
      { headers: { Authorization: `Bearer ${getToken()}` } },
    )
    if (res.ok) {
      const body = await res.json()
      // ResponseWrapperMiddleware 信封解构
      const payload = (body && typeof body === 'object' && 'data' in body && body.data)
        ? body.data
        : body
      const list = payload?.messages
      if (list && list.length > 0) {
        messages.value = list.map((m: any, idx: number) => ({
          id: m.id || `hist_${idx}`,
          role: m.role,
          content: m.content || m.text || '',
        }))
        scrollToBottom()
      }
    }
  } catch {
    // 静默处理
  } finally {
    historyLoaded.value = true
  }
}

// ─── Clear history ──────────────────────────────────────────────────────────

async function clearHistory() {
  messages.value = []
  streamingContent.value = ''

  try {
    await fetch(`/api/workpapers/${props.wpId}/ai-chat/history`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    })
  } catch {
    // 静默处理
  }
}

// ─── Send message (SSE streaming) ───────────────────────────────────────────

async function sendMessage(text: string) {
  const query = text.trim()
  if (!query || isStreaming.value || !props.aiAvailable) return

  // 清空输入框
  inputText.value = ''

  // 添加用户消息
  messages.value.push({
    id: `user_${Date.now()}`,
    role: 'user',
    content: query,
  })
  scrollToBottom()

  // 开始 streaming
  isStreaming.value = true
  streamingContent.value = ''
  pendingCitations.value = []

  try {
    const res = await fetch(`/api/workpapers/${props.wpId}/ai-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({
        query,
        project_id: props.projectId,
        wp_code: props.wpCode,
        wp_name: props.wpName,
      }),
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('无法获取响应流')

    const decoder = new TextDecoder()
    let fullText = ''

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
            pendingCitations.value = event.data || []
          } else if (event.type === 'content') {
            fullText += event.data
            streamingContent.value = fullText
            scrollToBottom()
          } else if (event.type === 'error') {
            fullText += `\n⚠️ ${event.data}`
            streamingContent.value = fullText
          }
          // type === 'done' → 结束
        } catch {
          // 非 JSON 行忽略
        }
      }
    }

    // 流结束，添加 assistant 消息
    messages.value.push({
      id: `ai_${Date.now()}`,
      role: 'assistant',
      content: fullText || '（无回复）',
      citations: pendingCitations.value.length > 0 ? [...pendingCitations.value] : undefined,
    })
    scrollToBottom()
  } catch {
    messages.value.push({
      id: `err_${Date.now()}`,
      role: 'assistant',
      content: 'AI 服务暂不可用，请稍后重试。',
    })
    scrollToBottom()
  } finally {
    isStreaming.value = false
    streamingContent.value = ''
  }
}

// ─── Handle send ────────────────────────────────────────────────────────────

function handleSend() {
  sendMessage(inputText.value)
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  fetchHistory()
})

// wpId 变化时重新加载历史
watch(() => props.wpId, () => {
  messages.value = []
  historyLoaded.value = false
  fetchHistory()
})
</script>

<template>
  <div class="gt-ai-chat">
    <!-- Message list -->
    <div ref="messageListRef" class="gt-ai-chat__messages">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="gt-ai-chat__msg"
        :class="[`gt-ai-chat__msg--${msg.role}`]"
      >
        <div class="gt-ai-chat__msg-bubble">{{ msg.content }}</div>
        <CitationList
          v-if="msg.role === 'assistant' && msg.citations && msg.citations.length > 0"
          :citations="msg.citations"
        />
      </div>

      <!-- Streaming indicator -->
      <div v-if="isStreaming" class="gt-ai-chat__msg gt-ai-chat__msg--assistant">
        <div class="gt-ai-chat__msg-bubble gt-ai-chat__msg-bubble--streaming">
          <span v-if="streamingContent">{{ streamingContent }}</span>
          <span class="gt-ai-chat__typing-dots">
            <span></span><span></span><span></span>
          </span>
        </div>
      </div>

      <!-- Empty state: recommended questions -->
      <div
        v-if="messages.length === 0 && !isStreaming && historyLoaded && recommendedQuestions.length > 0"
        class="gt-ai-chat__recommended"
      >
        <p class="gt-ai-chat__recommended-title">试试以下问题：</p>
        <button
          v-for="(q, idx) in recommendedQuestions"
          :key="idx"
          class="gt-ai-chat__recommended-btn"
          @click="sendMessage(q)"
        >
          {{ q }}
        </button>
      </div>
    </div>

    <!-- Controls bar -->
    <div class="gt-ai-chat__controls">
      <el-button
        text
        size="small"
        :disabled="messages.length === 0 || isStreaming"
        @click="clearHistory"
      >
        清除对话
      </el-button>
      <span v-if="!aiAvailable" class="gt-ai-chat__unavailable">
        AI 服务暂不可用
      </span>
    </div>

    <!-- Input area -->
    <div class="gt-ai-chat__input-area">
      <el-input
        v-model="inputText"
        :disabled="isStreaming || !aiAvailable"
        placeholder="输入问题…"
        :rows="1"
        type="textarea"
        resize="none"
        autosize
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button
        type="primary"
        :disabled="!inputText.trim() || isStreaming || !aiAvailable"
        size="small"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.gt-ai-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ─── Messages area ────────────────────────────────────────────────────── */

.gt-ai-chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-ai-chat__msg {
  display: flex;
}

.gt-ai-chat__msg--user {
  justify-content: flex-end;
}

.gt-ai-chat__msg--assistant {
  justify-content: flex-start;
}

.gt-ai-chat__msg-bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.gt-ai-chat__msg--user .gt-ai-chat__msg-bubble {
  background: var(--gt-primary, #4b2d77);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.gt-ai-chat__msg--assistant .gt-ai-chat__msg-bubble {
  background: #f5f5f5;
  color: #333;
  border-bottom-left-radius: 4px;
}

.gt-ai-chat__msg-bubble--streaming {
  min-height: 24px;
}

/* ─── Typing animation ─────────────────────────────────────────────────── */

.gt-ai-chat__typing-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 4px;
  vertical-align: middle;
}

.gt-ai-chat__typing-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--gt-primary, #4b2d77);
  opacity: 0.5;
  animation: gt-typing-bounce 1.2s infinite;
}

.gt-ai-chat__typing-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.gt-ai-chat__typing-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes gt-typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* ─── Recommended questions ────────────────────────────────────────────── */

.gt-ai-chat__recommended {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 12px;
}

.gt-ai-chat__recommended-title {
  font-size: 12px;
  color: #999;
  margin: 0 0 4px 0;
}

.gt-ai-chat__recommended-btn {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 8px;
  background: var(--gt-bg-light, #f4f0fa);
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: background 0.2s, border-color 0.2s;
}

.gt-ai-chat__recommended-btn:hover {
  background: var(--gt-border-light, #d8b8ee);
  border-color: var(--gt-primary, #4b2d77);
}

/* ─── Controls ─────────────────────────────────────────────────────────── */

.gt-ai-chat__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.gt-ai-chat__unavailable {
  font-size: 11px;
  color: #f56c6c;
  font-weight: 500;
}

/* ─── Input area ───────────────────────────────────────────────────────── */

.gt-ai-chat__input-area {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 12px 12px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.gt-ai-chat__input-area :deep(.el-textarea__inner) {
  border-radius: 8px;
  min-height: 32px !important;
  max-height: 80px;
  font-size: 13px;
  padding: 6px 12px;
}

.gt-ai-chat__input-area .el-button {
  border-radius: 8px;
  flex-shrink: 0;
}
</style>
