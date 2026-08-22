<template>
  <div
    class="chat-attachment-picker"
    :class="{ 'chat-attachment-picker--drag-over': isDragOver }"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!-- 拖拽遮罩 -->
    <div v-if="isDragOver" class="chat-attachment-picker__drop-overlay" aria-hidden="true">
      <el-icon :size="28"><Upload /></el-icon>
      <span>拖放文件到此处上传</span>
    </div>

    <!-- 已选附件列表 -->
    <div v-if="attachments.length > 0" class="chat-attachment-picker__list" role="list" aria-label="已添加附件">
      <div
        v-for="att in attachments"
        :key="att.id"
        class="chat-attachment-picker__item"
        :class="[`is-${att.status}`]"
        role="listitem"
        :aria-label="attachmentAriaLabel(att)"
      >
        <!-- 文件图标 -->
        <div class="chat-attachment-picker__item-icon" aria-hidden="true">
          <el-icon v-if="att.status === 'uploading'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="att.status === 'ocr_running'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="att.status === 'succeeded'"><Document /></el-icon>
          <el-icon v-else-if="att.status === 'empty'"><DocumentRemove /></el-icon>
          <el-icon v-else-if="att.status === 'failed'"><CircleCloseFilled /></el-icon>
          <el-icon v-else-if="att.status === 'cancelled'"><CircleCloseFilled /></el-icon>
          <el-icon v-else><Document /></el-icon>
        </div>

        <!-- 文件信息 -->
        <div class="chat-attachment-picker__item-info">
          <span class="chat-attachment-picker__item-name" :title="att.originalName">
            {{ att.originalName }}
          </span>
          <span class="chat-attachment-picker__item-status">
            {{ statusLabel(att.status) }}
          </span>
        </div>

        <!-- 上传进度条 -->
        <el-progress
          v-if="att.status === 'uploading' && att.progress != null"
          :percentage="att.progress"
          :stroke-width="3"
          :show-text="false"
          class="chat-attachment-picker__item-progress"
        />

        <!-- OCR 原文展开 -->
        <div v-if="att.status === 'succeeded' && att.ocrText" class="chat-attachment-picker__ocr">
          <el-button
            text
            size="small"
            type="primary"
            :aria-expanded="att.ocrExpanded ? 'true' : 'false'"
            aria-controls="ocr-text-content"
            @click="toggleOcrExpand(att)"
          >
            {{ att.ocrExpanded ? '收起 OCR 原文' : '展开 OCR 原文' }}
          </el-button>
          <div
            v-if="att.ocrExpanded"
            id="ocr-text-content"
            class="chat-attachment-picker__ocr-content"
            v-html="sanitizedOcrText(att.ocrText)"
          />
        </div>

        <!-- 空文本提示：允许补充说明 -->
        <div v-if="att.status === 'empty'" class="chat-attachment-picker__empty-hint">
          <span class="chat-attachment-picker__empty-msg">未识别到文字内容</span>
          <el-input
            v-model="att.userNote"
            type="textarea"
            :rows="2"
            placeholder="可补充说明此附件内容..."
            size="small"
            :aria-label="`为附件 ${att.originalName} 补充说明`"
          />
        </div>

        <!-- 失败态：重试 -->
        <div v-if="att.status === 'failed'" class="chat-attachment-picker__retry">
          <span class="chat-attachment-picker__error-msg">{{ att.errorMessage || '上传或识别失败' }}</span>
          <el-button size="small" type="warning" plain @click="retryUpload(att)">重试</el-button>
        </div>

        <!-- 操作按钮：取消/删除 -->
        <div class="chat-attachment-picker__item-actions">
          <el-button
            v-if="att.status === 'uploading'"
            text
            size="small"
            type="danger"
            :aria-label="`取消上传 ${att.originalName}`"
            @click="cancelUpload(att)"
          >
            取消
          </el-button>
          <el-button
            v-else
            text
            size="small"
            type="danger"
            :aria-label="`删除附件 ${att.originalName}`"
            @click="removeAttachment(att)"
          >
            删除
          </el-button>
        </div>

        <!-- 清理状态标识 -->
        <div v-if="att.cleanupStatus" class="chat-attachment-picker__cleanup" role="status">
          <span v-if="att.cleanupStatus === 'cleaning'" class="is-cleaning">
            <el-icon class="is-loading"><Loading /></el-icon>
            清理中...
          </span>
          <span v-else-if="att.cleanupStatus === 'failed'" class="is-cleanup-failed">
            清理失败
            <el-button text size="small" type="warning" @click="retryCleanup(att)">重试</el-button>
          </span>
        </div>
      </div>
    </div>

    <!-- 上传按钮 -->
    <div class="chat-attachment-picker__trigger">
      <input
        ref="fileInputRef"
        type="file"
        :accept="ACCEPT_TYPES"
        multiple
        class="chat-attachment-picker__file-input"
        aria-hidden="true"
        tabindex="-1"
        @change="onFileInputChange"
      />
      <el-button
        text
        size="small"
        type="primary"
        :disabled="disabled"
        aria-label="添加附件（支持拖拽或粘贴图片）"
        @click="triggerFilePicker"
      >
        <el-icon><Paperclip /></el-icon>
        附件
      </el-button>
      <span v-if="attachments.length > 0" class="chat-attachment-picker__count">
        {{ attachments.length }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ChatAttachmentPicker — AI 对话附件选择与 OCR 状态组件
 *
 * 支持：按钮上传、拖拽、剪贴板粘贴图片、上传进度、取消与重试
 * OCR 状态展示：uploaded/ocr_running/succeeded/empty/failed/cancelled
 * OCR 文本使用 marked + sanitizeHtml 统一净化路径
 * 仅提交 attachment IDs 到 run，不含文件正文
 *
 * Feature: dsh-agent-panel-integration / Task 17
 * Validates: Requirements 7.1, 7.6, 7.7, 7.9
 * Properties: 19, 20, 34
 */
import { ref, watch, onBeforeUnmount, type PropType } from 'vue'
import {
  Upload,
  Loading,
  Document,
  DocumentRemove,
  CircleCloseFilled,
  Paperclip,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { sanitizeHtml } from '@/composables/useSanitize'
import { useAuthStore } from '@/stores/auth'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AttachmentStatus =
  | 'uploading'
  | 'uploaded'
  | 'ocr_running'
  | 'succeeded'
  | 'empty'
  | 'failed'
  | 'cancelled'

export type CleanupStatus = 'cleaning' | 'failed' | null

export interface ChatAttachment {
  /** 本地临时 ID（上传前为随机值，上传成功后为服务端返回 ID） */
  id: string
  /** 原始文件名 */
  originalName: string
  /** 附件状态 */
  status: AttachmentStatus
  /** 上传进度 0-100 */
  progress?: number
  /** OCR 识别原文 */
  ocrText?: string
  /** OCR 展开状态 */
  ocrExpanded?: boolean
  /** 用户补充说明（空文本时） */
  userNote?: string
  /** 错误信息 */
  errorMessage?: string
  /** 清理状态 */
  cleanupStatus?: CleanupStatus
  /** 原始 File 对象（用于重试） */
  _file?: File
  /** 上传 AbortController（用于取消） */
  _abortController?: AbortController
}

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps({
  /** 是否禁用上传 */
  disabled: { type: Boolean, default: false },
  /** 最大附件数 */
  maxCount: { type: Number, default: 5 },
  /** 单文件最大体积（字节） */
  maxSizeBytes: { type: Number, default: 20 * 1024 * 1024 },
})

const emit = defineEmits<{
  /** 附件列表变化（提交给 run 时只取 IDs） */
  (e: 'change', attachmentIds: string[]): void
}>()

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACCEPT_TYPES = '.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff'

const STATUS_LABELS: Record<AttachmentStatus, string> = {
  uploading: '上传中...',
  uploaded: '已上传，等待识别',
  ocr_running: 'OCR 识别中...',
  succeeded: 'OCR 识别完成',
  empty: '未识别到文字',
  failed: '失败',
  cancelled: '已取消',
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const attachments = ref<ChatAttachment[]>([])
const isDragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// OCR 轮询定时器
let ocrPollTimers: Map<string, ReturnType<typeof setInterval>> = new Map()

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function getToken(): string {
  try {
    return useAuthStore().token || ''
  } catch {
    return ''
  }
}

// ---------------------------------------------------------------------------
// 上传
// ---------------------------------------------------------------------------

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function onFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) {
    handleFiles(Array.from(input.files))
  }
  // 重置 input 以便选择相同文件
  input.value = ''
}

/** 剪贴板粘贴监听（由父组件通过 ref 调用，或可绑定到输入区） */
function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items
  if (!items) return
  const files: File[] = []
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (files.length > 0) {
    event.preventDefault()
    handleFiles(files)
  }
}

