<template>
  <div
    class="ai-assistant-sidebar"
    :class="{ collapsed: isCollapsed }"
    :style="{ width: isCollapsed ? '28px' : sidebarWidth + 'px' }"
  >
    <!-- 拖拽调整宽度手柄 -->
    <div
      v-show="!isCollapsed"
      class="resize-handle"
      @mousedown="startResize"
    ></div>

    <!-- 折叠切换按钮 -->
    <div class="sidebar-toggle" @click="toggleCollapse">
      <span v-if="!isCollapsed">▶</span>
      <span v-else>◀</span>
    </div>

    <!-- 侧栏内容 -->
    <div v-show="!isCollapsed" class="sidebar-content">
      <div class="sidebar-header">
        <h3 class="sidebar-title">🤖 AI 助手</h3>
      </div>

      <!-- 快捷 prompt 按钮 -->
      <div class="quick-prompts">
        <el-button
          v-for="prompt in quickPrompts"
          :key="prompt.label"
          size="small"
          round
          @click="sendQuickPrompt(prompt.text)"
        >
          {{ prompt.label }}
        </el-button>
      </div>

      <!-- 嵌入式对话区（基于 AIChatPanel 逻辑，增强上下文传递） -->
      <div class="chat-history" ref="chatHistoryRef">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="chat-message"
          :class="msg.role"
        >
          <div class="message-role">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="message-content">
            <div v-if="msg.role === 'assistant'" class="markdown-content" v-html="renderMarkdown(msg.text)"></div>
            <div v-else class="plain-content">{{ msg.text }}</div>
            <!-- 插入到结论区按钮（仅 AI 回复显示） -->
            <div v-if="msg.role === 'assistant' && msg.text" class="insert-action">
              <el-button
                size="small"
                type="primary"
                plain
                @click="insertToConclusion(msg.text)"
              >
                📝 插入到结论区
              </el-button>
            </div>
          </div>
        </div>
        <!-- 流式输出 -->
        <div v-if="streamingMessage" class="chat-message assistant streaming">
          <div class="message-role">🤖</div>
          <div class="message-content">
            <div class="markdown-content" v-html="renderMarkdown(streamingMessage)"></div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <textarea
          v-model="inputText"
          class="chat-input"
          :rows="3"
          placeholder="输入问题...（Ctrl+Enter 发送）"
          @keydown.enter.ctrl="sendMessage"
        ></textarea>
        <div class="input-actions">
          <span class="context-hint" v-if="selectedCell">
            📍 {{ selectedCell.cell_ref }}
          </span>
          <el-button
            size="small"
            type="primary"
            @click="sendMessage"
            :loading="sending"
            :disabled="!inputText.trim()"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

// ─── Props ───
const props = defineProps<{
  projectId: string
  wpId: string
  /** 当前选中的单元格上下文（由 WorkpaperEditor 传入） */
  selectedCell?: {
    cell_ref: string
    value: any
    formula: string | null
    row: number
    column: number
  } | null
}>()

// ─── Emits ───
const emit = defineEmits<{
  /** 插入到结论区事件，WorkpaperEditor 监听后写入 parsed_data.conclusion */
  (e: 'insert-conclusion', text: string): void
}>()

// ─── Route ───
const route = useRoute()
const procedureCode = computed(() => (route.query.from_procedure as string) || '')

// ─── State ───
const STORAGE_KEY_WIDTH = 'ai_sidebar_width'
const DEFAULT_WIDTH = 320
const MIN_WIDTH = 240
const MAX_WIDTH = 600

const isCollapsed = ref(false)
const sidebarWidth = ref(DEFAULT_WIDTH)
const inputText = ref('')
const sending = ref(false)
const streamingMessage = ref('')
const chatHistoryRef = ref<HTMLElement | null>(null)

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
}

const messages = ref<ChatMessage[]>([])

// ─── Quick Prompts ───
const quickPrompts = [
  { label: '解释这个字段', text: '请解释当前选中的这个字段的含义和审计关注点' },
  { label: '上年是怎么做的', text: '上年同底稿这个位置是怎么处理的？有什么参考价值？' },
  { label: '是否需要扩大抽样', text: '根据当前数据情况，是否需要扩大抽样范围？请给出建议' },
]

// ─── Width Persistence ───
function loadWidth() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_WIDTH)
    if (stored) {
      const w = parseInt(stored, 10)
      if (w >= MIN_WIDTH && w <= MAX_WIDTH) {
        sidebarWidth.value = w
      }
    }
  } catch { /* 静默 */ }
}

function saveWidth() {
  try {
    localStorage.setItem(STORAGE_KEY_WIDTH, String(sidebarWidth.value))
  } catch { /* 静默 */ }
}

// ─── Resize Logic ───
let resizing = false
let startX = 0
let startWidth = 0

function startResize(e: MouseEvent) {
  resizing = true
  startX = e.clientX
  startWidth = sidebarWidth.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResize(e: MouseEvent) {
  if (!resizing) return
  // 右侧栏：鼠标向左移动 = 宽度增加
  const diff = startX - e.clientX
  const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + diff))
  sidebarWidth.value = newWidth
}

function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  saveWidth()
}

// ─── Collapse ───
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

