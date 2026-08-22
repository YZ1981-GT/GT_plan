<template>
  <div
    class="platform-ai-chat-panel"
    :class="{ 'platform-ai-chat-panel--unavailable': !hostAvailable }"
  >
    <!-- 宿主上下文条 -->
    <div
      class="platform-ai-chat-panel__scope"
      :class="{ 'is-global': !hostRequest.projectToolsEnabled }"
      role="status"
      :aria-label="`AI 对话范围：${scopeHint}`"
    >
      <el-tag
        :type="hostAvailable ? 'info' : 'warning'"
        size="small"
        effect="plain"
      >
        {{ hostRequest.label }}
      </el-tag>
      <span class="platform-ai-chat-panel__hint">{{ scopeHint }}</span>
      <!-- 选择模式入口按钮 -->
      <el-button
        v-if="noteCapture.hasSelectableMessages.value && !noteCapture.selectionMode.value"
        class="platform-ai-chat-panel__select-btn"
        size="small"
        text
        :icon="Select"
        aria-label="选择消息（可复制或转存为笔记）"
        @click="noteCapture.enterSelectionMode()"
      />
    </div>

    <!-- 选择模式工具条 -->
    <div
      v-if="showSelectionToolbar"
      class="platform-ai-chat-panel__selection-toolbar"
      role="toolbar"
      aria-label="消息选择操作"
    >
      <span class="platform-ai-chat-panel__selection-count">
        已选 {{ noteCapture.selectedCount.value }} 条
      </span>
      <el-button
        size="small"
        text
        @click="noteCapture.selectAll()"
      >
        全选
      </el-button>
      <el-button
        size="small"
        text
        :disabled="!noteCapture.hasSelection.value"
        :icon="DocumentCopy"
        @click="handleCopySelected"
      >
        复制
      </el-button>
      <el-button
        size="small"
        type="primary"
        :disabled="!noteCapture.hasSelection.value || !noteCapture.allSelectedHaveServerId.value"
        :loading="noteCapture.saving.value"
        :icon="Memo"
        @click="handleSaveAsNote"
      >
        转存笔记
      </el-button>
      <el-button
        size="small"
        text
        :icon="Close"
        aria-label="退出选择模式"
        @click="noteCapture.exitSelectionMode()"
      >
        取消
      </el-button>
    </div>

    <!-- 保存失败重试提示条 -->
    <div
      v-if="noteCapture.lastError.value && noteCapture.selectionMode.value"
      class="platform-ai-chat-panel__retry-bar"
      role="alert"
      aria-live="polite"
    >
      <span>{{ noteCapture.lastError.value }}</span>
      <el-button size="small" type="primary" plain :loading="noteCapture.saving.value" @click="handleRetrySave">
        重试
      </el-button>
    </div>

    <!-- 消息列表区 -->
    <div
      ref="messageListRef"
      class="platform-ai-chat-panel__messages"
      role="log"
      aria-label="AI 对话消息列表"
      aria-live="polite"
      aria-relevant="additions"
    >
      <el-empty
        v-if="messages.length === 0 && !streamingDelta"
        description="暂无对话，输入问题开始提问"
        :image-size="64"
      />
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="platform-ai-chat-panel__msg"
        :class="[
          msg.role,
          msg.status,
          {
            'is-selectable': noteCapture.selectionMode.value && msg.role === 'assistant' && msg.status === 'completed',
            'is-selected': noteCapture.selectionMode.value && isSelected(msg.id),
          },
        ]"
        role="article"
        :aria-label="msg.role === 'user' ? '用户消息' : 'AI 回复'"
        :aria-selected="noteCapture.selectionMode.value && msg.role === 'assistant' ? isSelected(msg.id) : undefined"
        @click="handleMsgClick(msg)"
      >
        <!-- 选择模式下的选中指示 -->
        <div
          v-if="noteCapture.selectionMode.value && msg.role === 'assistant' && msg.status === 'completed'"
          class="platform-ai-chat-panel__msg-check"
          aria-hidden="true"
        >
          <el-icon v-if="isSelected(msg.id)" color="var(--el-color-primary)"><Check /></el-icon>
          <span v-else class="platform-ai-chat-panel__msg-check-empty" />
        </div>
        <div class="platform-ai-chat-panel__msg-avatar" aria-hidden="true">
          {{ msg.role === 'user' ? '👤' : '🤖' }}
        </div>
        <div class="platform-ai-chat-panel__msg-body">
          <div
            v-if="msg.role === 'assistant'"
            class="markdown-content"
            v-html="renderMarkdown(msg.text)"
          />
          <div v-else class="plain-content">{{ msg.text }}</div>

          <!-- 引用来源 -->
          <div v-if="msg.citations && msg.citations.length > 0" class="platform-ai-chat-panel__citations">
            <span class="citation-label">📚 引用来源：</span>
            <span
              v-for="(cite, idx) in msg.citations"
              :key="idx"
              class="citation-tag"
            >
              {{ cite.source_name || cite.source_type }}
            </span>
          </div>

          <!-- 采纳按钮 -->
          <div v-if="msg.role === 'assistant' && msg.status === 'completed'" class="platform-ai-chat-panel__msg-actions">
            <el-button size="small" type="primary" plain @click="handleAdopt(msg)">
              采纳
            </el-button>
          </div>
        </div>
      </div>

      <!-- 流式输出（视觉渲染，aria-hidden 避免逐 token 轰炸屏幕阅读器） -->
      <div v-if="streamingDelta" class="platform-ai-chat-panel__msg assistant streaming" aria-hidden="true">
        <div class="platform-ai-chat-panel__msg-avatar">🤖</div>
        <div class="platform-ai-chat-panel__msg-body">
          <div class="markdown-content" v-html="renderMarkdown(streamingDelta)" />
        </div>
      </div>
    </div>

    <!-- 流式文本节流播报（屏幕阅读器专用，视觉隐藏） -->
    <div
      class="gt-sr-only"
      aria-live="polite"
      aria-atomic="true"
      role="status"
    >
      {{ streamingAnnouncement }}
    </div>

    <!--
      Context Manifest 检视器（Task 15 / Req 5.7, 5.9 / Property 12）
      挂在消息区与输入区之间，折叠态默认（组件内 expanded 初值 false）。
      manifest 来自 context_ready 事件（chatRunState.contextManifest），
      经 normalizeContextManifest 投影成组件契约要求的扁平数组。
    -->
    <div v-if="contextManifestReady" class="platform-ai-chat-panel__context">
      <ChatContextInspector
        :manifest="contextManifestItems"
        :token-budget="contextTokenBudget"
      />
    </div>

    <!-- 复核模式条（Task 21 / Req 9.1, 9.4, 9.5 / Properties 23, 24） -->
    <ChatReviewModeBar
      :host="host"
      :sheet-name="sheetName"
      :initial-review-mode="serverReviewMode"
      @update:review-mode="handleReviewModeChange"
    />

    <!-- 错误展示 -->
    <div
      v-if="displayError && phase === 'error'"
      class="platform-ai-chat-panel__error"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <el-icon aria-hidden="true"><WarningFilled /></el-icon>
      <span>{{ displayError }}</span>
    </div>

    <!-- Quota 提示（live-region，节流展示） -->
    <div
      v-if="quotaHint"
      class="platform-ai-chat-panel__quota"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span>{{ quotaHint }}</span>
    </div>

    <!-- 输入区 -->
    <div
      ref="inputAreaRef"
      class="platform-ai-chat-panel__input"
      @paste="handleInputPaste"
    >
      <!--
        Mention 选择器（Task 15 / Req 5.1, 5.4 / Properties 12, 13）
        浮在输入区**之上**（absolute + bottom:100%），不遮挡已输入内容。
        由输入框里的活跃 `@` 词唤出；Escape / 点击面板外 / `@` 词消失即关闭。
      -->
      <div class="platform-ai-chat-panel__mention-layer">
        <ChatMentionPicker
          :key="mentionPickerEpoch"
          :host="hostRequest.host"
          :open="mentionPickerOpen"
          @change="onMentionChange"
          @close="closeMentionPicker"
        />
      </div>

      <!-- 已选引用 tag（可移除；这些是真正随下一轮 run 提交的 mentions） -->
      <div
        v-if="selectedMentions.length > 0"
        class="platform-ai-chat-panel__mention-tags"
        role="list"
        aria-label="本轮已引用的资源"
      >
        <el-tag
          v-for="m in selectedMentions"
          :key="`${m.type}:${m.id}`"
          size="small"
          type="info"
          effect="plain"
          closable
          role="listitem"
          :aria-label="`已引用 ${mentionTypeLabel(m.type)}：${m.label}（点击移除）`"
          @close="removeMention(m)"
        >
          {{ mentionTypeLabel(m.type) }} · {{ m.label }}
        </el-tag>
      </div>

      <!-- 附件选择器（Task 17） -->
      <ChatAttachmentPicker
        ref="attachmentPickerRef"
        :disabled="loading || !hostAvailable"
        @change="onAttachmentChange"
      />

      <!-- 状态描述（屏幕阅读器可见） -->
      <span id="chat-input-status" class="gt-sr-only">
        {{ inputStatusHint }}
      </span>
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        :placeholder="hostAvailable ? '输入问题...（输入 @ 引用资源，Ctrl+Enter 发送）' : scopeHint"
        :disabled="loading || !hostAvailable"
        :aria-label="hostAvailable ? 'AI 对话输入框' : `AI 对话不可用：${scopeHint}`"
        aria-describedby="chat-input-status"
        @keydown="handleKeydown"
      />
      <div class="platform-ai-chat-panel__input-actions">
        <el-button
          v-if="isActive"
          type="danger"
          size="small"
          plain
          aria-label="取消当前 AI 回答"
          @click="handleCancel"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="loading"
          :disabled="!draft.trim() || !hostAvailable"
          :aria-label="loading ? 'AI 正在回答中' : '发送问题'"
          @click="handleSend"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PlatformAiChatPanel — 唯一核心 AI 聊天面板
 *
 * 所有宿主（底稿、报表、附注、知识库、DshPanel、独立窗口）通过 :host prop 复用此面板。
 * 面板编排 usePlatformAiChat（两阶段 API）+ chatRunState（SSE 生命周期）。
 *
 * Feature: dsh-agent-panel-integration / Task 9
 * Validates: Requirements 1.1, 1.4, 1.5, 1.8, 1.9, 1.10, 3.5
 * Properties: 5, 39
 */
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { WarningFilled, DocumentCopy, Memo, Check, Close, Select } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { sanitizeHtml } from '@/composables/useSanitize'
import { usePlatformAiChat, type ChatMessage } from '@/composables/usePlatformAiChat'
import { useAiNoteCapture } from '@/composables/useAiNoteCapture'
import { hostScopeHint, type AiHostRequest } from '@/composables/useAiHostContext'
import {
  MENTION_TYPE_LABELS,
  type MentionItem,
  type MentionType,
} from '@/composables/useAiMention'
import {
  normalizeContextManifest,
  readContextTokenBudget,
} from '@/utils/chatContextManifest'
import ChatAttachmentPicker from './ChatAttachmentPicker.vue'
import ChatContextInspector from './ChatContextInspector.vue'
import ChatMentionPicker from './ChatMentionPicker.vue'
import ChatReviewModeBar from './ChatReviewModeBar.vue'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  /**
   * 宿主上下文请求（由 useAiHostContext 的六个宿主 adapter 之一构造）。
   * 所有宿主页面提交同一形状，面板本身不拼 doc_type/doc_id/project_id/year。
   */
  host: AiHostRequest
  /** 面板是否可见（可选，用于触发历史加载） */
  visible?: boolean
  /** 当前底稿 sheet 名（用于复核模式匹配更精确的 prompt） */
  sheetName?: string
}>()

