<template>
  <div
    class="gt-attachment-dropzone"
    :class="{ 'gt-attachment-dropzone--active': isDragOver }"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!-- 拖拽覆盖层提示 -->
    <Transition name="gt-fade">
      <div v-if="isDragOver" class="gt-attachment-dropzone-overlay">
        <div class="gt-attachment-dropzone-overlay-content">
          <span class="gt-attachment-dropzone-icon">📎</span>
          <span class="gt-attachment-dropzone-text">释放文件以上传并关联到当前单元格</span>
          <span class="gt-attachment-dropzone-hint">
            支持：图片(JPG/PNG/GIF)、PDF、Word | 最大 20MB
          </span>
        </div>
      </div>
    </Transition>

    <!-- 上传进度提示 -->
    <Transition name="gt-fade">
      <div v-if="uploading" class="gt-attachment-dropzone-uploading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在上传附件...</span>
      </div>
    </Transition>

    <!-- 默认插槽：包裹 Univer 容器 -->
    <slot />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { uploadAttachment } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'

export interface AttachmentLinkResult {
  attachment_id: string
  wp_id: string
  cell_ref: string | null
  association_type: string
}

const props = defineProps<{
  projectId: string
  wpId: string
  /** 当前选中的单元格引用（如 "B5"），用于关联 */
  currentCellRef?: string | null
}>()

const emit = defineEmits<{
  /** 附件关联成功后触发，用于 WorkpaperEditor 渲染 📎 装饰 */
  (e: 'link-created', payload: AttachmentLinkResult): void
  /** 上传失败 */
  (e: 'upload-error', error: string): void
}>()

// ─── 常量 ───
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB
const ALLOWED_MIME_TYPES = [
  'image/jpeg',
  'image/png',
  'image/gif',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx']

// ─── 状态 ───
const isDragOver = ref(false)
const uploading = ref(false)
let dragLeaveTimer: ReturnType<typeof setTimeout> | null = null

// ─── 拖拽事件处理 ───
function onDragOver(e: DragEvent) {
  // 检查是否包含文件
  if (!e.dataTransfer?.types?.includes('Files')) return
  isDragOver.value = true
  if (dragLeaveTimer) {
    clearTimeout(dragLeaveTimer)
    dragLeaveTimer = null
  }
}

function onDragLeave(_e: DragEvent) {
  // 使用延时避免子元素触发 dragleave 导致闪烁
  dragLeaveTimer = setTimeout(() => {
    isDragOver.value = false
  }, 100)
}

async function onDrop(e: DragEvent) {
  isDragOver.value = false
  if (dragLeaveTimer) {
    clearTimeout(dragLeaveTimer)
    dragLeaveTimer = null
  }

  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  // 逐个处理文件
  for (let i = 0; i < files.length; i++) {
    await processFile(files[i])
  }
}

// ─── 文件处理 ───
async function processFile(file: File) {
  // 1. 类型白名单校验
  if (!validateFileType(file)) {
    ElMessage.warning({
      message: `文件 "${file.name}" 类型不允许。支持：JPG/PNG/GIF/PDF/Word`,
      duration: 4000,
    })
    emit('upload-error', `文件类型不允许: ${file.name}`)
    return
  }

  // 2. 大小校验
  if (file.size > MAX_FILE_SIZE) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    ElMessage.warning({
      message: `文件 "${file.name}" 大小 ${sizeMB}MB 超过 20MB 上限`,
      duration: 4000,
    })
    emit('upload-error', `文件大小超限: ${file.name} (${sizeMB}MB)`)
    return
  }

  // 3. 上传
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('attachment_type', 'evidence')
    formData.append('reference_type', 'workpaper')

    const uploadResult = await uploadAttachment(props.projectId, formData)
    const attachmentId = uploadResult?.id || uploadResult?.attachment_id

    if (!attachmentId) {
      throw new Error('上传返回无效的附件 ID')
    }

    // 4. 创建关联（workpaper_attachment_link）
    await createAttachmentLink(attachmentId)

    ElMessage.success({
      message: `附件 "${file.name}" 已上传并关联到底稿${props.currentCellRef ? ` (${props.currentCellRef})` : ''}`,
      duration: 3000,
    })
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '上传失败'
    ElMessage.error(`附件上传失败: ${msg}`)
    emit('upload-error', msg)
  } finally {
    uploading.value = false
  }
}

/** 创建附件与底稿的关联 */
async function createAttachmentLink(attachmentId: string) {
  const cellRef = props.currentCellRef || null
  const notes = cellRef ? `cell_ref:${cellRef}` : null

  const result = await httpApi.post(
    P_att.associate(attachmentId),
    {
      wp_id: props.wpId,
      association_type: 'evidence',
      notes,
    },
  )

  emit('link-created', {
    attachment_id: attachmentId,
    wp_id: props.wpId,
    cell_ref: cellRef,
    association_type: 'evidence',
  })

  return result
}

/** 校验文件类型（MIME + 扩展名双重校验） */
function validateFileType(file: File): boolean {
  // MIME 类型校验
  if (file.type && ALLOWED_MIME_TYPES.includes(file.type)) {
    return true
  }

  // 扩展名兜底（某些浏览器 MIME 可能为空）
  const ext = getFileExtension(file.name)
  if (ext && ALLOWED_EXTENSIONS.includes(ext)) {
    return true
  }

  return false
}

/** 获取文件扩展名（小写） */
function getFileExtension(filename: string): string {
  const idx = filename.lastIndexOf('.')
  if (idx < 0) return ''
  return filename.slice(idx).toLowerCase()
}
</script>

<style scoped>
.gt-attachment-dropzone {
  position: relative;
  width: 100%;
  height: 100%;
}

.gt-attachment-dropzone--active {
  outline: 2px dashed var(--el-color-primary, #409eff);
  outline-offset: -2px;
  border-radius: 4px;
}

.gt-attachment-dropzone-overlay {
  position: absolute;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(64, 158, 255, 0.08);
  backdrop-filter: blur(2px);
  border-radius: 4px;
  pointer-events: none;
}

.gt-attachment-dropzone-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 32px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.gt-attachment-dropzone-icon {
  font-size: 32px;
}

.gt-attachment-dropzone-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-color-primary, #409eff);
}

.gt-attachment-dropzone-hint {
  font-size: 12px;
  color: #999;
}

.gt-attachment-dropzone-uploading {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 200;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  font-size: 13px;
  color: var(--el-color-primary, #409eff);
}

/* 过渡动画 */
.gt-fade-enter-active,
.gt-fade-leave-active {
  transition: opacity 0.2s ease;
}
.gt-fade-enter-from,
.gt-fade-leave-to {
  opacity: 0;
}
</style>
