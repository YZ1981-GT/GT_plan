<template>
  <div class="gt-item-attach">
    <div class="gt-item-attach-list">
      <div
        v-for="att in attachments"
        :key="att.id"
        class="gt-item-attach-row"
      >
        <el-icon><Document /></el-icon>
        <a :href="downloadUrl(att.id)" target="_blank" class="gt-item-attach-link">{{ att.filename }}</a>
        <span class="gt-item-attach-size">{{ formatSize(att.file_size) }}</span>
        <el-button text size="small" type="danger" @click="onDelete(att.id)">×</el-button>
      </div>
    </div>

    <el-upload
      :auto-upload="true"
      :show-file-list="false"
      :http-request="onUpload"
      :before-upload="beforeUpload"
      :accept="accept || '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg'"
    >
      <el-button size="small" plain :loading="uploading">📎 上传附件</el-button>
    </el-upload>
  </div>
</template>

<script setup lang="ts">
/**
 * ItemAttachment — 逐项附件组件
 *
 * 关联键：title = `{wp_id}:{sheet_key}:{item_index}`（上传时写入）
 * 列表：GET /api/projects/{project_id}/attachments，再按 title 过滤
 */
import { ref, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { confirmDelete } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'

interface AttItem {
  id: string
  filename: string
  file_size: number
  created_at?: string
  title?: string
}
interface Props {
  projectId: string
  wpId: string
  sheetKey: string
  itemIndex: number
  accept?: string
}
const props = defineProps<Props>()

const attachments = ref<AttItem[]>([])
const uploading = ref(false)

const ATTACHMENT_TYPE = 'workpaper_item'
const objectId = () => `${props.wpId}:${props.sheetKey}:${props.itemIndex}`

function normalizeList(raw: any): AttItem[] {
  const rows = Array.isArray(raw) ? raw : (raw?.items || raw?.data || [])
  if (!Array.isArray(rows)) return []
  const key = objectId()
  return rows
    .filter((a: any) => {
      const title = String(a?.title || '')
      const docType = String(a?.document_type || '')
      return title === key || docType === key
    })
    .map((a: any) => ({
      id: a.id,
      filename: a.filename || a.original_name || a.file_name || '附件',
      file_size: a.file_size || 0,
      created_at: a.created_at,
      title: a.title,
    }))
}

async function loadList() {
  if (!props.projectId || !props.wpId) {
    attachments.value = []
    return
  }
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/attachments`, {
      params: { attachment_type: ATTACHMENT_TYPE },
      _silent: true,
    } as any)
    attachments.value = normalizeList(data)
    // 兼容历史未打 attachment_type 的附件：若过滤为空则拉全量再按 title 过滤
    if (attachments.value.length === 0) {
      const all: any = await api.get(`/api/projects/${props.projectId}/attachments`, {
        _silent: true,
      } as any)
      attachments.value = normalizeList(all)
    }
  } catch {
    attachments.value = []
  }
}

function beforeUpload(file: File): boolean {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

async function onUpload(req: any) {
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', req.file)
    formData.append('attachment_type', ATTACHMENT_TYPE)
    formData.append('reference_type', ATTACHMENT_TYPE)
    formData.append('title', objectId())
    formData.append('document_type', objectId())
    await api.post(`/api/projects/${props.projectId}/attachments/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    ElMessage.success('附件已上传')
    await loadList()
  } catch (err: any) {
    handleApiError(err, '上传')
  } finally {
    uploading.value = false
  }
}

async function onDelete(id: string) {
  const att = attachments.value.find((a) => a.id === id)
  try {
    await confirmDelete(att?.filename ? `附件「${att.filename}」` : '该附件')
  } catch {
    return
  }
  // 后端暂无通用 DELETE；先本地移除，避免误报 404
  attachments.value = attachments.value.filter((a) => a.id !== id)
  ElMessage.info('已从本页移除显示（服务端删除接口待接入）')
}

function downloadUrl(id: string): string {
  return `/api/attachments/${id}/download`
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

watch(
  () => [props.projectId, props.wpId, props.sheetKey, props.itemIndex] as const,
  () => { void loadList() },
  { immediate: true },
)
</script>

<style scoped>
.gt-item-attach {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-item-attach-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-item-attach-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 3px 6px;
  font-size: 12px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 3px;
}
.gt-item-attach-link {
  flex: 1;
  color: var(--gt-color-primary, #4b2d77);
  text-decoration: none;
}
.gt-item-attach-link:hover {
  text-decoration: underline;
}
.gt-item-attach-size {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
