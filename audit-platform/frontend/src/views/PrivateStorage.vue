<template>
  <div class="gt-private-storage gt-fade-in">
    <div class="gt-ps-header">
      <h2 class="gt-page-title">私人库</h2>
      <div class="gt-ps-quota">
        <el-progress
          :percentage="Math.round(quota.usage_pct * 100)"
          :color="quota.warning ? '#F56C6C' : 'var(--gt-color-primary)'"
          :stroke-width="8"
          style="width: 200px"
        />
        <span class="gt-ps-quota-text">
          {{ formatSize(quota.used) }} / {{ formatSize(quota.limit) }}
        </span>
        <el-tag v-if="quota.warning" type="danger" size="small">容量不足</el-tag>
      </div>
    </div>

    <div class="gt-ps-actions">
      <el-upload :auto-upload="false" :show-file-list="false" @change="onFileSelect">
        <el-button type="primary">上传文件</el-button>
      </el-upload>
      <el-button @click="fetchFiles" :loading="loading">刷新</el-button>
    </div>

    <el-table :data="files" stripe size="default" v-loading="loading">
      <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column label="大小" width="100" align="right">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="modified_at" label="修改时间" width="180">
        <template #default="{ row }">{{ row.modified_at?.slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="onDelete(row.name)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && files.length === 0" description="私人库为空，上传文件开始使用" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// TODO: 从认证状态获取当前用户ID
const userId = ref('me')

const loading = ref(false)
const files = ref<any[]>([])
const quota = ref({ used: 0, limit: 1073741824, usage_pct: 0, warning: false })

async function fetchFiles() {
  loading.value = true
  try {
    const [fResp, qResp] = await Promise.all([
      http.get(`/api/users/${userId.value}/private-storage`),
      http.get(`/api/users/${userId.value}/private-storage/quota`),
    ])
    files.value = fResp.data?.data ?? fResp.data ?? []
    const q = qResp.data?.data ?? qResp.data
    if (q) quota.value = q
  } catch { /* silent */ } finally { loading.value = false }
}

async function onFileSelect(file: any) {
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    await http.post(`/api/users/${userId.value}/private-storage/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('上传成功')
    await fetchFiles()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
  }
}

async function onDelete(name: string) {
  await ElMessageBox.confirm(`确定删除「${name}」？`, '删除确认', { type: 'warning' })
  try {
    await http.delete(`/api/users/${userId.value}/private-storage/${name}`)
    ElMessage.success('已删除')
    await fetchFiles()
  } catch { ElMessage.error('删除失败') }
}

function formatSize(bytes: number) {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + 'GB'
}

onMounted(fetchFiles)
</script>

<style scoped>
.gt-private-storage { padding: var(--gt-space-4); }
.gt-ps-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-ps-quota { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-ps-quota-text { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-ps-actions { display: flex; gap: var(--gt-space-2); margin-bottom: var(--gt-space-3); }
</style>