const emit = defineEmits<{
  /** 采纳 AI 内容 */
  adopt: [payload: { content: string; messageId: string }]
}>()

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

const {
  messages,
  loading,
  draft,
  hostRequest,
  hostAvailable,
  hostUnavailableReason,
  phase,
  streamingDelta,
  displayError,
  isActive,
  sendMessage,
  cancelRun,
  fetchHistory,
  adoptContent,
} = usePlatformAiChat({
  host: computed(() => props.host),
})

const scopeHint = computed(() => hostScopeHint(props.host))
const messageListRef = ref<HTMLElement | null>(null)
const inputAreaRef = ref<HTMLElement | null>(null)
const attachmentPickerRef = ref<InstanceType<typeof ChatAttachmentPicker> | null>(null)
const pendingAttachmentIds = ref<string[]>([])

// ---------------------------------------------------------------------------
// Mention（Task 15 / Req 5.1, 5.4, 5.5 / Properties 12, 13）
//
// 🔴 面板此前**没有 import ChatMentionPicker** —— 组件与 13 条 vitest 守卫都在，
// 但没有任何宿主渲染它，浏览器里 `@` 什么都不会发生，Req 5.1 在产品里等于没实现。
// 这里补的三段缺一不可：① `@` 唤出 picker ② 已选项在输入区上方可见可移除
// ③ 已选项**真的进入下一轮 run 的 mentions 载荷**（只渲染不提交仍是死代码）。
// ---------------------------------------------------------------------------