function handleFiles(files: File[]) {
  if (props.disabled) return

  // 数量检查
  const remaining = props.maxCount - attachments.value.length
  if (remaining <= 0) {
    ElMessage.warning(`最多可添加 ${props.maxCount} 个附件`)
    return
  }
  const toProcess = files.slice(0, remaining)
  if (toProcess.length < files.length) {
    ElMessage.warning(`已达附件上限，仅添加前 ${toProcess.length} 个文件`)
  }

  for (const file of toProcess) {
    // 大小检查
    if (file.size > props.maxSizeBytes) {
      ElMessage.error(`文件 ${file.name} 超过 ${Math.round(props.maxSizeBytes / 1024 / 1024)}MB 限制`)
      continue
    }
    uploadFile(file)
  }
}

async function uploadFile(file: File) {
  const tempId = `tmp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  const abortController = new AbortController()

  const att: ChatAttachment = {
    id: tempId,
    originalName: file.name || `粘贴图片_${new Date().toLocaleTimeString()}`,
    status: 'uploading',
    progress: 0,
    _file: file,
    _abortController: abortController,
  }
  attachments.value.push(att)

  try {
    const formData = new FormData()
    formData.append('file', file)

    const xhr = new XMLHttpRequest()
    const uploadPromise = new Promise<any>((resolve, reject) => {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const target = attachments.value.find(a => a.id === tempId)
          if (target) target.progress = Math.round((e.loaded / e.total) * 100)
        }
      })

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const body = JSON.parse(xhr.responseText)
            resolve(body?.data ?? body)
          } catch {
            resolve({})
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}`))
        }
      })

      xhr.addEventListener('error', () => reject(new Error('网络错误')))
      xhr.addEventListener('abort', () => reject(new Error('cancelled')))

      // 绑定 abort
      abortController.signal.addEventListener('abort', () => xhr.abort())

      xhr.open('POST', '/api/ai-chat/attachments')
      xhr.setRequestHeader('Authorization', `Bearer ${getToken()}`)
      xhr.send(formData)
    })

    const data = await uploadPromise
    const target = attachments.value.find(a => a.id === tempId)
    if (!target) return

    // 更新为服务端 ID
    const serverId = data.attachment_id || data.id || tempId
    target.id = serverId
    target.status = data.ocr_status || data.status || 'uploaded'
    target.progress = undefined
    target._abortController = undefined

    // 如果已完成 OCR
    if (target.status === 'succeeded') {
      target.ocrText = data.ocr_text || undefined
    } else if (target.status === 'empty') {
      // empty 状态保持
    } else if (target.status === 'failed') {
      target.errorMessage = data.error_message || data.error_code || '识别失败'
    } else if (target.status === 'uploaded' || target.status === 'ocr_running') {
      // 开始轮询 OCR 状态
      startOcrPolling(target)
    }

    emitChange()
  } catch (err: any) {
    const target = attachments.value.find(a => a.id === tempId)
    if (!target) return

    if (err?.message === 'cancelled') {
      target.status = 'cancelled'
      target.progress = undefined
    } else {
      target.status = 'failed'
      target.errorMessage = err?.message || '上传失败'
      target.progress = undefined
    }
    target._abortController = undefined
  }
}

