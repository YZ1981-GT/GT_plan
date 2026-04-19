<template>
  <div class="gt-private-storage">
    <div class="gt-ps-header">
      <h2>私人库</h2>
      <div class="gt-ps-quota">
        <el-progress
          :percentage="quotaPct"
          :color="quota.warning ? '#F56C6C' : 'var(--gt-color-primary, #4b2d77)'"
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

    <!-- 文件列表 -->
    <el-table v-if="files.length > 0" :data="files" stripe size="default" v-loading="loading">
      <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column label="大小" width="100" align="right">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="modified_at" label="修改时间" width="180">
        <template #default="{ row }">{{ formatTime(row.modified_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="onDownload(row.name)">下载</el-button>
          <el-button type="danger" size="small" text @click="onDelete(row.name)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <el-empty v-if="!loading && files.length === 0" description="私人库为空，上传文件开始使用" />

    <!-- 错误提示 -->
    <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon closable @close="errorMsg = ''" style="margin-top: 16px" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import http from '@/utils/http'

const authStore = useAuthStore()
const loading = ref(false)
const errorMsg = ref('')
const files = ref<any[]>([])
const quota = ref({ used: 0, limit: 1073741824, usage_pct: 0, warning: false })

const quotaPct = computed(() => Math.round((quota.value.usage_pct || 0) * 100))

// 获取当前用户 ID（从 auth store）
async function ensureUser() {
  if (!authStore.user) {
    try {
      await authStore.fetchUserProfile()
    } catch {
      // 静默失败
    }
  }
}

function getUserId(): string {
  const uid = authStore.userId || authStore.user?.id
  if (!uid) {
    errorMsg.value = '未获取到用户信息，请重新登录'
    return ''
  }
  return String(uid)
}

async function fetchFiles() {
  const uid = getUserId()
  if (!uid) return

  loading.value = true
  errorMsg.value = ''
  try {
    const { data: filesData } = await http.get(`/api/users/${uid}/private-storage`)
    files.value = Array.isArray(filesData) ? filesData : filesData?.files || []
  } catch (e: any) {
    files.value = []
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载文件列表失败'
  }

  try {
    const { data: quotaData } = await http.get(`/api/users/${uid}/private-storage/quota`)
    if (quotaData) quota.value = quotaData
  } catch {
    // 容量查询失败不阻断
  }

  loading.value = false
}

async function onFileSelect(file: any) {
  const uid = getUserId()
  if (!uid) return

  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    await http.post(`/api/users/${uid}/private-storage/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('上传成功')
    await fetchFiles()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
  }
}

async function onDownload(name: string) {
  const uid = getUserId()
  if (!uid) return
  try {
    const { data } = await http.get(`/api/users/${uid}/private-storage/${name}/download`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  }
}

async function onDelete(name: string) {
  const uid = getUserId()
  if (!uid) return

  await ElMessageBox.confirm(`确定删除「${name}」？`, '删除确认', { type: 'warning' })
  try {
    await http.delete(`/api/users/${uid}/private-storage/${name}`)
    ElMessage.success('已删除')
    await fetchFiles()
  } catch {
    ElMessage.error('删除失败')
  }
}

function formatSize(bytes: number) {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + 'GB'
}

function formatTime(t: string | null) {
  if (!t) return '—'
  return t.slice(0, 19).replace('T', ' ')
}

onMounted(async () => {
  await ensureUser()
  await fetchFiles()
})
</script>

<style scoped>
.gt-private-storage { padding: 20px; }
.gt-ps-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.gt-ps-header h2 { margin: 0; font-size: 20px; color: #333; }
.gt-ps-quota { display: flex; align-items: center; gap: 10px; }
.gt-ps-quota-text { font-size: 13px; color: #999; }
.gt-ps-actions { display: flex; gap: 8px; margin-bottom: 16px; }
</style>
