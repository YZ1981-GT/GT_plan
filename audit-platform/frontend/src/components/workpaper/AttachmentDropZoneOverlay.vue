<template>
  <Teleport to="body">
    <Transition name="gt-fade">
      <div
        v-if="visible"
        class="gt-attachment-overlay"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <div class="gt-attachment-overlay-card">
          <div class="gt-attachment-overlay-icon">📎</div>
          <div class="gt-attachment-overlay-title">释放文件以上传附件</div>
          <div class="gt-attachment-overlay-subtitle">
            将关联到当前底稿
            <span v-if="props.sheetName" class="gt-attachment-overlay-sheet">
              · {{ props.sheetName }}
            </span>
          </div>
          <div class="gt-attachment-overlay-hint">
            支持：JPG / PNG / GIF / PDF / Word / Excel · 最大 20 MB
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="gt-fade">
      <div v-if="uploading" class="gt-attachment-overlay-uploading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在上传 {{ uploadingCurrent }}/{{ uploadingTotal }}</span>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { uploadAttachment } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'

interface AttachmentUploadedPayload {
  attachment_id: string
  file_name: string
  wp_id: string
  sheet_name: string | null
}

const props = defineProps<{
  /** 监听拖拽事件的容器元素 ref（通常为 WorkpaperEditor 根 div） */
  containerEl: HTMLElement | null
  /** 当前项目 ID */
  projectId: string
  /** 当前底稿 ID */
  wpId: string
  /** 当前激活 sheet 名（关联元数据） */
  sheetName?: string
  /** 是否禁用（如 wpId 未就绪时） */
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'uploaded', payload: AttachmentUploadedPayload): void
  (e: 'error', message: string): void
}>()

// ─── 上传约束 ───
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB
const ALLOWED_EXTENSIONS = [
  '.jpg', '.jpeg', '.png', '.gif', '.webp',
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt',
]

// ─── overlay 显隐状态（dragCounter 处理嵌套元素 dragleave 闪烁）───
const visible = ref(false)
const uploading = ref(false)
const uploadingCurrent = ref(0)
const uploadingTotal = ref(0)
let dragCounter = 0

// ─── 拖拽事件处理 ───
function onDragEnter(e: DragEvent) {
  if (props.disabled) return
  if (!hasFiles(e)) return
  dragCounter += 1
  visible.value = true
}

function onDragLeave(e: DragEvent) {
  if (props.disabled) return
  if (!hasFiles(e)) return
  dragCounter = Math.max(0, dragCounter - 1)
  if (dragCounter === 0) {
    visible.value = false
  }
}

function onDragOver(e: DragEvent) {
  if (props.disabled) return
  if (!hasFiles(e)) return
  // 必须 preventDefault 否则 drop 不会触发
  e.preventDefault()
}

async function onDrop(e: DragEvent) {
  visible.value = false
  dragCounter = 0
  if (props.disabled) return
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
}

// ─── 工具 ───
function hasFiles(e: DragEvent): boolean {
  const types = e.dataTransfer?.types
  if (!types) return false
  // types 在不同浏览器为 DOMStringList 或 string[]
  for (let i = 0; i < types.length; i += 1) {
    if (types[i] === 'Files') return true
  }
  return false
}

function getExt(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

function validateFile(file: File): string | null {
  const ext = getExt(file.name)
  if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
    return `不支持的文件类型: ${file.name}`
  }
  if (file.size > MAX_FILE_SIZE) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    return `文件 "${file.name}" 大小 ${sizeMB}MB 超过 20MB 上限`
  }
  return null
}

