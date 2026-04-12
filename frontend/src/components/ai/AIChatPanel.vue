<template>
  <div class="ai-chat-panel">
    <!-- 侧边栏：会话列表 -->
    <aside class="chat-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <h3>AI 智能问答</h3>
        <button class="icon-btn" @click="sidebarCollapsed = !sidebarCollapsed" title="收起">
          <span>{{ sidebarCollapsed ? '→' : '←' }}</span>
        </button>
      </div>

      <div class="session-actions">
        <button class="btn-primary" @click="handleNewSession">
          <span>+</span> 新建会话
        </button>
      </div>

      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: currentSession?.session_id === session.session_id }"
          @click="handleSelectSession(session.session_id)"
        >
          <div class="session-title">{{ session.title || '未命名会话' }}</div>
          <div class="session-meta">
            {{ formatDate(session.updated_at) }}
          </div>
        </div>
        <div v-if="sessions.length === 0" class="empty-state">
          暂无会话记录
        </div>
      </div>
    </aside>

    <!-- 主聊天区 -->
    <main class="chat-main">
      <!-- 工具栏 -->
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <span class="session-title-display">{{ currentSession?.title || '新建会话' }}</span>
          <span class="badge" v-if="ragEnabled">RAG</span>
        </div>
        <div class="toolbar-right">
          <label class="toggle-label">
            <input type="checkbox" v-model="ragEnabled" />
            启用知识库检索
          </label>
          <button class="btn-sm" @click="clearChat" :disabled="messages.length === 0">
            清空
          </button>
          <button class="btn-sm btn-danger" @click="handleDeleteSession" v-if="currentSession">
            删除
          </button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div class="messages-container" ref="messagesContainer">
        <div v-if="messages.length === 0" class="welcome-state">
          <div class="welcome-icon">💬</div>
          <h2>审计智能问答助手</h2>
          <p>我可以帮助您：</p>
          <ul>
            <li>回答审计专业问题</li>
            <li>解释会计准则和审计准则</li>
            <li>提供审计程序建议</li>
            <li>检索项目知识库</li>
          </ul>
          <div class="quick-prompts">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              class="prompt-chip"
              @click="handleQuickPrompt(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar">
            <span>{{ msg.role === 'user' ? '👤' : '🤖' }}</span>
          </div>
          <div class="message-content">
            <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
            <div class="message-status" v-if="msg.pending">
              <span class="typing-indicator">
                <span></span><span></span><span></span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <div class="input-wrapper">
          <textarea
            v-model="inputMessage"
            placeholder="输入问题，按 Enter 发送，Shift+Enter 换行..."
            rows="1"
            @keydown.enter.exact.prevent="handleSend"
            @input="autoResize"
            ref="inputArea"
          ></textarea>
          <div class="input-actions">
            <button
              class="btn-primary"
              @click="handleSend"
              :disabled="!inputMessage.trim() || loading"
            >
              {{ streaming ? '取消' : '发送' }}
            </button>
          </div>
        </div>
        <div class="input-hints">
          <span>使用 RAG 知识检索增强回答</span>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { useAIChat } from '@/composables/useAI'

const props = defineProps({
  projectId: { type: String, required: true },
})

const {
  sessions,
  currentSession,
  messages,
  loading,
  streaming,
  error,
  createSession,
  fetchSessions,
  loadSession,
  sendMessage,
  sendMessageStream,
  stopStream,
  deleteSession,
} = useAIChat()

const sidebarCollapsed = ref(false)
const inputMessage = ref('')
const ragEnabled = ref(true)
const messagesContainer = ref(null)
const inputArea = ref(null)

const quickPrompts = [
  '请解释什么是实质性程序',
  '如何识别关联方交易',
  '存货监盘的主要程序有哪些',
]

onMounted(async () => {
  await fetchSessions(props.projectId)
})

async function handleNewSession() {
  const session = await createSession(props.projectId, 'general')
  currentSession.value = session
  messages.value = []
}

async function handleSelectSession(sessionId) {
  await loadSession(sessionId)
}

async function handleSend() {
  const text = inputMessage.value.trim()
  if (!text || loading.value) return

  if (!currentSession.value) {
    await handleNewSession()
  }

  inputMessage.value = ''
  scrollToBottom()

  try {
    if (streaming.value) {
      stopStream()
    } else {
      await sendMessageStream(currentSession.value.session_id, text, ragEnabled.value)
    }
  } catch (e) {
    console.error('Send failed:', e)
  }

  scrollToBottom()
}

function handleQuickPrompt(prompt) {
  inputMessage.value = prompt
  handleSend()
}

async function handleDeleteSession() {
  if (!currentSession.value) return
  if (!confirm('确定要删除此会话吗？')) return
  await deleteSession(currentSession.value.session_id)
}

function clearChat() {
  messages.value = []
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function renderMarkdown(text) {
  if (!text) return ''
  // 简单 Markdown 渲染
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

watch(messages, () => scrollToBottom(), { deep: true })
</script>

<style scoped>
.ai-chat-panel {
  display: flex;
  height: 100%;
  background: #f5f7fa;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.chat-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
}

.chat-sidebar.collapsed {
  width: 0;
  overflow: hidden;
  border-right: none;
}

.sidebar-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.session-actions {
  padding: 12px 16px;
}

.session-actions .btn-primary {
  width: 100%;
  padding: 8px 16px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  border-left: 3px solid #409eff;
}

.session-title {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-toolbar {
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.badge {
  padding: 2px 8px;
  background: #67c23a;
  color: #fff;
  border-radius: 10px;
  font-size: 12px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome-state {
  text-align: center;
  padding: 60px 20px;
  color: #606266;
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.welcome-state h2 {
  margin: 0 0 16px;
  color: #303133;
}

.welcome-state ul {
  list-style: none;
  padding: 0;
  margin: 16px 0;
}

.welcome-state li {
  padding: 4px 0;
  color: #606266;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 24px;
}

.prompt-chip {
  padding: 6px 14px;
  background: #f4f4f5;
  border: 1px solid #e4e7ed;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.prompt-chip:hover {
  background: #ecf5ff;
  border-color: #409eff;
  color: #409eff;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message.assistant .message-avatar {
  background: #ecf5ff;
}

.message-content {
  max-width: 70%;
}

.message.user .message-content {
  text-align: right;
}

.message-text {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.message.user .message-text {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-text {
  background: #fff;
  color: #303133;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.message-status {
  margin-top: 4px;
}

.typing-indicator {
  display: inline-flex;
  gap: 3px;
  padding: 4px 8px;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #909399;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.chat-input-area {
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-wrapper textarea {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  max-height: 120px;
}

.input-wrapper textarea:focus {
  outline: none;
  border-color: #409eff;
}

.input-hints {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  color: #606266;
}

.btn-primary {
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}

.btn-sm {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-danger {
  color: #f56c6c;
  border-color: #f56c6c;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
}

.empty-state {
  text-align: center;
  padding: 40px 16px;
  color: #909399;
  font-size: 14px;
}
</style>