// ---------------------------------------------------------------------------
// OCR 轮询
// ---------------------------------------------------------------------------

function startOcrPolling(att: ChatAttachment) {
  if (ocrPollTimers.has(att.id)) return

  att.status = 'ocr_running'
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/ai-chat/attachments/${att.id}/status`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      if (!res.ok) return

      const body = await res.json()
      const data = body?.data ?? body
      const newStatus = data.ocr_status || data.status

      if (newStatus === 'succeeded') {
        att.status = 'succeeded'
        att.ocrText = data.ocr_text || undefined
        stopOcrPolling(att.id)
        emitChange()
      } else if (newStatus === 'empty') {
        att.status = 'empty'
        stopOcrPolling(att.id)
        emitChange()
      } else if (newStatus === 'failed') {
        att.status = 'failed'
        att.errorMessage = data.error_message || data.error_code || 'OCR 识别失败'
        stopOcrPolling(att.id)
      } else if (newStatus === 'cancelled') {
        att.status = 'cancelled'
        stopOcrPolling(att.id)
      }
      // ocr_running/uploaded 继续轮询
    } catch {
      // 网络错误静默重试
    }
  }, 2000)

  ocrPollTimers.set(att.id, timer)
}

function stopOcrPolling(id: string) {
  const timer = ocrPollTimers.get(id)
  if (timer) {
    clearInterval(timer)
    ocrPollTimers.delete(id)
  }
}

// ---------------------------------------------------------------------------
// 取消 & 重试
// ---------------------------------------------------------------------------

function cancelUpload(att: ChatAttachment) {
  att._abortController?.abort()
  att.status = 'cancelled'
  att.progress = undefined
  att._abortController = undefined
}

function retryUpload(att: ChatAttachment) {
  if (!att._file) {
    ElMessage.warning('原文件引用已丢失，请重新选择文件')
    return
  }
  // 移除旧项并重新上传
  const idx = attachments.value.findIndex(a => a.id === att.id)
  if (idx >= 0) attachments.value.splice(idx, 1)
  uploadFile(att._file)
}

// ---------------------------------------------------------------------------
// 删除 & 清理
// ---------------------------------------------------------------------------

async function removeAttachment(att: ChatAttachment) {
  // 非服务端 ID 直接本地移除
  if (att.id.startsWith('tmp_')) {
    attachments.value = attachments.value.filter(a => a.id !== att.id)
    emitChange()
    return
  }

  // 调用后端删除 API
  att.cleanupStatus = 'cleaning'
  try {
    const res = await fetch(`/api/ai-chat/attachments/${att.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (res.ok || res.status === 404) {
      // 成功删除
      attachments.value = attachments.value.filter(a => a.id !== att.id)
      emitChange()
    } else {
      // 失败保留 metadata 可重试（Property 20）
      att.cleanupStatus = 'failed'
      ElMessage.error('附件清理失败，可重试')
    }
  } catch {
    att.cleanupStatus = 'failed'
    ElMessage.error('附件清理失败，请检查网络后重试')
  }
}