/** picker 是否展开（由输入框里的活跃 `@` 词驱动） */
const mentionPickerOpen = ref(false)
/** 本轮已选引用；这是提交给 run 的唯一真源 */
const selectedMentions = ref<MentionItem[]>([])
/**
 * picker 实例 epoch。发送后 +1 强制重建 picker，
 * 让它内部 `useAiMention` 的 `selected` 与宿主这份清单一起归零 ——
 * 否则上一轮的高亮会残留，用户以为引用还在。
 */
const mentionPickerEpoch = ref(0)

/**
 * 输入框里是否存在**活跃的 `@` 词**。
 *
 * 判据：最后一个 `@` 之后不含空白。`@` 后出现空白说明这个引用词已经写完
 * （用户在写正常句子），此时不该继续弹 picker。
 */
function hasActiveMentionToken(text: string): boolean {
  const at = text.lastIndexOf('@')
  if (at < 0) return false
  return !/\s/.test(text.slice(at + 1))
}

/** picker 的多选结果 → 宿主清单（picker 侧是权威，宿主原样镜像） */
function onMentionChange(items: MentionItem[]) {
  selectedMentions.value = [...items]
}

function removeMention(item: MentionItem) {
  selectedMentions.value = selectedMentions.value.filter(
    (m) => !(m.type === item.type && m.id === item.id),
  )
}

