<template>
  <div class="gt-ai-chat-panel" :class="{ collapsed: isCollapsed }">
    <div class="panel-header" @click="isCollapsed = !isCollapsed">
      <span class="panel-title">💬 AI 助手</span>
      <span class="collapse-icon">{{ isCollapsed ? '◀' : '▶' }}</span>
    </div>
    <div v-if="!isCollapsed" class="panel-body">
      <!-- 项目上下文 -->
      <div v-if="projectContext" class="project-context">
        <span class="context-label">当前项目：</span>
        <span class="context-value">{{ projectContext.name }}</span>
        <span class="context-year">{{ projectContext.year }}年度</span>
      </div>
      <!-- 对话历史 -->
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
            <!-- 数据来源引用 -->
            <div v-if="msg.sources && msg.sources.length > 0" class="message-sources">
              <span class="sources-label">📚 参考来源：</span>
              <span
                v-for="(src, idx) in msg.sources"
                :key="idx"
                class="source-tag"
                @click="navigateToSource(src)"
              >
                {{ src.label }}
              </span>
            </div>
            <!-- 系统操作确认卡片 -->
            <CommandConfirmCard
              v-if="msg.commandCard"
              :command="msg.commandCard"
              @confirm="handleCommandConfirm(msg.commandCard)"
              @cancel="handleCommandCancel(msg.commandCard)"
            />
            <!-- 文件上传区域 -->
            <div v-if="msg.showFileUpload" class="file-upload-area">
              <input
                type="file"
                :multiple="true"
                @change="handleFileUpload($event, msg)"
                class="file-input"
              />
              <span class="upload-hint">拖入或点击上传文件</span>
            </div>
          </div>
        </div>
        <!-- 流式输出中的消息 -->
        <div v-if="streamingText" class="chat-message assistant streaming">
          <div class="message-role">🤖</div>
          <div class="message-content">
            <div class="markdown-content" v-html="renderMarkdown(streamingText)"></div>
          </div>
        </div>
      </div>
      <!-- 输入区域 -->
      <div class="chat-input-area">
        <textarea
          v-model="inputText"
          class="chat-input"
          :rows="3"
          placeholder="输入问题或指令...（支持拖入文件）"
          @keydown.enter.ctrl="sendMessage"
          @drop.prevent="handleDrop"
          @dragover.prevent
        ></textarea>
        <div class="input-actions">
          <button class="btn-attach" @click="triggerFileUpload" title="添加附件">📎</button>
          <button class="btn-send" @click="sendMessage" :disabled="sending || !inputText.trim()">
            {{ sending ? '...' : '发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { useProjectStore } from '@/stores/project'
import CommandConfirmCard from './CommandConfirmCard.vue'
import { useAiChat } from '@/composables/useAiChat'

const props = defineProps({
  projectId: { type: String, default: null }
})

const projectStore = useProjectStore()
const isCollapsed = ref(false)
const inputText = ref('')
const chatHistoryRef = ref(null)

const projectContext = computed(() => {
  const project = projectStore.currentProject
  if (!project) return null
  return {
    name: project.company_name || project.project_name,
    year: project.audit_year || new Date().getFullYear()
  }
})

// [R9 F8 Task 28] 使用 useAiChat composable 替代内联 fetch 逻辑
const chatContext = computed(() => ({
  project_id: props.projectId,
  conversation_id: conversationId.value,
}))

const { messages, loading: sending, streamingText, send, clear } = useAiChat({
  endpoint: '/api/ai/chat',
  context: chatContext,
  streaming: true,
})

const conversationId = ref(null)

// SSE 流式对话（委托给 useAiChat）
async function sendMessage() {
  if (!inputText.value.trim() || sending.value) return
  const text = inputText.value.trim()
  inputText.value = ''
  await send(text)
  scrollToBottom()
}

// 保留文件分析功能（独立于 useAiChat）
function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files)
  if (files.length > 0) {
    processFiles(files)
  }
}

function triggerFileUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.onchange = (e) => processFiles(Array.from(e.target.files))
  input.click()
}

async function handleFileUpload(event, msg) {
  const files = Array.from(event.target.files)
  if (files.length > 0) {
    processFiles(files)
  }
}

async function processFiles(files) {
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('project_id', props.projectId)
    try {
      const res = await fetch('/api/ai/chat/file-analysis', {
        method: 'POST',
        body: formData
      })
      const result = await res.json()
      // 文件分析结果添加到对话（直接 push 到 messages）
      messages.value.push({
        id: Date.now().toString(),
        role: 'assistant',
        text: `📄 **${file.name}** 分析结果：\n\n${result.analysis || result.message || '分析完成'}`,
      })
      scrollToBottom()
    } catch (e) {
      console.error('File analysis error:', e)
    }
  }
}