// ─── Chat Logic ───
function buildCellContext() {
  if (!props.selectedCell) return undefined
  return {
    cell_ref: props.selectedCell.cell_ref,
    value: props.selectedCell.value,
    formula: props.selectedCell.formula,
    row: props.selectedCell.row,
    column: props.selectedCell.column,
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value) return

  inputText.value = ''
  sending.value = true

  // 添加用户消息
  const userMsg: ChatMessage = {
    id: Date.now().toString(),
    role: 'user',
    text,
  }
  messages.value.push(userMsg)
  scrollToBottom()

  // 准备请求体
  const body: Record<string, any> = {
    message: text,
    wp_id: props.wpId,
    project_id: props.projectId,
  }
  if (procedureCode.value) {
    body.procedure_code = procedureCode.value
  }
  const cellCtx = buildCellContext()
  if (cellCtx) {
    body.cell_context = cellCtx
  }

  streamingMessage.value = ''

  try {
    const response = await fetch(`/api/workpapers/${props.wpId}/chat`, {
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

    // 尝试流式读取
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('text/event-stream') || contentType.includes('text/plain')) {
      const reader = response.body?.getReader()
      if (reader) {
        const decoder = new TextDecoder()
        let fullText = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          fullText += decoder.decode(value, { stream: true })
          streamingMessage.value = fullText
          scrollToBottom()
        }
        addAssistantMessage(fullText)
      }
    } else {
      // JSON 响应
      const result = await response.json()
      const answer = result.answer || result.message || result.text || JSON.stringify(result)
      addAssistantMessage(answer)
    }
  } catch (e: any) {
    console.error('[AiAssistantSidebar] chat error:', e)
    addAssistantMessage('AI 服务暂不可用，请稍后重试。')
  } finally {
    sending.value = false
    streamingMessage.value = ''
  }
}

function addAssistantMessage(text: string) {
  const aiMsg: ChatMessage = {
    id: (Date.now() + 1).toString(),
    role: 'assistant',
    text,
  }
  messages.value.push(aiMsg)
  scrollToBottom()
}

function sendQuickPrompt(text: string) {
  inputText.value = text
  sendMessage()
}

function getToken(): string {
  try {
    const authStore = useAuthStore()
    return authStore.token || ''
  } catch {
    return ''
  }
}

// ─── Insert to Conclusion ───
function insertToConclusion(text: string) {
  emit('insert-conclusion', text)
  ElMessage.success('已插入到结论区')
}

// ─── Markdown Rendering ───
function renderMarkdown(text: string): string {
  if (!text) return ''
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\n/g, '<br>')
}

// ─── Scroll ───
function scrollToBottom() {
  nextTick(() => {
    if (chatHistoryRef.value) {
      chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
    }
  })
}

// ─── Lifecycle ───
onMounted(() => {
  loadWidth()
})

onUnmounted(() => {
  // 清理可能残留的 resize 事件
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<style scoped>
.ai-assistant-sidebar {
  position: relative;
  min-width: 28px;
  border-left: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: var(--el-bg-color, #fff);
  display: flex;
  flex-direction: column;
  transition: min-width 0.2s ease;
  overflow: hidden;
}

.ai-assistant-sidebar.collapsed {
  min-width: 28px;
  width: 28px !important;
}

/* 拖拽手柄 */
.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  cursor: col-resize;
  z-index: 20;
  background: transparent;
  transition: background 0.2s;
}

.resize-handle:hover {
  background: var(--el-color-primary-light-7, #b3d8ff);
}

/* 折叠按钮 */
.sidebar-toggle {
  position: absolute;
  top: 12px;
  left: 6px;
  z-index: 10;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  color: #909399;
  transition: background 0.2s;
}

.sidebar-toggle:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-color-primary, #409eff);
}

/* 内容区 */
.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-left: 4px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px 24px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.sidebar-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

/* 快捷 prompt */
.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.quick-prompts .el-button {
  font-size: 11px;
  padding: 4px 10px;
}

/* 对话历史 */
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-message {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.message-role {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
  background: #f0f0f0;
}

.chat-message.assistant .message-role {
  background: rgba(75, 45, 119, 0.1);
}

.chat-message.user .message-role {
  background: rgba(45, 120, 75, 0.1);
}

.message-content {
  max-width: 80%;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.chat-message.user .message-content {
  background: rgba(45, 120, 75, 0.08);
  border-radius: 10px 4px 10px 10px;
}

.chat-message.assistant .message-content {
  background: #f5f5f5;
  border-radius: 4px 10px 10px 10px;
}

.markdown-content {
  word-break: break-word;
}

.plain-content {
  white-space: pre-wrap;
}

/* 插入到结论区按钮 */
.insert-action {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.insert-action .el-button {
  font-size: 11px;
}

/* 输入区域 */
.chat-input-area {
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: #fff;
}

.chat-input {
  width: 100%;
  min-height: 56px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  resize: none;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: var(--el-color-primary, #409eff);
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}

.context-hint {
  font-size: 11px;
  color: #909399;
  background: var(--el-fill-color-lighter, #fafafa);
  padding: 2px 6px;
  border-radius: 4px;
}

/* Markdown 内容样式 */
.markdown-content :deep(pre) {
  background: #f5f5f5;
  padding: 6px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 11px;
}

.markdown-content :deep(code) {
  background: #f0f0f0;
  padding: 1px 3px;
  border-radius: 3px;
  font-size: 11px;
}

.markdown-content :deep(strong) {
  font-weight: 600;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3) {
  margin: 4px 0;
  font-size: 13px;
}
</style>
