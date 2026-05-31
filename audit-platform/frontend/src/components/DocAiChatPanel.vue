<template>
  <el-drawer
    :model-value="visible"
    title="💬 AI 文档对话"
    direction="rtl"
    size="460px"
    :destroy-on-close="false"
    @update:model-value="handleVisibleChange"
  >
    <!-- 文档上下文信息 -->
    <div class="doc-context-bar">
      <el-tag type="info" size="small" effect="plain">
        {{ docTypeLabel }}
      </el-tag>
      <span class="doc-context-id">{{ docId }}</span>
    </div>

    <!-- 对话历史 -->
    <div ref="chatHistoryRef" class="chat-history">
      <el-empty
        v-if="messages.length === 0 && !streamingText"
        description="暂无对话，输入问题开始提问"
        :image-size="64"
      />
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="chat-message"
        :class="msg.role"
      >
        <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="message-body">
          <div
            v-if="msg.role === 'assistant'"
            class="markdown-content"
            v-html="renderMarkdown(msg.text)"
          />
          <div v-else class="plain-content">{{ msg.text }}</div>

          <!-- 引用来源标注 -->
          <div v-if="msg.citations && msg.citations.length > 0" class="citation-list">
            <span class="citation-label">📚 引用来源：</span>
            <span
              v-for="(cite, idx) in msg.citations"
              :key="idx"
              class="citation-tag"
              @click="handleCitationClick(cite)"
            >
              {{ cite.source_name || cite.source_type }}
              <span v-if="cite.paragraph_index != null" class="cite-para">
                §{{ cite.paragraph_index }}
              </span>
            </span>
          </div>

          <!-- 采纳按钮（仅 assistant 消息） -->
          <div v-if="msg.role === 'assistant' && msg.text" class="message-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :icon="Check"
              @click="handleAdopt(msg)"
            >
              采纳
            </el-button>
          </div>
        </div>
      </div>

      <!-- 流式输出中 -->
      <div v-if="streamingText" class="chat-message assistant streaming">
        <div class="message-avatar">🤖</div>
        <div class="message-body">
          <div class="markdown-content" v-html="renderMarkdown(streamingText)" />
        </div>
      </div>
    </div>

    <!-- @mention 选择器 -->
    <div v-if="showMentionPopover" class="mention-popover">
      <div class="mention-header">选择额外知识范围</div>
      <div
        v-for="scope in availableScopes"
        :key="scope.id"
        class="mention-item"
        :class="{ selected: selectedScopes.includes(scope.id) }"
        @click="toggleScope(scope.id)"
      >
        <el-icon><Folder /></el-icon>
        <span>{{ scope.name }}</span>
        <el-icon v-if="selectedScopes.includes(scope.id)"><Check /></el-icon>
      </div>
      <div v-if="availableScopes.length === 0" class="mention-empty">
        暂无可选知识范围
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <!-- 已选 scope 标签 -->
      <div v-if="selectedScopes.length > 0" class="selected-scopes">
        <el-tag
          v-for="scopeId in selectedScopes"
          :key="scopeId"
          size="small"
          closable
          @close="removeScope(scopeId)"
        >
          {{ getScopeName(scopeId) }}
        </el-tag>
      </div>
      <div class="input-row">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="2"
          placeholder="输入问题...（输入 @ 选择额外知识范围）"
          :disabled="loading"
          @keydown="handleInputKeydown"
        />
      </div>
      <div class="input-actions">
        <el-button
          size="small"
          :icon="FolderOpened"
          @click="showMentionPopover = !showMentionPopover"
          title="选择额外知识范围"
        >
          @
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="loading"
          :disabled="!inputText.trim()"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Check, Folder, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useDocAiChat, type DocChatMessage, type Citation } from '@/composables/useDocAiChat'
import { useCellLocate } from '@/composables/useCellLocate'
import { eventBus } from '@/utils/eventBus'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

interface ScopeOption {
  id: string
  name: string
}

const props = defineProps<{
  /** 文档类型（workpaper / note / report / knowledge_folder） */
  docType: string
  /** 文档 ID */
  docId: string
  /** 项目 ID */
  projectId: string
  /** 审计年度 */
  year: number
  /** 控制抽屉显隐 */
  visible: boolean
}>()

const emit = defineEmits<{
  /** 采纳 AI 内容 */
  adopt: [payload: { content: string; messageId: string }]
  /** 关闭面板 */
  close: []
  /** v-model:visible 更新 */
  'update:visible': [val: boolean]
}>()

// ---------------------------------------------------------------------------
// Composable — 对话核心逻辑
// ---------------------------------------------------------------------------