function closeMentionPicker() {
  mentionPickerOpen.value = false
}

function mentionTypeLabel(type: string): string {
  return MENTION_TYPE_LABELS[type as MentionType] ?? type
}

// 输入内容变化 → 按活跃 `@` 词开/关 picker。
// 用 watch(draft) 而不是 keydown：程序化赋值（粘贴、Playwright 的 fill()）不产生按键事件。
watch(draft, (val) => {
  if (!hostAvailable.value) {
    mentionPickerOpen.value = false
    return
  }
  mentionPickerOpen.value = hasActiveMentionToken(val)
})

/** 点击输入区之外关闭 picker（picker 本身在输入区容器内，点它不会关） */
function handleDocumentMouseDown(evt: MouseEvent) {
  if (!mentionPickerOpen.value) return
  const root = inputAreaRef.value
  const target = evt.target
  if (root && target instanceof Node && !root.contains(target)) {
    mentionPickerOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleDocumentMouseDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentMouseDown)
})

// ---------------------------------------------------------------------------
// Review Mode（Task 21 / Req 9.1, 9.4, 9.5 / Properties 23, 24）
// 模式从 server session 恢复，不写 localStorage
// ---------------------------------------------------------------------------

/** 从 server session 恢复的复核模式初始值（由 fetchHistory 解析） */
const serverReviewMode = ref(false)
/** 当前复核模式激活状态 */
const reviewModeEnabled = ref(false)

function handleReviewModeChange(enabled: boolean) {
  reviewModeEnabled.value = enabled
}

// ---------------------------------------------------------------------------
// Attachment Handlers (Task 17)
// ---------------------------------------------------------------------------

function onAttachmentChange(ids: string[]) {
  pendingAttachmentIds.value = ids
}

function handleInputPaste(event: ClipboardEvent) {
  // 委托给 ChatAttachmentPicker 处理图片粘贴
  attachmentPickerRef.value?.handlePaste(event)
}

// ---------------------------------------------------------------------------
// Note Capture（Task 19: 消息选择、复制与项目笔记转存）
// Validates: Requirements 8.2, 8.5 | Properties: 21
// ---------------------------------------------------------------------------

const noteCapture = useAiNoteCapture({
  messages: () => messages.value,
  host: () => hostRequest.value.host,
})

/** 是否显示选择模式工具条 */
const showSelectionToolbar = computed(() => noteCapture.selectionMode.value)

/** 处理消息点击（选择模式下切换选中） */
function handleMsgClick(msg: ChatMessage) {
  if (noteCapture.selectionMode.value && msg.role === 'assistant' && msg.status === 'completed') {
    noteCapture.toggleMessage(msg.id)
  }
}

/** 是否选中某消息 */
function isSelected(msgId: string): boolean {
  return noteCapture.selectedIds.value.has(msgId)
}

