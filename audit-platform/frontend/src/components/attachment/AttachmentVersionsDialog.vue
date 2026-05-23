<template>
  <el-dialog
    v-model="visible"
    title="附件历史版本"
    width="640px"
    append-to-body
    @closed="handleClosed"
  >
    <div v-loading="loading" class="gt-att-versions">
      <el-empty v-if="!loading && versions.length === 0" description="暂无版本记录" />
      <el-table
        v-else
        :data="versions"
        size="small"
        stripe
        max-height="420"
      >
        <el-table-column prop="version" label="版本" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.version === latestVersion ? 'success' : 'info'" size="small">
              v{{ row.version }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="160" show-overflow-tooltip />
        <el-table-column label="大小" width="90" align="right">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="uploaded_at" label="上传时间" width="150">
          <template #default="{ row }">{{ formatDate(row.uploaded_at) }}</template>
        </el-table-column>
        <el-table-column prop="uploaded_by" label="上传人" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-text-tertiary">{{ row.uploaded_by ? row.uploaded_by.slice(0, 8) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="onPreview(row)">预览</el-button>
            <el-button
              v-if="row.version !== latestVersion"
              link
              type="warning"
              size="small"
              @click="onRollback(row)"
            >
              回滚到此版本
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <template #footer>
      <el-button size="small" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface AttachmentVersion {
  id: string
  version: number
  previous_version_id: string | null
  file_name: string
  file_size: number
  file_type: string
  storage_type: string
  uploaded_by: string | null
  uploaded_at: string | null
  is_deleted: boolean
}

const props = defineProps<{
  modelValue: boolean
  attachmentId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'rolled-back', payload: { newVersion: AttachmentVersion }): void
  (e: 'preview', payload: AttachmentVersion): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const loading = ref(false)
const versions = ref<AttachmentVersion[]>([])

const latestVersion = computed(() =>
  versions.value.length > 0 ? Math.max(...versions.value.map((v) => v.version)) : 0
)

watch(
  () => [props.modelValue, props.attachmentId] as const,
  async ([show, id]) => {
    if (show && id) {
      await loadVersions()
    }
  },
  { immediate: true }
)

async function loadVersions() {
  if (!props.attachmentId) return
  loading.value = true
  try {
    const data = await api.get(P_att.versions(props.attachmentId))
    versions.value = (data?.versions ?? []) as AttachmentVersion[]
  } catch (e) {
    handleApiError(e, '加载版本')
    versions.value = []
  } finally {
    loading.value = false
  }
}

function onPreview(row: AttachmentVersion) {
  emit('preview', row)
}

async function onRollback(row: AttachmentVersion) {
  try {
    await ElMessageBox.confirm(
      `确认将文件回滚到 v${row.version}？将创建 v${latestVersion.value + 1} 复制 v${row.version} 的内容，旧版本仍保留。`,
      '回滚确认',
      { confirmButtonText: '确认回滚', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  loading.value = true
  try {
    const result = await api.post(P_att.rollback(props.attachmentId, row.id), {})
    ElMessage.success(`已回滚为 v${result?.version ?? '?'}`)
    emit('rolled-back', { newVersion: result as AttachmentVersion })
    await loadVersions()
  } catch (e) {
    handleApiError(e, '回滚')
  } finally {
    loading.value = false
  }
}

function handleClosed() {
  versions.value = []
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.gt-att-versions { min-height: 200px; }
.gt-text-tertiary { color: var(--gt-color-text-tertiary); font-family: var(--gt-font-mono, monospace); font-size: var(--gt-font-size-xs); }
</style>