const router = useRouter()
const { locateCell } = useCellLocate()

const {
  messages,
  loading,
  streamingText,
  sendMessage: doSendMessage,
  fetchHistory,
  adoptContent,
} = useDocAiChat({
  docType: computed(() => props.docType),
  docId: computed(() => props.docId),
  projectId: computed(() => props.projectId),
  year: computed(() => props.year),
})

// ---------------------------------------------------------------------------
// Local UI State
// ---------------------------------------------------------------------------

const inputText = ref('')
const chatHistoryRef = ref<HTMLElement | null>(null)

// @mention 相关
const showMentionPopover = ref(false)
const selectedScopes = ref<string[]>([])
const availableScopes = ref<ScopeOption[]>([])

// ---------------------------------------------------------------------------
// 文档类型标签
// ---------------------------------------------------------------------------

const DOC_TYPE_LABELS: Record<string, string> = {
  workpaper: '底稿',
  note: '附注',
  report: '报表',
  knowledge_folder: '知识库文件夹',
}

const docTypeLabel = computed(() => DOC_TYPE_LABELS[props.docType] || props.docType)

// ---------------------------------------------------------------------------
// 抽屉显隐
// ---------------------------------------------------------------------------

function handleVisibleChange(val: boolean) {
  emit('update:visible', val)
  if (!val) {
    emit('close')
    showMentionPopover.value = false
  }
}

// 打开时拉取服务端历史 + 可选范围
watch(() => props.visible, async (val) => {
  if (val) {
    await fetchHistory()
    await fetchAvailableScopes()
  }
})

// ---------------------------------------------------------------------------
// 拉取可选知识范围（extra_scopes）
// ---------------------------------------------------------------------------

async function fetchAvailableScopes() {
  try {
    const authStore = useAuthStore()
    const res = await fetch(
      `/api/knowledge/folders?project_id=${props.projectId}`,
      {
        headers: { Authorization: `Bearer ${authStore.token || ''}` },
      },
    )
    if (res.ok) {
      const data = await res.json()
      availableScopes.value = (data.items || data || []).map((f: any) => ({
        id: f.id || f.folder_id,
        name: f.name || f.folder_name || f.title,
      }))
    }
  } catch {
    availableScopes.value = []
  }
}

// ---------------------------------------------------------------------------
// 发送消息（委托 composable）
// ---------------------------------------------------------------------------

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  inputText.value = ''
  showMentionPopover.value = false
  scrollToBottom()

  await doSendMessage(
    text,
    selectedScopes.value.length > 0 ? selectedScopes.value : undefined,
  )
  scrollToBottom()
}

// ---------------------------------------------------------------------------
// 采纳按钮
// ---------------------------------------------------------------------------

async function handleAdopt(msg: DocChatMessage) {
  const { success } = await adoptContent(msg.id)
  if (success) {
    emit('adopt', { content: msg.text, messageId: msg.id })
    ElMessage.success('已提交采纳，等待确认')
  } else {
    ElMessage.error('采纳提交失败，请稍后重试')
  }
}

// ---------------------------------------------------------------------------
// 引用来源点击跳转（需求 3.2, 3.3 — D3 引用可追溯）
// ---------------------------------------------------------------------------

function handleCitationClick(cite: Citation) {
  if (!cite.source_id) return

  switch (cite.source_type) {
    case 'knowledge_doc':
      // 知识文档：直接打开知识文件页面
      window.open(`/knowledge/files/${cite.source_id}`, '_blank')
      break

    case 'workpaper':
      // 底稿：使用 router 导航到底稿编辑器，并通过 eventBus 触发单元格定位
      navigateToWorkpaper(cite)
      break

    case 'trial_balance':
      // 试算表：导航到试算表视图
      router.push({
        name: 'TrialBalance',
        params: { projectId: props.projectId },
      })
      break

    default:
      // 通用 fallback：打开文档页面
      window.open(`/documents/${cite.source_id}`, '_blank')
      break
  }
}

/**
 * 导航到底稿并定位到引用位置
 * 使用 useCellLocate + eventBus 实现精确定位
 */