/** 复制选中消息 */
async function handleCopySelected() {
  await noteCapture.copySelected()
}

/** 保存为项目笔记 */
async function handleSaveAsNote() {
  const result = await noteCapture.saveAsNote()
  if (result.success && result.jumpRoute) {
    // 跳转到笔记（使用 router 或 window.open）
    window.open(result.jumpRoute, '_blank')
  } else if (!result.success && result.errorMessage && result.errorMessage !== '已取消保存') {
    ElMessage.error(result.errorMessage)
  }
}

/** 重试保存 */
async function handleRetrySave() {
  const result = await noteCapture.retrySaveAsNote()
  if (result.success && result.jumpRoute) {
    window.open(result.jumpRoute, '_blank')
  } else if (!result.success && result.errorMessage && result.errorMessage !== '已取消保存') {
    ElMessage.error(result.errorMessage)
  }
}

// ---------------------------------------------------------------------------
// Quota & 状态提示（可访问性 live-region）
// ---------------------------------------------------------------------------

import { useChatRunStateStore } from '@/stores/chatRunState'

const runStore = useChatRunStateStore()

// ---------------------------------------------------------------------------
// Context Manifest（Task 15 / Req 5.7, 5.9 / Property 12）
//
// 🔴 面板此前**没有 import ChatContextInspector** —— manifest 在 store 里被
// `context_ready` 存下来了，但没有任何宿主渲染它，用户看不到本轮 AI 到底读了什么。
//
// store 存的是服务端原样的**分组 dict**，组件契约要的是扁平数组，键名也不同
// （status/used_tokens/reason/stale ↔ decision/token_estimate/reason_code/is_stale），
// 所以这里必须投影；组件不动（它有 11 条独立守卫锁着行为）。
// ---------------------------------------------------------------------------

/** 本轮是否已收到 context_ready（收到才渲染检视器，避免空会话摆一个空壳） */
const contextManifestReady = computed(() => !!runStore.contextManifest)
/** 投影后的扁平 manifest（included/trimmed/denied/unavailable 全保留） */
const contextManifestItems = computed(() => normalizeContextManifest(runStore.contextManifest))
/** token 预算总量；服务端未下发时为 0，组件据此不画预算条 */
const contextTokenBudget = computed(() => readContextTokenBudget(runStore.contextManifest))

/** Quota 中文提示（rate_limited 时显示重试倒计时） */
const quotaHint = computed<string>(() => {
  if (phase.value !== 'error') return ''
  if (runStore.errorCode !== 'rate_limited') return ''
  const retry = runStore.retryAfter
  if (retry && retry > 0) {
    return `请求过于频繁，请 ${retry} 秒后再试。`
  }
  return ''
})

/** 输入框状态描述（屏幕阅读器） */
const inputStatusHint = computed<string>(() => {
  if (!hostAvailable.value) return `AI 对话不可用：${scopeHint.value}`
  if (loading.value) return 'AI 正在生成回答中，请等待完成或点击取消。'
  if (quotaHint.value) return quotaHint.value
  return '按 Ctrl+Enter 发送问题。'
})

// ---------------------------------------------------------------------------
// 流式文本节流播报（aria-live 节流，≤3秒更新一次）
// ---------------------------------------------------------------------------

const STREAM_ANNOUNCE_INTERVAL = 3000 // 3 秒
const streamingAnnouncement = ref('')
let streamAnnounceTimer: ReturnType<typeof setTimeout> | null = null
let lastAnnouncedLength = 0

watch(streamingDelta, (text) => {
  if (!text) {
    // 流式结束，清理
    streamingAnnouncement.value = ''
    lastAnnouncedLength = 0
    if (streamAnnounceTimer) {
      clearTimeout(streamAnnounceTimer)
      streamAnnounceTimer = null
    }
    return
  }

  // 首次出现流式文本时立即播报
  if (lastAnnouncedLength === 0 && text.length > 0) {
    streamingAnnouncement.value = 'AI 正在回答中...'
    lastAnnouncedLength = text.length
    scheduleNextAnnouncement()
    return
  }
})