function retryCleanup(att: ChatAttachment) {
  att.cleanupStatus = null
  removeAttachment(att)
}

/** 清空全部附件（session 清除时调用） */
async function clearAll() {
  const toClean = attachments.value.filter(a => !a.id.startsWith('tmp_'))
  // 停止所有轮询
  for (const [id] of ocrPollTimers) stopOcrPolling(id)

  // 并行清理
  const results = await Promise.allSettled(
    toClean.map(async (att) => {
      att.cleanupStatus = 'cleaning'
      try {
        const res = await fetch(`/api/ai-chat/attachments/${att.id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${getToken()}` },
        })
        if (res.ok || res.status === 404) {
          return { id: att.id, success: true }
        }
        att.cleanupStatus = 'failed'
        return { id: att.id, success: false }
      } catch {
        att.cleanupStatus = 'failed'
        return { id: att.id, success: false }
      }
    }),
  )

  // 移除成功的
  const successIds = results
    .filter((r): r is PromiseFulfilledResult<{ id: string; success: boolean }> => r.status === 'fulfilled')
    .filter(r => r.value.success)
    .map(r => r.value.id)

  attachments.value = attachments.value.filter(
    a => a.id.startsWith('tmp_') || !successIds.includes(a.id),
  )

  // 如果有失败项，不假报成功
  const failedCount = toClean.length - successIds.length
  if (failedCount > 0) {
    ElMessage.warning(`${successIds.length} 个附件已清理，${failedCount} 个清理失败可重试`)
  } else if (successIds.length > 0) {
    // 全部成功，移除本地临时项
    attachments.value = []
  } else {
    attachments.value = []
  }
  emitChange()
}

// ---------------------------------------------------------------------------
// Drag & Drop
// ---------------------------------------------------------------------------

function onDragOver(event: DragEvent) {
  if (props.disabled) return
  isDragOver.value = true
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(event: DragEvent) {
  isDragOver.value = false
  if (props.disabled) return
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    handleFiles(Array.from(files))
  }
}

// ---------------------------------------------------------------------------
// OCR 文本净化（Property 34）
// ---------------------------------------------------------------------------

function sanitizedOcrText(raw: string): string {
  if (!raw) return ''
  // OCR 文本按 markdown 渲染并统一净化（与 PlatformAiChatPanel 同一路径）
  const html = marked.parse(raw, { async: false }) as string
  return sanitizeHtml(html)
}

// ---------------------------------------------------------------------------
// 辅助
// ---------------------------------------------------------------------------

function statusLabel(status: AttachmentStatus): string {
  return STATUS_LABELS[status] || status
}

function attachmentAriaLabel(att: ChatAttachment): string {
  return `附件 ${att.originalName}，状态：${statusLabel(att.status)}`
}

function toggleOcrExpand(att: ChatAttachment) {
  att.ocrExpanded = !att.ocrExpanded
}