function navigateToWorkpaper(cite: Citation) {
  const wpId = cite.source_id

  // 构建定位目标（snake_case，对齐 useCellLocate 签名）
  const locateTarget = {
    wp_code: cite.source_name || '',
    sheet_name: (cite as any).sheet_name || null,
    cell_ref: (cite as any).cell_ref || null,
    component_type: (cite as any).component_type || 'c-note-table',
  }

  // 如果当前已在底稿编辑器页面且是同一底稿，直接定位
  const hasCellInfo = locateTarget.cell_ref || locateTarget.sheet_name
  if (hasCellInfo) {
    // 通过 eventBus 发送定位事件（GtWpRenderer 监听此事件）
    nextTick(() => {
      eventBus.emit('workpaper:locate-cell', {
        wpId,
        sheetName: locateTarget.sheet_name || undefined,
        cellRef: locateTarget.cell_ref || '',
        componentType: locateTarget.component_type || undefined,
        wpCode: locateTarget.wp_code || undefined,
      })
    })
  }

  // 导航到底稿编辑器
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: props.projectId, wpId },
  })
}

// ---------------------------------------------------------------------------
// @mention 逻辑
// ---------------------------------------------------------------------------

function handleInputKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault()
    sendMessage()
  }
  if (e.key === '@' || (e.key === '2' && e.shiftKey)) {
    showMentionPopover.value = true
  }
}

function toggleScope(scopeId: string) {
  const idx = selectedScopes.value.indexOf(scopeId)
  if (idx >= 0) {
    selectedScopes.value.splice(idx, 1)
  } else {
    selectedScopes.value.push(scopeId)
  }
}

function removeScope(scopeId: string) {
  selectedScopes.value = selectedScopes.value.filter((s) => s !== scopeId)
}

function getScopeName(scopeId: string): string {
  const found = availableScopes.value.find((s) => s.id === scopeId)
  return found?.name || scopeId
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function scrollToBottom() {
  nextTick(() => {
    if (chatHistoryRef.value) {
      chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
    }
  })
}

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
</script>

<style scoped>
.doc-context-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--gt-color-primary-bg, #f5f0ff);
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
  font-size: var(--gt-font-size-xs, 12px);
}

.doc-context-id {
  color: var(--gt-color-text-tertiary, #909399);
  font-family: monospace;
  font-size: var(--gt-font-size-xs, 12px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 对话历史 */
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  max-height: calc(100vh - 280px);
}

.chat-message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  background: var(--gt-color-border-lighter, #f2f6fc);
}

.chat-message.assistant .message-avatar {
  background: rgba(75, 45, 119, 0.1);
}

.chat-message.user .message-avatar {
  background: rgba(45, 120, 75, 0.1);
}

.message-body {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: var(--gt-font-size-sm, 13px);
  line-height: 1.6;
}

.chat-message.user .message-body {
  background: rgba(45, 120, 75, 0.08);
  border-radius: 12px 4px 12px 12px;
}

.chat-message.assistant .message-body {
  background: var(--gt-color-bg, #f5f7fa);
  border-radius: 4px 12px 12px 12px;
}

.plain-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.markdown-content {
  word-break: break-word;
}

/* 引用来源 */
.citation-list {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--gt-color-border-light, #ebeef5);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.citation-label {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-tertiary, #909399);
}

.citation-tag {
  background: rgba(75, 45, 119, 0.08);
  color: var(--gt-color-primary, #4b2d77);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs, 12px);
  cursor: pointer;
  transition: background 0.2s;
}

.citation-tag:hover {
  background: rgba(75, 45, 119, 0.18);
}

.cite-para {
  margin-left: 2px;
  opacity: 0.7;
}

/* 采纳按钮 */
.message-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

/* @mention 弹出层 */
.mention-popover {
  margin: 0 16px;
  padding: 8px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  max-height: 200px;
  overflow-y: auto;
}

.mention-header {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary, #606266);
  padding: 4px 8px;
  font-weight: 600;
}

.mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm, 13px);
  transition: background 0.15s;
}

.mention-item:hover {
  background: var(--gt-color-primary-bg, #f5f0ff);
}

.mention-item.selected {
  background: rgba(75, 45, 119, 0.1);
  color: var(--gt-color-primary, #4b2d77);
}

.mention-empty {
  padding: 12px 8px;
  text-align: center;
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-tertiary, #909399);
}

/* 输入区域 */
.chat-input-area {
  padding: 12px 16px;
  border-top: 1px solid var(--gt-color-border-light, #ebeef5);
  background: var(--gt-color-bg-white, #fff);
}

.selected-scopes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.input-row {
  margin-bottom: 8px;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Markdown 渲染样式 */
.markdown-content :deep(pre) {
  background: var(--gt-color-bg, #f5f7fa);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: var(--gt-font-size-xs, 12px);
}

.markdown-content :deep(code) {
  background: var(--gt-color-border-lighter, #f2f6fc);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs, 12px);
}

.markdown-content :deep(strong) {
  font-weight: 600;
}

/* streaming 动画 */
.chat-message.streaming .message-body::after {
  content: '▌';
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