function scheduleNextAnnouncement() {
  if (streamAnnounceTimer) return
  streamAnnounceTimer = setTimeout(() => {
    streamAnnounceTimer = null
    const text = streamingDelta.value
    if (!text) return
    // 播报新增内容的摘要（取最近 80 个字符）
    const newContent = text.slice(lastAnnouncedLength)
    if (newContent.length > 0) {
      const snippet = newContent.length > 80
        ? newContent.slice(0, 80) + '...'
        : newContent
      streamingAnnouncement.value = snippet
      lastAnnouncedLength = text.length
      // 继续调度
      if (text && !runStore.isTerminal) {
        scheduleNextAnnouncement()
      }
    }
  }, STREAM_ANNOUNCE_INTERVAL)
}

// 流式结束时做最终播报
watch(phase, (p) => {
  if (p === 'done' && lastAnnouncedLength > 0) {
    streamingAnnouncement.value = 'AI 回答完成。'
    lastAnnouncedLength = 0
  }
})

// ---------------------------------------------------------------------------
// 可见时拉取历史
// ---------------------------------------------------------------------------

watch(
  () => props.visible,
  (val) => {
    if (val) fetchHistory()
  },
  { immediate: true },
)

// 消息变化自动滚动到底部
watch(
  () => messages.value.length,
  () => {
    nextTick(() => {
      if (messageListRef.value) {
        messageListRef.value.scrollTop = messageListRef.value.scrollHeight
      }
    })
  },
)

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

function handleSend() {
  // 🔴 mention / 附件 / 复核模式**必须随请求体提交** —— 后端 ChatRunRequest 早已声明
  // 这几个字段，此前面板收集完就丢在本地，等于用户选了个空气。
  void sendMessage(undefined, {
    mentions: selectedMentions.value.map((m) => ({ type: m.type, id: m.id })),
    attachmentIds: [...pendingAttachmentIds.value],
    reviewMode: reviewModeEnabled.value,
    sheetName: props.sheetName ?? null,
  })
  // 本轮引用已随请求提交 ⇒ 清空并重建 picker，避免悄悄跟到下一轮
  selectedMentions.value = []
  mentionPickerOpen.value = false
  mentionPickerEpoch.value += 1
}

function handleCancel() {
  cancelRun()
}

function handleKeydown(evt: Event | KeyboardEvent) {
  const e = evt as KeyboardEvent
  // Escape 优先关 mention picker（不冒泡给 DshPanel，否则整个面板会被关掉）
  if (e.key === 'Escape' && mentionPickerOpen.value) {
    e.preventDefault()
    e.stopPropagation()
    mentionPickerOpen.value = false
    return
  }
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault()
    handleSend()
  }
}

async function handleAdopt(msg: ChatMessage) {
  const { success, message } = await adoptContent(msg.id)
  if (success) {
    emit('adopt', { content: msg.text, messageId: msg.id })
    ElMessage.success('已提交采纳，等待确认')
  } else {
    ElMessage.error(message || '采纳提交失败，请稍后重试')
  }
}

// ---------------------------------------------------------------------------
// Markdown 渲染 — 统一走 marked.parse() → useSanitize（DOMPurify）
// Task 10: 不可信内容统一净化
// Validates: Requirements 13.1, 13.2
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): string {
  if (!text) return ''
  const rawHtml = marked.parse(text, { async: false }) as string
  return sanitizeHtml(rawHtml)
}
</script>

<style scoped>
.platform-ai-chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--el-bg-color, #fff);
}