// ─── 上传 + 关联 ───
async function uploadFiles(files: File[]) {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('当前底稿未就绪，无法上传附件')
    emit('error', 'wp_id 或 project_id 未就绪')
    return
  }

  uploading.value = true
  uploadingTotal.value = files.length
  uploadingCurrent.value = 0
  const successList: AttachmentUploadedPayload[] = []
  const errorList: string[] = []

  for (let i = 0; i < files.length; i += 1) {
    const file = files[i]
    uploadingCurrent.value = i + 1
    const validationError = validateFile(file)
    if (validationError) {
      errorList.push(validationError)
      continue
    }

    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('attachment_type', 'evidence')
      fd.append('reference_type', 'workpaper')
      fd.append('reference_id', props.wpId)
      // metadata 透传到后端 metadata.title / 落到 paperless 元数据
      const sheetTag = props.sheetName ? ` [${props.sheetName}]` : ''
      fd.append('title', `${file.name}${sheetTag}`)

      const uploadResp = await uploadAttachment(props.projectId, fd)
      const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
      if (!attachmentId) {
        throw new Error('上传响应缺少 attachment_id')
      }

      // 创建底稿关联（notes 携带 sheet_name 元数据）
      const sheetName = props.sheetName || ''
      const notes = sheetName ? `sheet:${sheetName}` : null
      try {
        await httpApi.post(P_att.associate(attachmentId), {
          wp_id: props.wpId,
          association_type: 'evidence',
          notes,
        })
      } catch (associateErr: any) {
        // 关联失败不阻断主流程：附件已上传，仅记录错误
        const detail = associateErr?.response?.data?.detail || associateErr?.message || '关联失败'
        errorList.push(`附件 ${file.name} 已上传但关联失败: ${detail}`)
      }

      successList.push({
        attachment_id: attachmentId,
        file_name: file.name,
        wp_id: props.wpId,
        sheet_name: sheetName || null,
      })
      emit('uploaded', successList[successList.length - 1])
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '上传失败'
      errorList.push(`${file.name}: ${detail}`)
    }
  }

  uploading.value = false
  uploadingCurrent.value = 0
  uploadingTotal.value = 0

  // 友好提示
  if (successList.length > 0 && errorList.length === 0) {
    const sheetTag = props.sheetName ? `（${props.sheetName}）` : ''
    ElMessage.success(`成功上传 ${successList.length} 个附件并关联到当前底稿${sheetTag}`)
  } else if (successList.length > 0 && errorList.length > 0) {
    ElMessage.warning(`部分成功：${successList.length} 个上传成功，${errorList.length} 个失败`)
    errorList.forEach((m) => emit('error', m))
  } else if (errorList.length > 0) {
    ElMessage.error(`附件上传失败：${errorList[0]}`)
    errorList.forEach((m) => emit('error', m))
  }
}

// ─── 容器事件挂载/卸载 ───
let attachedEl: HTMLElement | null = null

function attachListeners(el: HTMLElement) {
  el.addEventListener('dragenter', onDragEnter)
  el.addEventListener('dragleave', onDragLeave)
  el.addEventListener('dragover', onDragOver)
  el.addEventListener('drop', onDrop)
  attachedEl = el
}

function detachListeners() {
  if (!attachedEl) return
  attachedEl.removeEventListener('dragenter', onDragEnter)
  attachedEl.removeEventListener('dragleave', onDragLeave)
  attachedEl.removeEventListener('dragover', onDragOver)
  attachedEl.removeEventListener('drop', onDrop)
  attachedEl = null
}

watch(
  () => props.containerEl,
  (next, prev) => {
    if (prev && prev === attachedEl) {
      detachListeners()
    }
    if (next) {
      attachListeners(next)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  detachListeners()
  visible.value = false
  dragCounter = 0
})

// 测试钩子（仅用于单测，prod 无副作用）
defineExpose({
  _uploadFiles: uploadFiles,
  _onDragEnter: onDragEnter,
  _onDragLeave: onDragLeave,
  _onDrop: onDrop,
})
</script>

<style scoped>
.gt-attachment-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(64, 158, 255, 0.12);
  backdrop-filter: blur(2px);
  pointer-events: auto;
}

.gt-attachment-overlay-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 56px;
  background: var(--gt-color-bg-white, #fff);
  border: 2px dashed var(--el-color-primary, #409eff);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  pointer-events: none;
}

.gt-attachment-overlay-icon {
  font-size: 40px /* allow-px: special */;
  margin-bottom: 4px;
}

.gt-attachment-overlay-title {
  font-size: var(--gt-font-size-lg);
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
}

.gt-attachment-overlay-subtitle {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
}

.gt-attachment-overlay-sheet {
  margin-left: 4px;
  color: var(--gt-color-text-secondary);
  font-weight: 500;
}

.gt-attachment-overlay-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-top: 4px;
}

.gt-attachment-overlay-uploading {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 3001;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  font-size: var(--gt-font-size-sm);
  color: var(--el-color-primary, #409eff);
}

.gt-fade-enter-active,
.gt-fade-leave-active {
  transition: opacity 0.18s ease;
}
.gt-fade-enter-from,
.gt-fade-leave-to {
  opacity: 0;
}
</style>