function emitChange() {
  // 仅提交已成功上传到服务端的 attachment IDs
  const ids = attachments.value
    .filter(a => !a.id.startsWith('tmp_') && (a.status === 'succeeded' || a.status === 'uploaded' || a.status === 'ocr_running' || a.status === 'empty'))
    .map(a => a.id)
  emit('change', ids)
}

/** 获取可提交的附件 ID 列表 */
function getSubmittableIds(): string[] {
  return attachments.value
    .filter(a => !a.id.startsWith('tmp_') && (a.status === 'succeeded' || a.status === 'uploaded' || a.status === 'ocr_running' || a.status === 'empty'))
    .map(a => a.id)
}

/** 是否有正在上传/识别的附件 */
function hasPending(): boolean {
  return attachments.value.some(a => a.status === 'uploading' || a.status === 'ocr_running')
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onBeforeUnmount(() => {
  // 清理所有 OCR 轮询
  for (const [id] of ocrPollTimers) stopOcrPolling(id)
  // 终止进行中的上传
  for (const att of attachments.value) {
    if (att._abortController) att._abortController.abort()
  }
})

// ---------------------------------------------------------------------------
// Expose
// ---------------------------------------------------------------------------

defineExpose({
  handlePaste,
  clearAll,
  getSubmittableIds,
  hasPending,
  attachments,
})
</script>

<style scoped>
.chat-attachment-picker {
  position: relative;
  width: 100%;
}

.chat-attachment-picker--drag-over {
  outline: 2px dashed var(--el-color-primary, #4b2d77);
  outline-offset: -2px;
  border-radius: 4px;
}

/* 拖拽遮罩 */
.chat-attachment-picker__drop-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: rgba(75, 45, 119, 0.06);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-color-primary, #4b2d77);
  z-index: 10;
  pointer-events: none;
}

/* 附件列表 */
.chat-attachment-picker__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 0;
  max-height: 200px;
  overflow-y: auto;
}

.chat-attachment-picker__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  font-size: 12px;
  transition: background 0.2s;
}

.chat-attachment-picker__item.is-uploading {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.chat-attachment-picker__item.is-succeeded {
  background: var(--el-color-success-light-9, #f0f9eb);
}

.chat-attachment-picker__item.is-empty {
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.chat-attachment-picker__item.is-failed,
.chat-attachment-picker__item.is-cancelled {
  background: var(--el-color-danger-light-9, #fef0f0);
}

.chat-attachment-picker__item-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.chat-attachment-picker__item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-attachment-picker__item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.chat-attachment-picker__item-status {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
}

.chat-attachment-picker__item-progress {
  width: 100%;
  flex-basis: 100%;
}

/* OCR 原文 */
.chat-attachment-picker__ocr {
  width: 100%;
  flex-basis: 100%;
  margin-top: 4px;
}

.chat-attachment-picker__ocr-content {
  margin-top: 4px;
  padding: 8px;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 150px;
  overflow-y: auto;
  word-break: break-word;
}

/* 空文本提示 */
.chat-attachment-picker__empty-hint {
  width: 100%;
  flex-basis: 100%;
  margin-top: 4px;
}

.chat-attachment-picker__empty-msg {
  display: block;
  font-size: 11px;
  color: var(--el-color-warning-dark-2, #a77730);
  margin-bottom: 4px;
}

/* 失败重试 */
.chat-attachment-picker__retry {
  width: 100%;
  flex-basis: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.chat-attachment-picker__error-msg {
  font-size: 11px;
  color: var(--el-color-danger, #f56c6c);
  flex: 1;
}

/* 操作按钮 */
.chat-attachment-picker__item-actions {
  flex-shrink: 0;
}

/* 清理状态 */
.chat-attachment-picker__cleanup {
  width: 100%;
  flex-basis: 100%;
  margin-top: 2px;
  font-size: 11px;
}

.chat-attachment-picker__cleanup .is-cleaning {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary, #909399);
}

.chat-attachment-picker__cleanup .is-cleanup-failed {
  color: var(--el-color-warning, #e6a23c);
}

/* 触发按钮 */
.chat-attachment-picker__trigger {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-attachment-picker__file-input {
  display: none;
}

.chat-attachment-picker__count {
  font-size: 11px;
  background: var(--el-color-primary-light-9, #ecf5ff);
  color: var(--el-color-primary, #4b2d77);
  padding: 0 5px;
  border-radius: 8px;
  line-height: 16px;
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .chat-attachment-picker__item {
    transition: none;
  }
}
</style>