.platform-ai-chat-panel__scope {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-bottom: 1px solid var(--el-border-color-lighter, #e4e7ed);
  flex-shrink: 0;
}

.platform-ai-chat-panel__scope.is-global {
  color: var(--el-color-warning, #e6a23c);
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.platform-ai-chat-panel__hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 消息列表 */
.platform-ai-chat-panel__messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.platform-ai-chat-panel__msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.platform-ai-chat-panel__msg.user {
  flex-direction: row-reverse;
}

.platform-ai-chat-panel__msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  background: var(--el-fill-color-light, #f2f6fc);
}

.platform-ai-chat-panel__msg.assistant .platform-ai-chat-panel__msg-avatar {
  background: rgba(75, 45, 119, 0.1);
}

.platform-ai-chat-panel__msg.user .platform-ai-chat-panel__msg-avatar {
  background: rgba(45, 120, 75, 0.1);
}

.platform-ai-chat-panel__msg-body {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
}

.platform-ai-chat-panel__msg.user .platform-ai-chat-panel__msg-body {
  background: rgba(45, 120, 75, 0.08);
  border-radius: 12px 4px 12px 12px;
}

.platform-ai-chat-panel__msg.assistant .platform-ai-chat-panel__msg-body {
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px 12px 12px 12px;
}

.platform-ai-chat-panel__msg.failed .platform-ai-chat-panel__msg-body {
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger, #f56c6c);
}

.plain-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.markdown-content {
  word-break: break-word;
}

/* 引用来源 */
.platform-ai-chat-panel__citations {
  margin-top: 6px;
  padding-top: 4px;
  border-top: 1px dashed var(--el-border-color-lighter, #ebeef5);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.citation-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.citation-tag {
  background: rgba(75, 45, 119, 0.08);
  color: var(--el-color-primary, #4b2d77);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

/* 采纳按钮 */
.platform-ai-chat-panel__msg-actions {
  margin-top: 6px;
}

/* 错误展示 */
.platform-ai-chat-panel__error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-color-danger-light-9, #fef0f0);
  color: var(--el-color-danger, #f56c6c);
  font-size: 12px;
  flex-shrink: 0;
}

/* Quota 提示 */
.platform-ai-chat-panel__quota {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning-dark-2, #a77730);
  font-size: 12px;
  flex-shrink: 0;
}

/* Context Manifest 检视器容器 */
.platform-ai-chat-panel__context {
  padding: 6px 12px 0;
  flex-shrink: 0;
}

/* 输入区 */
.platform-ai-chat-panel__input {
  position: relative; /* mention picker 以此为定位基准 */
  padding: 10px 12px;
  border-top: 1px solid var(--el-border-color-lighter, #e4e7ed);
  background: var(--el-bg-color, #fff);
  flex-shrink: 0;
}

/* Mention picker 浮层：贴在输入区上沿之上，不遮挡已输入内容 */
.platform-ai-chat-panel__mention-layer {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 4px);
  z-index: 10;
}

/* 已选引用 tag 行 */
.platform-ai-chat-panel__mention-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.platform-ai-chat-panel__input-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

/* Streaming 动画 */
.platform-ai-chat-panel__msg.streaming .platform-ai-chat-panel__msg-body::after {
  content: '▌';
  animation: blink-cursor 1s infinite;
}

@keyframes blink-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* reduced-motion：禁用闪烁光标和流式动画 */
@media (prefers-reduced-motion: reduce) {
  .platform-ai-chat-panel__msg.streaming .platform-ai-chat-panel__msg-body::after {
    animation: none;
    content: '|'; /* 静态光标代替闪烁 */
  }
}

/* Markdown 内部样式 */
.markdown-content :deep(pre) {
  background: var(--el-fill-color-lighter, #f5f7fa);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}

.markdown-content :deep(code) {
  background: var(--el-fill-color-light, #f2f6fc);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

/* 选择模式入口按钮 */
.platform-ai-chat-panel__select-btn {
  margin-left: auto;
  flex-shrink: 0;
}

/* 选择模式工具条 */
.platform-ai-chat-panel__selection-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-bottom: 1px solid var(--el-color-primary-light-7, #c6e2ff);
  flex-shrink: 0;
}

.platform-ai-chat-panel__selection-count {
  font-size: 12px;
  color: var(--el-color-primary, #409eff);
  font-weight: 500;
  margin-right: 4px;
}

/* 保存失败重试提示条 */
.platform-ai-chat-panel__retry-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--el-color-danger-light-9, #fef0f0);
  border-bottom: 1px solid var(--el-color-danger-light-7, #fbc4c4);
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
  flex-shrink: 0;
}

.platform-ai-chat-panel__retry-bar span {
  flex: 1;
}

/* 选择模式下的消息样式 */
.platform-ai-chat-panel__msg.is-selectable {
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.15s;
}

.platform-ai-chat-panel__msg.is-selectable:hover {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.platform-ai-chat-panel__msg.is-selected {
  background: var(--el-color-primary-light-8, #d9ecff);
  border-radius: 6px;
}

.platform-ai-chat-panel__msg.is-selected:hover {
  background: var(--el-color-primary-light-7, #c6e2ff);
}

/* 选中指示器 */
.platform-ai-chat-panel__msg-check {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  align-self: center;
}

.platform-ai-chat-panel__msg-check-empty {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--el-border-color, #dcdfe6);
  border-radius: 3px;
}

.platform-ai-chat-panel__msg.is-selected .platform-ai-chat-panel__msg-check-empty {
  border-color: var(--el-color-primary, #409eff);
  background: var(--el-color-primary, #409eff);
}
</style>