function navigateToSource(src) {
  if (src.url) {
    window.open(src.url, '_blank')
  }
}

async function handleCommandConfirm(command) {
  try {
    const res = await fetch('/api/ai/chat/execute-command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command_id: command.id, confirmed: true })
    })
    const result = await res.json()
    messages.value.push({
      id: Date.now().toString(),
      role: 'assistant',
      text: `✅ ${command.label} 执行完成\n\n${result.message || ''}`,
    })
    scrollToBottom()
  } catch (e) {
    console.error('Command execution error:', e)
  }
}

function handleCommandCancel(command) {
  messages.value.push({
    id: Date.now().toString(),
    role: 'assistant',
    text: `❌ 已取消操作：${command.label}`,
  })
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (chatHistoryRef.value) {
      chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
    }
  })
}

function renderMarkdown(text) {
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
</script>

<style scoped>
.gt-ai-chat-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 380px;
  background: var(--gt-color-bg-white);
  border-left: 1px solid var(--gt-color-border-light);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width 0.3s;
  box-shadow: -2px 0 8px rgba(0,0,0,0.08);
}

.gt-ai-chat-panel.collapsed {
  width: 40px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(75, 45, 119, 0.08);
  cursor: pointer;
  user-select: none;
}

.panel-title {
  font-weight: 600;
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-base);
}

.collapse-icon {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}

.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.project-context {
  padding: 8px 16px;
  background: var(--gt-color-primary-bg);
  border-bottom: 1px solid var(--gt-color-border-light);
  font-size: var(--gt-font-size-xs);
}

.context-label { color: var(--gt-color-text-secondary); }
.context-value { font-weight: 600; color: var(--gt-color-primary); }
.context-year { color: var(--gt-color-text-tertiary); margin-left: 8px; }

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.chat-message.user { flex-direction: row-reverse; }
.chat-message.assistant { flex-direction: row; }

.message-role {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--gt-color-border-lighter);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-sm);
  flex-shrink: 0;
}

.chat-message.assistant .message-role { background: rgba(75,45,119,0.1); }
.chat-message.user .message-role { background: rgba(45,120,75,0.1); }

.message-content {
  max-width: 75%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: var(--gt-font-size-sm);
  line-height: 1.5;
}

.chat-message.user .message-content {
  background: rgba(45,120,75,0.1);
  border-radius: 12px 4px 12px 12px;
}

.chat-message.assistant .message-content {
  background: var(--gt-color-bg);
  border-radius: 4px 12px 12px 12px;
}

.markdown-content { word-break: break-word; }
.plain-content { white-space: pre-wrap; }

.message-sources {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.sources-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

.source-tag {
  background: rgba(75,45,119,0.1);
  color: var(--gt-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
  cursor: pointer;
}

.source-tag:hover { background: rgba(75,45,119,0.2); }

.file-upload-area {
  margin-top: 8px;
  padding: 12px;
  border: 2px dashed var(--gt-color-border-light);
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
}

.file-upload-area:hover { border-color: var(--gt-color-primary); }
.upload-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

.chat-input-area {
  padding: 12px;
  border-top: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
}

.chat-input {
  width: 100%;
  min-height: 64px;
  border: 1px solid var(--gt-color-border-light);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: var(--gt-font-size-sm);
  resize: none;
  font-family: inherit;
  outline: none;
}

.chat-input:focus { border-color: var(--gt-color-primary); }

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.btn-attach {
  background: none;
  border: none;
  font-size: var(--gt-font-size-xl);
  cursor: pointer;
  padding: 4px 8px;
}

.btn-send {
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  border: none;
  padding: 6px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}

.btn-send:disabled { background: var(--gt-color-border); cursor: not-allowed; }
.btn-send:hover:not(:disabled) { background: var(--gt-color-primary-dark); }

.markdown-content :deep(h1),
.markdown-content :deep(h2) {
  border-bottom: 1px solid var(--gt-color-border-light);
  padding-bottom: 4px;
  margin: 8px 0;
}

.markdown-content :deep(h1) { font-size: var(--gt-font-size-md); }
.markdown-content :deep(h2) { font-size: var(--gt-font-size-sm); }
.markdown-content :deep(p) { margin: 4px 0; }
.markdown-content :deep(ul), .markdown-content :deep(ol) { margin: 4px 0; padding-left: 16px; }
.markdown-content :deep(li) { margin: 2px 0; }
.markdown-content :deep(pre) { background: var(--gt-color-bg); padding: 8px; border-radius: 4px; overflow-x: auto; }
.markdown-content :deep(code) { background: var(--gt-color-border-lighter); padding: 1px 4px; border-radius: 3px; font-size: var(--gt-font-size-xs); }
</style>
