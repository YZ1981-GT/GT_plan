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
 * ItemAttachment — 逐项附件组件（Sprint 2 Task 2.25）
 *
 * 锚定 requirements F6.2 + F6.4
 * 后端关联：object_type='workpaper_item' + object_id='{wp_id}:{sheet_key}:{item_index}'
 */
import { ref, onMounted, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { confirmDelete } from '@/utils/confirm'

interface AttItem {
  id: string
  filename: string
  file_size: number
  created_at?: string
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

const objectType = 'workpaper_item'
const objectId = () => `${props.wpId}:${props.sheetKey}:${props.itemIndex}`

async function loadList() {
  try {
    const data: any = await api.get('/api/attachments', {
      params: {
        object_type: objectType,
        object_id: objectId(),
      },
    })
    attachments.value = (data?.items || data || []).map((a: any) => ({
      id: a.id,
      filename: a.filename || a.original_name,
      file_size: a.file_size || 0,
      created_at: a.created_at,
    }))
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
    formData.append('object_type', objectType)
    formData.append('object_id', objectId())
    formData.append('project_id', props.projectId)
    await api.post(`/api/projects/${props.projectId}/attachments/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('附件已上传')
    await loadList()
  } catch (err: any) {
    ElMessage.error('上传失败：' + (err?.message || '未知错误'))
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
  try {
    await api.delete(`/api/attachments/${id}`)
    attachments.value = attachments.value.filter((a) => a.id !== id)
  } catch (err: any) {
    ElMessage.error('删除失败')
  }
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

onMounted(loadList)
watch(() => [props.wpId, props.sheetKey, props.itemIndex], loadList)
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
